# Cloud Run integration deployment

Project `hackathon-510415`, region `asia-south1`, service `bharat-sourcer-integration`.
This is a team integration environment for the v0.10 backend, not a public launch.

Base URL: `https://bharat-sourcer-integration-diahnrbuna-el.a.run.app`

API reference: [Swagger UI](https://bharat-sourcer-integration-diahnrbuna-el.a.run.app/docs).
Use `/health` for cloud liveness. `/healthz` remains a local alias but is intercepted by
Google's edge; [Cloud Run reserves some paths ending in z](https://docs.cloud.google.com/run/docs/known-issues#reserved_url_paths).

## Verified deployment — 3 Oct 2026

Revision `bharat-sourcer-integration-00002-vld` serves 100% of traffic. The remote smoke
test passed health, required team key, localhost:5173 and localhost:3000 CORS, live video
extraction, persisted Gemini chat, and an actual HTTP SSE snapshot. The test job remains
awaiting confirmation; no seller search was run. Local suite: 167 passed, 1 emulator
test skipped, followed by the passing targeted health-alias test. Frontend/browser UI
integration still needs the teammate's app; this test used an HTTP client.

Start with the [frontend quickstart](../../docs/contracts/frontend-quickstart.md).

## Runtime configuration

- One Uvicorn worker in a Python 3.12 container, 1 CPU, 512 MiB RAM.
- Minimum and maximum instances: 1. CPU stays allocated outside requests so the current
  background tasks and recovery sweeps can run. This incurs idle-instance charges.
- Request timeout: 300 seconds; SSE streams end after about 60 seconds and reconnect.
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

Cloud Run may terminate instances; leases and stored checkpoints handle bounded recovery,
but this is not durable task dispatch. See the [remaining feature roadmap](../../docs/contracts/backend-roadmap.md).

References: [Python on Cloud Run](https://docs.cloud.google.com/run/docs/tips/python)
and [background work and minimum instances](https://docs.cloud.google.com/run/docs/about-instance-autoscaling).
