"""Bounded live discovery comparison; no extraction, Gemini judge, or checkout claims."""

import argparse
import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

from bharat_sourcer.compat import resolve_part
from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import BomItem
from bharat_sourcer.sourcing.coordination import MemoryCoordinator
from bharat_sourcer.sourcing.fetch import SafeFetcher
from bharat_sourcer.sourcing.listings import variant_url, verify_page
from bharat_sourcer.sourcing.platforms import storefront_offer
from bharat_sourcer.sourcing.politeness import PoliteFetcher, Politeness
from bharat_sourcer.sourcing.providers import ProviderSearch
from bharat_sourcer.sourcing.seller_search import SellerSearch, query_variants, url_key

PROJECTS = [
    {
        "name": "ESP32 BME280 weather station",
        "url": "https://randomnerdtutorials.com/esp32-web-server-with-bme280-mini-weather-station/",
        "parts": ["ESP32 DOIT DevKit V1", "BME280 sensor module"],
    },
    {
        "name": "Arduino ultrasonic distance / temperature correction",
        "url": "https://dronebotworkshop.com/hc-sr04-ultrasonic-distance-sensor-arduino/",
        "parts": ["Arduino Uno", "HC-SR04 ultrasonic sensor", "DHT22 temperature humidity sensor"],
    },
    {
        "name": "Arduino 28BYJ-48 stepper (demo 1)",
        "url": "https://dronebotworkshop.com/stepper-motors-with-arduino/",
        "parts": ["Arduino Uno", "28BYJ-48 5V stepper motor", "ULN2003 driver board"],
    },
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    logging.disable(logging.CRITICAL)
    settings = Settings(mouser_search_api_key=None)
    if not settings.brave_search_api_key or not settings.shopify_catalog_enabled:
        raise SystemExit("Configure Brave and Shopify before running this comparison.")
    coordinator = MemoryCoordinator()
    raw = SafeFetcher(coordinator=coordinator)
    polite = Politeness(coordinator=coordinator)
    fetcher = PoliteFetcher(raw, polite)
    direct = SellerSearch(politeness=polite, fetcher=raw)
    providers = ProviderSearch(settings, coordinator)
    result = {
        "started_at": datetime.now(UTC).isoformat(),
        "projects": PROJECTS,
        "method": (
            "Fixed core-component baskets; direct search plus incremental providers; "
            "8 verification candidates per stage; existing deterministic page matcher; "
            "no Gemini fallback/judge, extraction, shipping or checkout validation. "
            "Supplies, wiring and breadboards excluded. Shared components tested once. "
            "Direct stage always runs first; warm shared cache/pacing means timings are "
            "operational, not randomized A/B latency."
        ),
        "parts": [],
    }
    parts = list(dict.fromkeys(p for project in PROJECTS for p in project["parts"]))
    for name in parts:
        print("Starting:", name, flush=True)
        query = resolve_part(BomItem(line_id="L01", raw_name=name)).query
        memo = {}

        def verify(candidates, memo=memo, query=query):
            rows = []
            for candidate in candidates:
                key = url_key(candidate.url)
                if key in memo:
                    rows.append(dict(memo[key], source=candidate.source, reused=True))
                    continue
                row = {"source": candidate.source, "url": candidate.url, "reused": False}
                try:
                    page = fetcher.get(candidate.url)
                    offer = verify_page(page, query)
                    if offer is None:
                        variant = variant_url(page, query)
                        if variant:
                            offer = verify_page(fetcher.get(variant), query)
                    offer = offer or storefront_offer(page, query, fetcher)
                    row["status"] = "verified" if offer else "no_verified_offer"
                    if offer:
                        row.update(
                            title=offer.title,
                            stock=offer.stock,
                            price_inr=str(offer.price_inr),
                            seller=offer.seller,
                            offer_url=str(offer.url),
                        )
                except Exception as exc:
                    # Exception text may contain sensitive URLs; retain only class.
                    row["status"] = type(exc).__name__
                memo[key] = row
                rows.append(row)
            return rows

        start = time.monotonic()
        d = direct.search(query_variants([name, query]), 5, 8)
        direct_search_s = time.monotonic() - start
        baseline = verify(d.candidates)
        baseline_s = time.monotonic() - start
        start = time.monotonic()
        p = providers.search(query, budget=8)
        provider_search_s = time.monotonic() - start
        extra = verify(p.candidates)
        incremental_s = time.monotonic() - start
        base = {
            url_key(r.get("offer_url", r["url"])) for r in baseline if r["status"] == "verified"
        }
        expanded = base | {
            url_key(r.get("offer_url", r["url"])) for r in extra if r["status"] == "verified"
        }
        row = {
            "name": name,
            "query": query,
            "baseline": baseline,
            "external": extra,
            "baseline_verified": len(base),
            "expanded_verified": len(expanded),
            "baseline_seconds": round(baseline_s, 2),
            "direct_search_seconds": round(direct_search_s, 2),
            "incremental_seconds": round(incremental_s, 2),
            "provider_search_seconds": round(provider_search_s, 2),
            "provider_diagnostics": [asdict(x) for x in p.diagnostics],
            "direct_diagnostics": [asdict(x) for x in d.diagnostics],
        }
        result["parts"].append(row)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(
            name,
            "page-verified:",
            len(base),
            "->",
            len(expanded),
            "extra seconds:",
            round(incremental_s),
            "providers:",
            [(x.seller, x.status, x.candidates) for x in p.diagnostics],
            flush=True,
        )
    print("Complete:", args.output, flush=True)


if __name__ == "__main__":
    main()
