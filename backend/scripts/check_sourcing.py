"""Run one live grounded search and verify candidate pages; no checkout or selection."""

import argparse
from pathlib import Path

from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import BomItem
from bharat_sourcer.sourcing.service import GeminiDiscovery, SourcingService

parser = argparse.ArgumentParser()
parser.add_argument("--part", required=True)
args = parser.parse_args()
settings = Settings()
result = SourcingService(GeminiDiscovery(settings)).source(
    BomItem(line_id="L01", raw_name=args.part)
)
target = Path(".data/sourcing-check.json")
target.parent.mkdir(exist_ok=True)
target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
print(result.model_dump_json(indent=2, exclude={"attribution"}))
print(
    {
        "candidate_count": len(result.attribution.source_urls) if result.attribution else 0,
        "saved_to": str(target),
    }
)
