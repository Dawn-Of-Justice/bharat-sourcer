import pathlib
"""Live probe of the free direct seller search (no model calls). Sequential, polite."""

import json
import os
import sys
import time
from pathlib import Path

for key in list(os.environ):
    if key.startswith("BS_") or "GEMINI" in key or "VERTEX" in key or "GOOGLE_API" in key:
        os.environ.pop(key)

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5] / "backend" / "src"))

from bharat_sourcer.compat import resolve_part  # noqa: E402
from bharat_sourcer.schemas import BomItem  # noqa: E402
from bharat_sourcer.sourcing.fetch import SafeFetcher  # noqa: E402
from bharat_sourcer.sourcing.listings import title_matches  # noqa: E402
from bharat_sourcer.sourcing.part_spec import buyable_spec  # noqa: E402
from bharat_sourcer.sourcing.politeness import Politeness  # noqa: E402
from bharat_sourcer.sourcing.seller_search import SellerSearch  # noqa: E402
from bharat_sourcer.sourcing.service import seller_queries  # noqa: E402

OUT = Path(__file__).parent
RAW = OUT / "raw"
RAW.mkdir(exist_ok=True)
CAP = 330

PARTS = [
    "Arduino Uno R3", "ESP32 DevKit V1", "10k ohm resistor", "BME280 sensor module",
    "SG90 servo", "HC-SR04 ultrasonic sensor", "0.96 inch OLED I2C", "LM2596 buck converter",
    "TP4056 charging module", "jumper wires male to female", "18650 battery holder 2 cell",
    "WS2812B LED strip", "NEMA 17 stepper motor", "A4988 driver", "100uF 25V capacitor",
    "IRFZ44N mosfet", "Raspberry Pi Pico",
]


class Recording:
    def __init__(self):
        self.inner = SafeFetcher()
        self.log = []

    def get(self, url, **kwargs):
        start = time.monotonic()
        entry = {"url": url}
        try:
            page = self.inner.get(url, **kwargs)
            entry.update(status=page.status, ctype=page.headers.get("content-type"),
                         bytes=len(page.body), final=page.url)
            return page
        except Exception as exc:
            entry.update(error=f"{type(exc).__name__}: {exc}")
            raise
        finally:
            entry["latency_s"] = round(time.monotonic() - start, 2)
            entry["n"] = len(self.log) + 1
            self.log.append(entry)
            if len(self.log) >= CAP:
                raise SystemExit("request cap reached")


rec = Recording()
search = SellerSearch(Politeness(), fetcher=rec, max_workers=1)
results = []
for part in PARTS:
    item = BomItem(line_id="L01", raw_name=part, evidence=[])
    spec, resolution = buyable_spec(item), resolve_part(item)
    queries = seller_queries(spec.queries, part, resolution.query)
    for seller in search.sellers:
        before = len(rec.log)
        start = time.monotonic()
        found, diag = search._search_one(seller, queries, 5)
        reqs = rec.log[before:]
        results.append({
            "part": part,
            "seller": seller["domain"],
            "queries_planned": queries,
            "queries_tried": diag.queries,
            "status": diag.status,
            "detail": diag.detail,
            "candidates": len(found),
            "latency_s": round(time.monotonic() - start, 2),
            "http": [(r.get("status"), r.get("error"), r["latency_s"]) for r in reqs
                     if "robots.txt" not in r["url"]],
            "top": [{"title": c.title, "url": c.url, "score": round(c.score, 2),
                     "price_hint": c.price_hint, "query": c.query,
                     "legacy_gate": title_matches(part, c.title or "")} for c in found[:5]],
        })
        print(part, seller["domain"], diag.status, len(found), diag.detail or "",
              [c.title for c in found[:2]], flush=True)
        (OUT / "search_results.json").write_text(json.dumps(results, indent=1), "utf-8")
        (OUT / "search_requests.json").write_text(json.dumps(rec.log, indent=1), "utf-8")
print("requests", len(rec.log))
