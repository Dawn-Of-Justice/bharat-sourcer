"""Bounded live catalogue probe, no AI calls. Results are dated observations, not fixtures.

Run from backend/: python scripts/probe_routing.py. Writes ignored .data/routing-probe.json.
The cap includes robots.txt, redirects, retries and product verification HTTP requests.
The matching count is a deterministic title-gate proxy, not a human accuracy measurement.
"""

import argparse
import json
import time
from datetime import UTC, datetime
from pathlib import Path

from bharat_sourcer.compat import resolve_part
from bharat_sourcer.schemas import BomItem
from bharat_sourcer.sourcing.fetch import SafeFetcher
from bharat_sourcer.sourcing.listings import meta_offer, variant_url, verify_page
from bharat_sourcer.sourcing.part_spec import buyable_spec
from bharat_sourcer.sourcing.platforms import storefront_offer
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.sourcing.routing import route_queries
from bharat_sourcer.sourcing.seller_search import SellerSearch
from bharat_sourcer.sourcing.textmatch import title_gate

PARTS = [
    "Arduino Uno R3",
    "ESP32 DevKit V1",
    "10k ohm resistor",
    "BME280 sensor module",
    "SG90 servo",
    "HC-SR04 ultrasonic sensor",
    "0.96 inch OLED I2C",
    "LM2596 buck converter",
    "TP4056 charging module",
    "jumper wires male to female",
    "18650 battery holder 2 cell",
    "WS2812B LED strip",
    "NEMA 17 stepper motor",
    "A4988 driver",
    "100uF 25V capacitor",
    "IRFZ44N mosfet",
    "Raspberry Pi Pico",
]


class RequestCap(BaseException):
    """Cannot be swallowed by adapter error recovery."""


class RecordingFetcher(SafeFetcher):
    def __init__(self, cap=390):
        super().__init__()
        self.cap = cap
        self.requests = []

    def _request(self, url, max_bytes):
        if len(self.requests) >= self.cap:
            raise RequestCap()
        entry = {"url": url}
        self.requests.append(entry)
        started = time.monotonic()
        try:
            page = super()._request(url, max_bytes)
            entry["status"] = page.status
            return page
        except Exception as exc:
            entry["error"] = type(exc).__name__
            raise
        finally:
            entry["seconds"] = round(time.monotonic() - started, 2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true", help="Recheck saved candidate pages")
    args = parser.parse_args()
    output = Path(".data/routing-probe.json")
    output.parent.mkdir(exist_ok=True)
    fetcher = RecordingFetcher()
    polite = Politeness()
    search = SellerSearch(polite, fetcher=fetcher, max_workers=1)
    result = {
        "observed_at": datetime.now(UTC).isoformat(),
        "rows": [],
        "pages": [],
        "requests": fetcher.requests,
        "request_cap": fetcher.cap,
        "note": "Live observations; title-gate counts are not human accuracy scores.",
    }

    if args.verify_only:
        result = json.loads(output.read_text("utf-8"))
        fetcher.requests = result["requests"]
        result["pages"] = []
        result["verified_at"] = datetime.now(UTC).isoformat()

    def save():
        output.write_text(json.dumps(result, indent=2, ensure_ascii=False), "utf-8")

    try:
        for part in [] if args.verify_only else PARTS:
            item = BomItem(line_id="L01", raw_name=part)
            rungs = route_queries(buyable_spec(item), part, resolve_part(item).query)
            for seller in search.sellers:
                found, diagnostic = search._search_one(seller, rungs, 5)
                row = {
                    "part": part,
                    "seller": diagnostic.seller,
                    "status": diagnostic.status,
                    "queries": diagnostic.queries,
                    "top": [
                        {
                            "url": c.url,
                            "title": c.title,
                            "score": c.score,
                            "title_gate": title_gate(part, c.title or ""),
                        }
                        for c in found[:5]
                    ],
                }
                result["rows"].append(row)
                print(json.dumps(row, ensure_ascii=True), flush=True)
                save()
        # Verify a bounded sample, including the historical comma-price regression.
        selected = {}
        for row in result["rows"]:
            if row["top"] and row["seller"] not in selected:
                selected[row["seller"]] = row["top"][0]["url"]
        reader = polite.wrap(fetcher)
        for seller, url in selected.items():
            entry = {"seller": seller, "url": url}
            try:
                page = reader.get(url)
                offer = verify_page(page, None)
                if not offer and (variant := variant_url(page, None)):
                    offer = verify_page(reader.get(variant), None)
                offer = offer or storefront_offer(page, None, reader) or meta_offer(page, None)
                entry["offer"] = offer.model_dump(mode="json") if offer else None
            except Exception as exc:
                entry["error"] = type(exc).__name__
            result["pages"].append(entry)
            save()
    except RequestCap:
        result["cap_reached"] = True
    finally:
        save()
    print(f"Saved {len(result['rows'])} rows, {len(fetcher.requests)} HTTP requests: {output}")


if __name__ == "__main__":
    main()
