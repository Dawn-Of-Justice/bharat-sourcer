"""Summarise GEMINI_USAGE log lines per call site.

Run from backend/ with an identity that can read Cloud Logging:
    python scripts/usage_report.py --days 7
or offline on saved lines (one log line or JSON payload per line):
    python scripts/usage_report.py --file usage.log
"""

import argparse
import json
import subprocess
from collections import defaultdict

parser = argparse.ArgumentParser()
parser.add_argument("--days", type=int, default=7)
parser.add_argument("--file")
parser.add_argument("--project", default="hackathon-510415")
parser.add_argument("--service", default="bharat-sourcer-integration")
args = parser.parse_args()

if args.file:
    with open(args.file, encoding="utf-8") as handle:
        lines = handle.read().splitlines()
else:
    query = f'resource.labels.service_name="{args.service}" AND textPayload:"GEMINI_USAGE"'
    lines = subprocess.run(
        [
            "gcloud",
            "logging",
            "read",
            query,
            f"--project={args.project}",
            f"--freshness={args.days}d",
            "--limit=10000",
            "--format=value(textPayload)",
        ],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()

sites = defaultdict(lambda: defaultdict(int))
for line in lines:
    if "GEMINI_USAGE" not in line:
        continue
    try:
        fields = json.loads(line.split("GEMINI_USAGE", 1)[1])
    except ValueError:
        continue
    totals = sites[f"{fields.get('site')} ({fields.get('model')})"]
    totals["calls"] += 1
    totals["grounded"] += bool(fields.get("grounded"))
    for key in ("prompt", "output", "thoughts", "cached", "tool_prompt"):
        totals[key] += int(fields.get(key) or 0)

print(
    f"{'site':40} {'calls':>6} {'grounded':>8} {'avg in':>9} {'avg out':>8} "
    f"{'avg think':>9} {'cached%':>7}"
)
for site, t in sorted(sites.items(), key=lambda item: -item[1]["prompt"]):
    calls = t["calls"] or 1
    cached = 100 * t["cached"] / t["prompt"] if t["prompt"] else 0
    print(
        f"{site:40} {t['calls']:>6} {t['grounded']:>8} {t['prompt'] // calls:>9} "
        f"{t['output'] // calls:>8} {t['thoughts'] // calls:>9} {cached:>6.0f}%"
    )
print("Token counts only; multiply by current per-token and per-grounded-request prices.")
