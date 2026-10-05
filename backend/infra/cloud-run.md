# Cloud Run integration deployment

Project `hackathon-510415`, region `asia-south1`, service `bharat-sourcer-integration`.
This is a team integration environment for the v0.17.2 backend.

## Current deployment: v0.17.2

5 October: authentication enabled on revision `bharat-sourcer-integration-00026-fzl`
at 100% traffic, explicitly ahead of the frontend deployment completing. Production
Firebase domain and CORS configured. Direct auth/session/cookie/usage/logout checks
passed with no model calls. Real Google sign-in and frontend proxy integration remain
to verify. Trusted proxy IP mode remains disabled pending proxy review.

Verified healthy in live Firestore mode with integration-key enforcement. Revoked
sessions and disabled/deleted account checks are deployed with authentication enabled.
The runtime service account has Firebase Auth Viewer access for account lookup.
Validation: 265 tests passed, two emulator tests skipped; lint, formatting and OpenAPI
checks passed. Live account revocation testing remains pending auth-enabled staging.

## Previous deployment: v0.17.1

Deployed and verified healthy in live Firestore mode. Personal usage counters and
accurate quota retry delays are available when authentication is enabled. The auth
flag remains disabled. Firebase Management and Identity Toolkit APIs are enabled;
the existing GCP project and `Bharat Sourcer Web` app are registered with Firebase.
Authentication is initialized and the Google provider is enabled, verified through
the Firebase API and console. SDK config is in ignored `.data/firebase-web-config.json`.
Production-domain authorization and an actual frontend sign-in test remain pending.

## Previous deployment: v0.17.0, authentication awaiting frontend integration

Deployed and verified 4 October 2026: healthy live Firestore mode, API v0.17.0,
and integration-key enforcement. Authentication remains disabled so the existing
frontend continues working. See the [frontend auth handoff](../../docs/contracts/authentication.md).

Validation: 254 tests passed, two emulator tests skipped; lint, formatting and
OpenAPI checks passed. A separate live Firestore check verified owner-scoped
pagination and atomic shared quotas across clients, then removed its synthetic
records. No Gemini or sourcing calls were made by these checks.

`scripts/prepare_auth.py` prepares a stable Secret Manager guest-session secret
and requests TTL cleanup for the deployed usage collection. It does not enable
authentication. Firebase Google provider configuration, frontend integration,
production CORS and staging login checks remain prerequisites for activation.

## Previous deployment: v0.16.1 with durable dispatch

The live release check confirmed API 0.16.1, healthy live Firestore mode, research
schemas and integration-access enforcement after the deployment resumed. This release
adds one bounded alternative-source search when the initial search provides neither
verified offers nor research evidence. Unreadable documents no longer consume the
readable-document review budget.

Validation: 238 tests passed, one Firestore emulator test skipped; lint, formatting
and OpenAPI checks passed. The controlled workflow covers confirmation, source recovery,
requirement edits, stale assessments and refresh-based reassessment without re-extraction.
A live switch search returned one verified offer and two research candidates with 11
quoted facts. That run succeeded on the first search; automatic follow-up recovery was
tested with controlled sources. Full browser integration still requires frontend controls.

## Previous v0.16 deployment

Deployed v0.16 on 4 Oct 2026. `scripts/check_release.py` verified live Firestore
health, API version 0.16.0, research and requirements schemas, and unauthenticated
job-creation rejection. The deployed frontend has not been updated for research cards.
See [the frontend research contract](../../docs/contracts/part-research.md).

Validation: 227 tests passed and one emulator test skipped; the subsequently added
frontend fixture check passed with all 36 focused research tests. Lint, formatting
and OpenAPI consistency passed. A local adapter call to live Gemini using the Quartz
Components LED page returned one candidate, four quoted facts and two questions.
The switch source check returned no usable evidence. This is not an end-to-end
cloud research-job verification or a guarantee of source coverage.

## Previous v0.15 deployment

Revision `bharat-sourcer-integration-00010-txx` serves API v0.15. Verified public
health reports live mode with Firestore storage. OpenAPI reports v0.15 and includes
optional `VerifiedOffer.image_url`. Live classifier checks rejected unrelated
requests and accepted a project-specific electronics question. A real Quartz
Components 5mm red LED variant was fetched and verified at INR 2.00. Local
validation: 192 tests passed, one Firestore emulator test skipped; lint, formatting
and OpenAPI consistency checks passed. The concurrent sourcing behavior was
verified with a controlled adapter and full API suite.

End-to-end frontend proxy check on 4 Oct created and confirmed a real YouTube job.
It completed with offers on all three lines (Pro Micro 1, TTP223 1, OLED 3).
This confirms the deployed request path and this sample search; it does not mean
every seller page can be read or every part has verified offers.

The v0.15 image URL field is available to the frontend at
`offers[].image_url`. A live seller search was not run as part of this deployment.

Revision `bharat-sourcer-integration-00005-6x4` serves the queued backend with
request-based billing, zero minimum instances, maximum one instance and a
1,800-second worker timeout. Cloud Tasks queue `bharat-sourcer` dispatches work;
Scheduler job `bharat-sourcer-reconcile` checks pending work every five minutes.
See [execution, recovery and frontend behavior](../../docs/contracts/queued-dispatch.md).

