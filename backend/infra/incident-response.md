# Incident response

For a two-to-three person team running Bharat Sourcer on Cloud Run (`bharat-sourcer-web`,
`bharat-sourcer-integration`) in `hackathon-510415`, `asia-south1`. Alert-specific steps:
[runbooks](runbooks.md). Vulnerability reports: [SECURITY.md](../../SECURITY.md).

## Severity

| Level | Definition for this app | Examples | Response |
| --- | --- | --- | --- |
| SEV1 | Site or API down for most users, or user data exposed, or spend running away | Uptime check failing on <https://bharatsourcer.web.app>; share links or projects readable by others; a leaked Gemini key; spend on track to exceed the monthly budget within a day | Drop other work; owner involved now; status post within 30 min |
| SEV2 | A core flow broken or badly degraded for many users | Most new jobs fail; sourcing returns no offers anywhere; sign-in broken; queue stuck over 2 h; p95 latency over 5 s | Start within 1 h in working hours; status post if users notice |
| SEV3 | Partial or minor issue, workaround exists | One seller blocking; one source type failing; a single error burst without user impact; cost estimate drifting | Ticket; fix in normal work |

Unsure: pick the higher level and lower it later.

## Roles

One person can hold several roles; on a team this small, the person who acknowledges the
alert is **incident lead** until they hand it over.

| Role | Does | Default |
| --- | --- | --- |
| Incident lead | Decides severity and mitigation, keeps the timeline | Whoever acknowledged |
| Operator | Runs commands (rollback, pause, env changes) | Incident lead, or the backend owner |
| Communicator | Posts status and user updates | Repository owner for SEV1; lead otherwise |
| Owner | Approves data-incident notices, cost decisions and secret rotation | Repository owner (Dawn-Of-Justice) |

Frontend issues: involve the frontend teammate (`frontend/` is theirs).

## Steps

1. **Detect.** An alert (channel set in `setup_monitoring.py`), a user report or a failed
   deploy job. Note the time in UTC.
