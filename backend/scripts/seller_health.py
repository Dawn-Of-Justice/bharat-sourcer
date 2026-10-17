"""Summarize exported Cloud Logging JSON or local JSONL, without exposing queries/URLs.

python scripts/seller_health.py events.json --output seller-health.json
"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def summarize(events):
    outcomes = defaultdict(Counter)
    durations = defaultdict(list)
    for entry in events:
        event = entry.get("jsonPayload", entry)
        if event.get("event") not in {"SELLER_FETCH", "SELLER_SEARCH_RESULT", "SELLER_PROVIDER"}:
            continue
        host = str(event.get("host") or event.get("provider") or "unknown")
        key = (event["event"], host)
        outcomes[key][str(event.get("outcome", "unknown"))] += 1
        duration = event.get("duration_ms")
        if isinstance(duration, (int, float)) and duration >= 0:
            durations[key].append(duration)
    rows = []
    for (event, host), counts in sorted(outcomes.items()):
        values = sorted(durations[event, host])
        rows.append(
            {
                "event": event,
                "host": host,
                "count": sum(counts.values()),
                "outcomes": dict(counts),
                "p95_ms": values[min(len(values) - 1, int(len(values) * 0.95))] if values else None,
            }
        )
    return {"rows": rows, "note": "Operational outcomes, not BOM accuracy or verified coverage."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.input.read_text(encoding="utf-8-sig").strip()
    events = (
        json.loads(raw)
        if raw.startswith("[")
        else [json.loads(line) for line in raw.splitlines() if line.strip()]
    )
    result = json.dumps(summarize(events), indent=2)
    if args.output:
        args.output.write_text(result + "\n", encoding="utf-8")
    else:
        print(result)


if __name__ == "__main__":
    main()