Verified after migration: live queued video extraction and queued Gemini chat,
Firestore persistence, HTTP SSE, CORS and integration access. The test job remains
awaiting confirmation; no paid seller search was started. Local suite: 181 passed,
1 emulator test skipped. Cloud Run CPU throttling is enabled and the old minimum
instance setting is removed. Earlier deployment records below are historical.

Previous revision `bharat-sourcer-integration-00004-fbh` was verified for:
health, v0.12 refresh-proposal schema, reading an existing persisted job, and decision
access checks. Local suite: 176 passed, 1 emulator test skipped; lint, formatting
and OpenAPI consistency passed. Approval execution was tested with controlled
adapters; this deployment check did not call Gemini or start paid seller searches.

Previous v0.11 revision `bharat-sourcer-integration-00003-2dm` was verified for:
health, v0.11 schema, pause/resume access and state guards, and reading a pre-v0.11
Firestore snapshot. No paid sourcing was started for this deployment check.
Local validation: full suite 170 passed/1 emulator test skipped, then all four
pause/resume tests passed after adding refresh-scope coverage. Lint, formatting
and OpenAPI consistency checks passed. Active pause/resume behavior was tested
with controlled sourcing adapters; it was not exercised against live sellers.

Base URL: `https://bharat-sourcer-integration-diahnrbuna-el.a.run.app`

API reference: [Swagger UI](https://bharat-sourcer-integration-diahnrbuna-el.a.run.app/docs).
Use `/health` for cloud liveness. `/healthz` remains a local alias but is intercepted by
Google's edge; [Cloud Run reserves some paths ending in z](https://docs.cloud.google.com/run/docs/known-issues#reserved_url_paths).

## Verified deployment — 3 Oct 2026

The previous revision `bharat-sourcer-integration-00002-vld` passed a remote smoke
test passed health, required team key, localhost:5173 and localhost:3000 CORS, live video
extraction, persisted Gemini chat, and an actual HTTP SSE snapshot. The test job remains
awaiting confirmation; no seller search was run. Local suite: 167 passed, 1 emulator
test skipped, followed by the passing targeted health-alias test. Frontend/browser UI
integration still needs the teammate's app; this test used an HTTP client.

Start with the [frontend quickstart](../../docs/contracts/frontend-quickstart.md).

## Runtime configuration

- One Uvicorn worker in a Python 3.12 container, 1 CPU, 512 MiB RAM.
- Minimum instances: 0; maximum: 1. CPU is allocated during requests, including
  Cloud Tasks worker requests. Scheduled reconciliation replaces background sweeps.
- Request timeout: 1,800 seconds; SSE streams end after about 60 seconds and reconnect.
- Firestore `(default)` database, separate collection `backend_integration_jobs`.
- Runtime identity `bharat-sourcer-api@hackathon-510415.iam.gserviceaccount.com`, with
  `roles/datastore.user`. This role is project-wide data access, not collection-scoped.
- Gemini and team integration keys are version-pinned Secret Manager environment bindings.
- Cloud Run permits invocation; application middleware requires `X-Integration-Key` on
  every `/v1/` request, plus the existing job token where applicable. Health and API docs
  are public. This shared development credential is not per-user authentication.
- CORS origins: localhost and 127.0.0.1, ports 5173 and 3000. Add exact hosted origins
  when the frontend has a deployment. CORS is not an authorization mechanism.

## Deploy

The deployment script is Windows-specific and uses the installed gcloud path. Run from
`backend/`, after tests and OpenAPI checks pass, using an authorized GCP identity:

```powershell
.venv/Scripts/python scripts/deploy_integration.py
```

It provisions a dedicated runtime identity, grants data access, uploads secrets through
stdin, builds the Dockerfile in Cloud Build and deploys Cloud Run. It reuses the local
integration key when `.data/integration-access.json` exists. Losing that local file and
rerunning rotates the key; coordinate that change with the frontend teammate.
The source upload uses an allowlist and excludes `.env`, `.data`, virtual environments,
tests, caches and local credentials. Do not add secrets to the container context.

Required services: Cloud Run, Cloud Build, Artifact Registry, Secret Manager and Firestore.
The deployer needs API enablement, build/deploy, service account and IAM administration
permissions. The script records the URL and integration key only in ignored
`.data/integration-access.json`. Share this credential privately for development.

## Verify

```powershell
.venv/Scripts/python scripts/check_deployed.py
```

This performs a live extraction and chat call (potential Gemini charges), checks CORS
and both access layers, then reads a real remote SSE snapshot. It leaves one integration
test job in Firestore and saves token-free results plus a separate ignored access file.
Do not commit those files. It does not confirm the BOM, source sellers or make purchases.

## Operations and remaining work

Use Cloud Run revisions to roll traffic back to a prior healthy revision if a deployment
fails verification. Inspect sanitized Cloud Logging errors for recovery or rule failures.
Keep old pinned secret versions while a revision may need rollback. There is no automated
retention or distributed abuse quota yet. Min/max settings bound instance count but do
not cap Gemini or Firestore charges. Shut down/delete the integration service when no
longer needed; do not leave it running unintentionally.

Cloud Run may terminate instances; Cloud Tasks retries and scheduled reconciliation
use leases and stored checkpoints for bounded workflow recovery. See the
[remaining feature roadmap](../../docs/contracts/backend-roadmap.md).

References: [Python on Cloud Run](https://docs.cloud.google.com/run/docs/tips/python)
and [background work and minimum instances](https://docs.cloud.google.com/run/docs/about-instance-autoscaling).
