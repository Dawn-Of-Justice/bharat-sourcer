# Cost guardrails

What caps spend on `hackathon-510415`, and how to cut it fast. Background:
[Gemini cost](gemini-cost.md), `docs/contracts/cost-controls.md`. Alert response:
[gemini-spend runbook](runbooks.md#gemini-spend).

## Billing budget

- Budget: **2,000 INR / month** (default), created by `backend/scripts/setup_monitoring.py`
  (branch `ops/monitoring`). A budget alerts; it does not stop spending.
- Thresholds and recipients: as set by that script (see `backend/infra/monitoring.md`).
- Check: `gcloud billing budgets list --billing-account=BILLING_ACCOUNT_ID` (find the id
  with `gcloud billing projects describe hackathon-510415`). Console:
  <https://console.cloud.google.com/billing?project=hackathon-510415>.

## Gemini spend alert

- Log-based estimate from `GEMINI_USAGE` `usd_est` (dated price table in `config.py`,
  grounding queries counted at $0.014 without the free tier, so an upper bound). It is
  faster than billing data, which lags by hours.
- Threshold: as set in `setup_monitoring.py`.
- Report: `.venv/Scripts/python scripts/usage_report.py --days 7` from `backend/`
  (`--job JOB_ID` for one job).
- Prices double for `gemini-3.8-flash` on 2027-01-01 (already in the price table).

## Max instances

| Service | Max instances (live, 17 Oct 2026) | Min instances | Notes |
| --- | --- | --- | --- |
| `bharat-sourcer-integration` | Revision template: 3. Service-level `run.googleapis.com/maxScale`: 1 | 0 (no min-scale annotation found) | 1 vCPU, 512 MiB, concurrency 20, timeout 1,800 s, CPU only during requests |
| `bharat-sourcer-web` | Revision template: 1. Service-level: 20 | 0 | 1 vCPU, 512 MiB, concurrency 20, timeout 120 s (deploy script) |
| Compile jobs `bharat-sourcer-compile-{avr,esp32,esp8266,rp2040}` | One task per run; `BS_COMPILE_DAILY_LIMIT` 100/day | n/a | Bill only while running |
| Cloud Tasks `bharat-sourcer` | 2 concurrent, 2/s dispatch | n/a | Bounds parallel Gemini work |

The service-level and template values disagree, and min instances is 0 although the
[README](README.md#demo-and-judging-scaling-approved-7-october-2026) plans 1 until
6 November 2026. Owner to confirm intended values. Check:

```sh
gcloud run services describe bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415 --format='value(metadata.annotations,spec.template.metadata.annotations)'
```

`scripts/deploy_integration.py` deploys with `--max-instances=1` and min 0 (queued mode);
`frontend/scripts/deploy_cloud_run.ps1` with max 1, min 0. Re-apply scaling after running
either. Image deploys from GitHub Actions keep scaling. Each warm minimum instance costs
about $0.33/day.

## Per-user quotas

Defaults from `config.py` and `access.py`; production may override them through env vars
(check with `gcloud run services describe ... --format='yaml(spec.template.spec.containers[0].env)'`).
Quotas apply when auth is enabled (`BS_AUTH_ENABLED`). Counters live in
`backend_integration_jobs_usage` (UTC day windows).

| Limit | Default | Setting |
| --- | --- | --- |
| Actions per guest per day | 5 | `BS_GUEST_DAILY_ACTIONS` |
| Actions per account per day | 40 | `BS_ACCOUNT_DAILY_ACTIONS` |
| Actions per IP per day | 100 | `BS_IP_DAILY_ACTIONS` |
| Actions across everyone per day | 1,000 | `BS_GLOBAL_DAILY_ACTIONS` |
| Actions per identity per minute | 5 | hard-coded (`access.py`) |
| New projects per day | guest 1, account 5 | hard-coded |
| Guest sessions per IP per day / global | 10 / 1,000 | hard-coded |
| Project claims per account per minute | 20 | `CLAIMS_PER_MINUTE` |
| Parts sourced per project | guest 3, account 30 | `BS_GUEST_PART_LIMIT`, `BS_SOURCING_MAX_PARTS` |
| Gemini budget per sourcing run | $0.25 | `BS_JOB_GEMINI_BUDGET_USD` |
| Seller refresh batches per project | 2 | `Job.refresh_limit` (exempt: `BS_REFRESH_UNLIMITED_UIDS`) |
| Nearby markets per owner / global per day | 5 / 50 | `BS_MARKETS_DAILY_LIMIT`, `BS_MARKETS_GLOBAL_DAILY_LIMIT` |
| Explain aloud / clip zoom / parts scan per owner per day | 10 / 10 / 5 (all off by default) | `BS_EXPLAIN_DAILY_LIMIT`, `BS_ZOOM_DAILY_LIMIT`, `BS_SCAN_DAILY_LIMIT` |
| Extras across everyone per day | 200 | `BS_EXTRAS_GLOBAL_DAILY_LIMIT` |
| Part images per day | 30 (generation off) | `BS_IMAGE_DAILY_LIMIT` |
| AI code patches / compile checks per day | 50 / 100 | `BS_CODE_ADAPT_DAILY_LIMIT`, `BS_COMPILE_DAILY_LIMIT` |

## Cut cost fast

All are env changes on the API (each creates a revision in about a minute; image deploys
keep them; `deploy_integration.py` drops ones it does not manage). Use the
`^@^` delimiter for values containing commas ([raise limits](runbooks.md#raise-limits)).

```sh
S="bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415"
# 1. Stop all new paid work now (saved jobs wait)
gcloud tasks queues pause bharat-sourcer --location=asia-south1 --project=hackathon-510415
gcloud scheduler jobs pause bharat-sourcer-reconcile --location=asia-south1 --project=hackathon-510415
# 2. Lower the global daily cap and the per-run budget
gcloud run services update $S --update-env-vars=BS_GLOBAL_DAILY_ACTIONS=100,BS_JOB_GEMINI_BUDGET_USD=0.10
# 3. Turn off optional Gemini stages
gcloud run services update $S --update-env-vars=BS_OVERVIEW_ENABLED=false,BS_RESEARCH_FOLLOWUP_ENABLED=false,BS_MARKETS_ENABLED=false,BS_FABRICATION_ENABLED=false,BS_BUILD_GUIDE_ENABLED=false
# 4. Cheaper models for heavy sites
gcloud run services update $S '--update-env-vars=^@^BS_GEMINI_SITE_MODELS={"research":"gemini-3.1-flash-lite","buyer":"gemini-3.1-flash-lite","chat_reply":"gemini-3.1-flash-lite"}'
# 5. Stop sourcing entirely (extraction still works)
gcloud run services update $S --update-env-vars=BS_SOURCING_ENABLED=false
# 6. Drop warm instances and compile runs
gcloud run services update $S --min-instances=0 --update-env-vars=BS_COMPILE_BACKEND=none
gcloud run services update bharat-sourcer-web --region=asia-south1 --project=hackathon-510415 --min-instances=0
# Last resort: revoke the Gemini key in the Google console (all AI stops; Vertex sites keep billing to the project)
```

Order of preference: 2 and 3 (users keep core flows), then 1 (everyone waits), then 5.
Keep `BS_CACHE_ENABLED=true`: the cache is what keeps repeat parts cheap. Model choice per
site trades quality: check `gemini-cost.md` before leaving step 4 in place. Undo each step
when the spike ends and record what changed in the incident timeline.
