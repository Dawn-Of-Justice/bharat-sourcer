"""Summarise GEMINI_USAGE and GEMINI_CACHE_HIT log lines per call site, with estimated USD.

Run from backend/ with an identity that can read Cloud Logging:
    python scripts/usage_report.py --days 7
or offline on saved lines (one log line or JSON payload per line):
    python scripts/usage_report.py --file usage.log
Limit to one job with --job JOB_ID. Estimates use the dated price table in
bharat_sourcer/config.py and price grounding queries as if the free tier were used up.
"""

import argparse
import json
import subprocess
from collections import defaultdict

from bharat_sourcer.config import GEMINI_PRICES_CHECKED
from bharat_sourcer.usage import estimate_usd

# Which call site a cache namespace saves when it hits; free namespaces save fetches only.
SAVED_SITE = {"discovery": "discovery", "judge": "judge", "research": "research"}


def payload(line: str, marker: str) -> dict | None:
    if marker not in line:
        return None
    try:
        fields = json.loads(line.split(marker, 1)[1])
    except ValueError:
        return None
    return fields if isinstance(fields, dict) else None


def summarise(lines: list[str], job: str | None = None) -> str:
    sites = defaultdict(lambda: defaultdict(float))
    by_site_usd, by_site_calls = defaultdict(float), defaultdict(int)
    jobs, hits = set(), defaultdict(int)
    for line in lines:
        fields = payload(line, "GEMINI_USAGE")
        if fields is not None:
            if job and fields.get("job_id") != job:
                continue
            usd = fields.get("usd_est")
            if usd is None:  # lines logged before v0.20 cost accounting
                usd = estimate_usd(str(fields.get("model")), fields)
            totals = sites[f"{fields.get('site')} ({fields.get('model')})"]
            totals["calls"] += 1
            totals["grounded"] += bool(fields.get("grounded"))
            totals["usd"] += usd
            for key in ("prompt", "output", "thoughts", "cached", "tool_prompt", "search_queries"):
                totals[key] += int(fields.get(key) or 0)
            by_site_usd[str(fields.get("site"))] += usd
            by_site_calls[str(fields.get("site"))] += 1
            if fields.get("job_id"):
                jobs.add(fields["job_id"])
            continue
        fields = payload(line, "GEMINI_CACHE_HIT")
        if fields is not None and (not job or fields.get("job_id") == job):
            hits[str(fields.get("namespace"))] += 1

    out = [
        f"{'site':40} {'calls':>6} {'grounded':>8} {'avg in':>9} {'avg out':>8} "
        f"{'avg think':>9} {'cached%':>7} {'queries':>7} {'est USD':>9}"
    ]
    for site, t in sorted(sites.items(), key=lambda item: -item[1]["usd"]):
        calls = int(t["calls"]) or 1
        cached = 100 * t["cached"] / t["prompt"] if t["prompt"] else 0
        out.append(
            f"{site:40} {int(t['calls']):>6} {int(t['grounded']):>8} "
            f"{int(t['prompt']) // calls:>9} {int(t['output']) // calls:>8} "
            f"{int(t['thoughts']) // calls:>9} {cached:>6.0f}% {int(t['search_queries']):>7} "
            f"{t['usd']:>9.4f}"
        )
    total = sum(by_site_usd.values())
    out.append(f"{'total':40} {sum(by_site_calls.values()):>6} {'':>53} {total:>9.4f}")
    if jobs:
        out.append(
            f"Attributed jobs: {len(jobs)}; average est. USD per job {total / len(jobs):.4f}"
        )
    if hits:
        out.append("")
        out.append(f"{'cache namespace':40} {'hits':>6} {'est. USD saved':>15}")
        for namespace, count in sorted(hits.items()):
            site = SAVED_SITE.get(namespace)
            average = by_site_usd[site] / by_site_calls[site] if site and by_site_calls[site] else 0
            out.append(f"{namespace:40} {count:>6} {count * average:>15.4f}")
    out.append(
        f"Estimates only (prices checked {GEMINI_PRICES_CHECKED}; free grounding tier ignored)."
    )
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--file")
    parser.add_argument("--job")
    parser.add_argument("--project", default="hackathon-510415")
    parser.add_argument("--service", default="bharat-sourcer-integration")
    args = parser.parse_args()

    if args.file:
        with open(args.file, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    else:
        query = (
            f'resource.labels.service_name="{args.service}" AND '
            '(textPayload:"GEMINI_USAGE" OR textPayload:"GEMINI_CACHE_HIT")'
        )
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
    print(summarise(lines, args.job))


if __name__ == "__main__":
    main()
