"""Re-source a saved job's BOM with the live sourcing engine and print the result.

Makes real seller fetches and real Gemini calls (judge, grounded discovery, research), so it
costs money: run it only with the owner's approval. Nothing is written to Firestore; the
shared cache is in memory.

    python scripts/check_job_sourcing.py job.json

`job.json` is a Job snapshot (for example from scripts/inspect_job.py's store read).
"""

import argparse
import json
import time
from decimal import Decimal

from bharat_sourcer.config import Settings
from bharat_sourcer.costing import update_costs
from bharat_sourcer.recommend import apply_recommendations
from bharat_sourcer.schemas import Job, Report
from bharat_sourcer.sourcing import seller_search
from bharat_sourcer.sourcing.cache import build_cache
from bharat_sourcer.sourcing.judge import GeminiJudge
from bharat_sourcer.sourcing.research import GeminiResearch
from bharat_sourcer.sourcing.service import GeminiDiscovery, SourcingService
from bharat_sourcer.sourcing.spec_writer import GeminiSpecWriter
from bharat_sourcer.sourcing.trust import TrustChecker
from bharat_sourcer.storage import MemoryJobStore
from bharat_sourcer.usage import JobLedger, attribute

parser = argparse.ArgumentParser()
parser.add_argument("job_json")
parser.add_argument("--lines", nargs="*", help="only these line ids")
args = parser.parse_args()

job = Job.model_validate(json.load(open(args.job_json, encoding="utf-8")))
if args.lines:
    job.items = [item for item in job.items if item.line_id in args.lines]
settings = Settings(demo_mode=False, storage_backend="memory", sourcing_enabled=True)
cache = build_cache(settings, MemoryJobStore())
sourcing = SourcingService(
    GeminiDiscovery(settings),
    researcher=GeminiResearch(settings, cache=cache) if settings.research_enabled else None,
    followup_enabled=settings.research_followup_enabled,
    trust=TrustChecker() if settings.seller_trust_enabled else None,
    seller_search=seller_search.from_settings(settings, cache=cache),
    seller_fetch_budget=settings.seller_search_fetch_budget,
    seller_limit=settings.seller_search_per_seller,
    judge=GeminiJudge(settings, cache=cache) if settings.judge_enabled else None,
    spec_writer=GeminiSpecWriter(settings, cache=cache) if settings.spec_writer_enabled else None,
)
ledger = JobLedger(job.job_id, settings.job_gemini_budget_usd)
lines = []
started = time.monotonic()
# As JobService does: one batched spec call for lines without an AI buying spec.
with attribute(ledger, None):
    specs = sourcing.write_specs(job.items, job.project)
for item in job.items:
    if item.line_id in specs:
        item.buyable_spec = specs[item.line_id]
for item in job.items:
    with attribute(ledger, item.line_id):
        lines.append(sourcing.source_for_project(item, job.items, project=job.project))
report = Report(demo=False, summary="Live sourcing check (not saved).", lines=lines)
apply_recommendations(report, Decimal(settings.recommend_seller_penalty_inr))
update_costs(report)

print(f"\n=== {job.project.title if job.project else job.input.url} ===")
print(f"time {time.monotonic() - started:.0f}s, est. Gemini cost ${ledger.total_usd:.3f}")
for line in report.lines:
    spec = line.buyable_spec
    print(f"\n## {line.item.raw_name}: {line.sourcing_status}  stages={line.stages}")
    if spec:
        print(
            f"   spec: {spec.category} mount={spec.mount} needs_value={spec.needs_value}"
            f" queries={spec.queries}"
        )
    for offer in line.offers[:5]:
        match = offer.match
        print(
            f"   - {offer.seller} | {offer.title[:60]} | Rs {offer.price_inr} | {offer.stock}"
            f" | match={match.status if match else None}"
            f" | grade={offer.compatibility.grade if offer.compatibility else None}"
        )
        if match:
            print(f"       why: {'; '.join(match.reasons)[:300]} | claims={len(match.claims)}")
    print(
        f"   selected={line.selected_offer_url} ({line.selection_source})"
        f" image={line.line_image.kind if line.line_image else None}"
    )
    if line.sourcing_error:
        print(f"   error: {line.sourcing_error.message[:300]}")
plan = report.order_plan
if plan:
    print("\n=== Order plan ===")
    for group in plan.sellers:
        names = ", ".join(entry.name for entry in group.lines)
        print(f"   {group.seller}: {names} | subtotal Rs {group.subtotal_inr}")
    for entry in plan.unsourced:
        print(f"   unsourced: {entry.name}: {entry.reason}: {entry.message[:160]}")
