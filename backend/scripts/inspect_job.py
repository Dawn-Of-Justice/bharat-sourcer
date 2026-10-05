"""Read one project's sourcing diagnostics without exposing ownership or credentials."""

import argparse
import json

from bharat_sourcer.storage import FirestoreJobStore

parser = argparse.ArgumentParser()
parser.add_argument("job_id")
args = parser.parse_args()
record = FirestoreJobStore("hackathon-510415", collection="backend_integration_jobs").get(
    args.job_id
)
if record is None:
    raise SystemExit("Job not found")
job = record.job.model_dump(mode="json")
print(
    json.dumps(
        {
            **{key: job.get(key) for key in ("status", "created_at", "updated_at", "error")},
            "lines": [
                {
                    "line_id": line["item"]["line_id"],
                    "part": line["item"]["raw_name"],
                    "status": line["sourcing_status"],
                    "error": line["sourcing_error"],
                    "offers": len(line["offers"]),
                    "research": line.get("research", {}).get("summary")
                    if line.get("research")
                    else None,
                }
                for line in (job.get("report") or {}).get("lines", [])
            ],
        },
        indent=2,
    )
)
