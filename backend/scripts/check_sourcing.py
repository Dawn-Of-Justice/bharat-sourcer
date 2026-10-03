"""Run one live grounded search and verify candidate pages; no checkout or selection."""

import argparse
from pathlib import Path

from bharat_sourcer.config import Settings
from bharat_sourcer.schemas import BomItem
from bharat_sourcer.sourcing.research import GeminiResearch
from bharat_sourcer.sourcing.service import GeminiDiscovery, SourcingService

parser = argparse.ArgumentParser()
parser.add_argument("--part", required=True)
parser.add_argument("--research", action="store_true", help="Also run paid evidence research")
parser.add_argument("--followup", action="store_true", help="Allow one extra search if no evidence")
args = parser.parse_args()
settings = Settings()
result = SourcingService(
    GeminiDiscovery(settings),
    researcher=GeminiResearch(settings) if args.research else None,
    followup_enabled=args.followup,
).source(BomItem(line_id="L01", raw_name=args.part))
target = Path(".data/sourcing-check.json")
target.parent.mkdir(exist_ok=True)
target.write_text(result.model_dump_json(indent=2), encoding="utf-8")
print(
    {
        "sourcing_status": result.sourcing_status,
        "verified_offers": len(result.offers),
        "research_status": result.research.status if result.research else None,
        "research_candidates": len(result.research.candidates) if result.research else 0,
        "facts": sum(len(c.facts) for c in result.research.candidates) if result.research else 0,
        "read_sources": sum(s.reviewed for s in result.research.sources) if result.research else 0,
    }
)
print(
    {
        "candidate_count": len(result.attribution.source_urls) if result.attribution else 0,
        "saved_to": str(target),
    }
)
