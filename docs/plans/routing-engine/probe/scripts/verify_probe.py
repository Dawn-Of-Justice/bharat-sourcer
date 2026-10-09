import pathlib
"""Run the production page verification path on a few live product URLs from the search probe."""

import json
import os
import re
import sys
import time
from pathlib import Path

for key in list(os.environ):
    if key.startswith("BS_") or "GEMINI" in key or "VERTEX" in key or "GOOGLE_API" in key:
        os.environ.pop(key)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5] / "backend" / "src"))

from bharat_sourcer.sourcing.fetch import SafeFetcher  # noqa: E402
from bharat_sourcer.sourcing.listings import (  # noqa: E402
    extract_product, meta_offer, page_products, variant_url, verify_page)
from bharat_sourcer.sourcing.platforms import (  # noqa: E402
    detect_platform, shopify_variants, storefront_offer)
from bharat_sourcer.sourcing.politeness import Politeness  # noqa: E402

OUT = Path(__file__).parent
PAGES = OUT / "pages"
PAGES.mkdir(exist_ok=True)
PER_SELLER = int(sys.argv[1]) if len(sys.argv) > 1 else 3

results = json.loads((OUT / "search_results.json").read_text("utf-8"))
picked: dict[str, list] = {}
for row in results:
    if not row["top"]:
        continue
    chosen = picked.setdefault(row["seller"], [])
    if len(chosen) < PER_SELLER and row["top"][0]["url"] not in {c[1] for c in chosen}:
        chosen.append((row["part"], row["top"][0]["url"], row["top"][0].get("price_hint")))

fetcher = Politeness().wrap(SafeFetcher())
log = []
PRICE_TEXT = re.compile(r"(?:₹|&#8377;|Rs\.?|INR)\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)")
STOCK_TEXT = re.compile(r"(?i)(in stock|out of stock|sold out|add to cart|notify me|backorder)")


def offer_dict(offer):
    if offer is None:
        return None
    return {"title": offer.title, "price_inr": offer.price_inr, "stock": offer.stock,
            "verification": offer.verification, "url": str(offer.url)}


for seller, rows in picked.items():
    for index, (part, url, hint) in enumerate(rows):
        entry = {"seller": seller, "part": part, "url": url, "price_hint": hint}
        start = time.monotonic()
        try:
            page = fetcher.get(url)
            body = page.body.decode("utf-8", errors="replace")
            name = f"{seller.split('.')[0]}_{index}.html"
            (PAGES / name).write_text(body, "utf-8")
            products, _ = page_products(page)
            ext = extract_product(page)
            entry.update(
                status=page.status, final=page.url, ctype=page.headers.get("content-type"),
                bytes=len(page.body), saved=name, platform=detect_platform(page),
                jsonld_products=len(products),
                jsonld_offers=[p.get("offers") for p in products][:2],
                extracted_options=None if ext is None else [
                    (str(o.price), o.stock, o.name, o.url) for o in ext.options[:6]],
                verify_page_judge=offer_dict(verify_page(page, None)),
                verify_page_legacy=offer_dict(verify_page(page, part)),
                variant_url=variant_url(page, part),
                storefront_judge=offer_dict(storefront_offer(page, None, fetcher)),
                meta_judge=offer_dict(meta_offer(page, None)),
                meta_legacy=offer_dict(meta_offer(page, part)),
                page_price_texts=list(dict.fromkeys(PRICE_TEXT.findall(body)))[:12],
                page_stock_texts=sorted({m.lower() for m in STOCK_TEXT.findall(body)}),
                og_meta=re.findall(r'<meta[^>]+(?:price|availability)[^>]*>', body)[:6],
            )
            if entry["verify_page_judge"] is None and entry["storefront_judge"] is None:
                group = shopify_variants(page, fetcher)
                entry["shopify_variants"] = None if group is None else [
                    (str(o.price), o.stock, o.name) for o in group.options[:6]]
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
        entry["latency_s"] = round(time.monotonic() - start, 2)
        log.append(entry)
        print(json.dumps({k: entry.get(k) for k in (
            "seller", "part", "status", "platform", "jsonld_products", "verify_page_judge",
            "storefront_judge", "meta_judge", "error")}, ensure_ascii=False)[:600], flush=True)
        (OUT / "verify_results.json").write_text(json.dumps(log, indent=1, default=str), "utf-8")