2. **Triage (5 min).** Open the alert's [runbook](runbooks.md) section; run its first-5-minute
   queries. Answer: what is broken, since when, for whom, and did a deploy just happen
   ([Actions](https://github.com/Dawn-Of-Justice/bharat-sourcer/actions),
   `gcloud run revisions list --service=bharat-sourcer-integration --region=asia-south1
   --project=hackathon-510415 --limit=5`). Set severity.
3. **Mitigate.** Stop the harm before finding the root cause. In order of preference:
   roll back the revision, pause queued dispatch, turn off the failing feature with its env
   flag, raise limits. Commands: [common mitigations](runbooks.md#common-mitigations).
4. **Communicate.** SEV1: status post within 30 min, then every 60 min and at resolution.
   SEV2: post if users are affected. Keep updates short: impact, what we did, next update
   time. Never post tokens, URLs with share tokens, emails or job contents.
5. **Resolve.** Confirm recovery on the dashboard for 15 min (same checks as the
   [release checklist](release-checklist.md#post-deploy)). Unpin traffic
   (`--to-latest`) once the fix is deployed. Resume paused queues and scheduler. Close the
   alert incident. Write the postmortem for every SEV1 and SEV2 within 5 working days.

## Where to post status

- Status page / channel: `<OWNER TO DECIDE: e.g. GitHub Discussions post, a pinned
  banner, or a team chat channel>`
- Internal coordination: `<OWNER TO DECIDE>`
- Alert notification channel: as configured by `setup_monitoring.py` (existing channel
  `projects/hackathon-510415/notificationChannels/16148970600683421140` is used by
  [queue-age-alert.json](queue-age-alert.json)).

## Postmortem template (blameless)

Describe systems and decisions, not people. Copy into a PR under `docs/` or an issue.

```markdown
# Postmortem: <short title> (<YYYY-MM-DD>, SEV<n>)

## Summary
Two or three sentences: what happened, impact, how it ended.

## Impact
- Duration (UTC start → end):
- Users / jobs affected (counts from logs, not guesses):
- Data exposed: yes / no (if yes, see data-incident addendum)
- Cost impact (estimate):

## Timeline (UTC)
| Time | Event |
| --- | --- |
| | First alert / report |
| | Acknowledged |
| | Mitigation applied |
| | Resolved |

## Root cause
The technical chain of causes. Which safeguards were missing or did not trigger.

## What went well / what was hard

## Action items
| Action | Type (prevent / detect / mitigate) | Owner | Due | Issue |
| --- | --- | --- | --- | --- |

## Error budget
SLO affected and budget consumed (see backend/infra/slos.md).
```

## Data-incident addendum

Use when user data may be exposed: projects, chat text, share links, account settings,
Firebase Auth records, logs with identifiers, or a leaked credential. Always SEV1.

1. **Contain.** Notify the owner immediately; do not discuss details in public channels.
   If a code path leaks data, roll back or disable the route now
   ([rollback](runbooks.md#roll-back-a-cloud-run-revision)).
2. **Revoke share links.** One project: the owner calls `DELETE /v1/jobs/{job_id}/share`.
   All projects (operator, owner approval, from `backend/` with ADC):

   ```python
   # Clears every active share link; links then return 404 SHARE_NOT_FOUND.
   from google.cloud import firestore
   from google.cloud.firestore_v1.base_query import FieldFilter

   db = firestore.Client(project="hackathon-510415", database="(default)")
   jobs = db.collection("backend_integration_jobs")
   count = 0
   for snap in jobs.where(filter=FieldFilter("share_token_hash", "!=", None)).stream():
       snap.reference.update({"share_token_hash": None, "shared_at": None})
       count += 1
   print("revoked", count)
   ```

   Run against a PITR clone first if unsure (`backups.md`, branch `ops/firestore-backups`).
3. **Rotate secrets** that could be exposed. Secret Manager secrets used by the services:

   | Secret | Used as | Set by | Rotate |
   | --- | --- | --- | --- |
   | `bharat-sourcer-gemini` | `BS_GEMINI_API_KEY` (API, pinned version) | `scripts/deploy_integration.py` | Create a new key, revoke the old one in the Google console, put the new key in `backend/.env`, run `deploy_integration.py` |
   | `bharat-sourcer-integration-key` | `BS_INTEGRATION_KEY` (API, pinned); `INTEGRATION_KEY` (web, `:latest`) | `deploy_integration.py` | Delete `backend/.data/integration-access.json`, run `deploy_integration.py` (new key), then redeploy `bharat-sourcer-web` so it reads `:latest` |
   | `bharat-sourcer-guest-session` | `BS_GUEST_SESSION_SECRET` (API) | `scripts/prepare_auth.py` | Add a version, update the binding; signs out every guest and resets IP-keyed usage counters |
   | `bharat-sourcer-youtube` | `BS_YOUTUBE_API_KEY` (API) | Manual ([README](README.md#youtube-data-api-key)) | New key in the console, add a version, update the binding |

   Generic rotation (value through stdin, never on the command line):

   ```sh
   gcloud secrets versions add SECRET --data-file=- --project=hackathon-510415   # paste, then Ctrl-D
   gcloud run services update bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415 --update-secrets=ENV_NAME=SECRET:NEW_VERSION
   gcloud secrets versions disable OLD_VERSION --secret=SECRET --project=hackathon-510415
   ```

   Disable old versions only after no serving revision pins them (rollback targets do).
   Workload Identity Federation for GitHub deploys has no stored key; if the deploy
   account is suspected, remove its bindings and review the IAM audit log.
4. **Scope.** Find what was accessed: Cloud Run request logs (paths, client IPs), app logs
   by `job_id`, and Admin Activity / Data Access audit logs. Record counts, not contents.
   Data stores and who can read them: [data inventory](data-inventory.md).
5. **Notify.** The owner decides on notifying affected users and any legal or regulatory
   notice (for example under India's DPDP Act). Do not contact users before that decision.
6. **Follow up.** Postmortem with the data-incident fields filled. Remember backups: deleted
   data stays in PITR (7 days) and weekly exports (30 days) until they age out.
