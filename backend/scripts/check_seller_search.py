"""Live seller-catalogue search plus the existing verifier; no Gemini or other paid calls.

For each part: seller-search candidates (grounded discovery is not run, so it reports 0),
fetched candidate pages, pages with an extractable INR offer ignoring the title match, and
offers that pass the current verifier (title match included). Requests are polite: robots.txt,
per-host pacing, caching and challenge detection; blocked sellers are reported, not bypassed.

    python scripts/check_seller_search.py [--part "5mm LED" ...] [--budget 8]
"""

import argparse
import json
from pathlib import Path
from unittest.mock import patch

from bharat_sourcer.compat import resolve_part
from bharat_sourcer.schemas import BomItem
from bharat_sourcer.sourcing.fetch import FetchError, SafeFetcher
from bharat_sourcer.sourcing.listings import variant_url, verify_page
from bharat_sourcer.sourcing.platforms import storefront_offer
from bharat_sourcer.sourcing.politeness import BlockedError, PoliteFetcher, Politeness
from bharat_sourcer.sourcing.seller_search import SellerSearch, query_variants

PARTS = [
    "33kΩ resistor",
    "22µF 16V electrolytic capacitor",
    "5mm LED",
    "LDR",
    "bare copper wire",
]


def verify(page, query, fetcher):
    offer = verify_page(page, query)
    if offer is None:
        variant = variant_url(page, query)
        if variant:
            offer = verify_page(fetcher.get(variant), query)
    return offer or storefront_offer(page, query, fetcher)


def loose(page, query, fetcher):
    """Same extraction with the title match disabled: is there any INR offer at all?"""
    with (
        patch("bharat_sourcer.sourcing.listings.title_matches", lambda q, t: True),
        patch("bharat_sourcer.sourcing.platforms.title_matches", lambda q, t: True),
    ):
        return verify(page, query, fetcher)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--part", action="append")
    parser.add_argument("--budget", type=int, default=8, help="Pages fetched per part")
    args = parser.parse_args()
    politeness = Politeness()
    raw = SafeFetcher()
    search = SellerSearch(politeness, raw)
    fetcher = PoliteFetcher(raw, politeness)
    report = []
    for name in args.part or PARTS:
        item = BomItem(line_id="L01", raw_name=name)
        query = resolve_part(item).query
        result = search.search(query_variants([name, query]), 5, args.budget)
        print(f"\n=== {name}  queries={result.queries}")
        for d in result.diagnostics:
            print(f"  seller {d.seller:24} {d.status:26} {d.candidates} {d.detail or ''}")
        fetched = extractable = 0
        verified, rows = [], []
        for candidate in result.candidates:
            row = {"url": candidate.url, "title_hint": candidate.title, "status": None}
            try:
                page = fetcher.get(candidate.url)
                fetched += 1
                any_offer = loose(page, query, fetcher)
                offer = verify(page, query, fetcher)
                extractable += bool(any_offer)
                row["status"] = (
                    "verified" if offer else "extractable_title_mismatch" if any_offer else "none"
                )
                if any_offer:
                    row["price_inr"], row["stock"] = any_offer.price_inr, any_offer.stock
                    row["page_title"] = any_offer.title
                if offer:
                    verified.append(offer)
            except BlockedError as exc:
                row["status"] = f"blocked ({exc.reason})"
            except (FetchError, ValueError) as exc:
                row["status"] = f"error ({exc})"
            rows.append(row)
            print(
                f"  {row['status']:28} {row.get('price_inr') or '':>8} "
                f"{(candidate.title or '')[:55]:55} {candidate.url}"
            )
        summary = {
            "part": name,
            "candidates_seller_search": len(result.candidates),
            "candidates_grounded": 0,
            "fetched": fetched,
            "extractable_inr_offer": extractable,
            "verified_current_matcher": len(verified),
            "verified_sellers": sorted({o.seller for o in verified}),
            "blocked": result.blocked(),
            "message": result.message(),
        }
        print("  " + json.dumps(summary, ensure_ascii=False))
        report.append({**summary, "rows": rows})
    target = Path(".data/seller-search-check.json")
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(
        "\nTOTAL",
        json.dumps(
            {
                k: sum(r[k] for r in report)
                for k in (
                    "candidates_seller_search",
                    "fetched",
                    "extractable_inr_offer",
                    "verified_current_matcher",
                )
            }
        ),
        "saved_to",
        target,
    )


if __name__ == "__main__":
    main()
