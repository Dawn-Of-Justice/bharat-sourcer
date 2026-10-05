# GitHub deployments

Workflows:

- `.github/workflows/backend.yml`
- `.github/workflows/frontend.yml`

Both workflows run checks on pull requests and non-main branches, then deploy on
pushes to `main` (or manual dispatch) after checks pass.

## Backend workflow

- Triggered by changes in `backend/`, `docs/contracts/`, or
  `.github/workflows/backend.yml`.
- Checks: `ruff check`, `ruff format --check`, `pytest`, and OpenAPI consistency.
- Deployment: builds `backend/Dockerfile`, pushes a commit-tagged image to the
  `cloud-run-source-deploy` Artifact Registry repository, and runs
  `gcloud run services update --image` on Cloud Run service `bharat-sourcer-integration`
  (`asia-south1`). Only the image changes: environment variables, pinned Secret Manager
  bindings, runtime identity, scaling and Cloud Tasks settings remain as configured by
  `scripts/deploy_integration.py`. The job then checks that the service runs the pushed
  image and that `/openapi.json` reports the `pyproject.toml` version.
- Until 5 October 2026 this job targeted a GKE cluster that was never created (the
  Kubernetes Engine API is disabled), so every deploy run failed and releases were made
  manually with `deploy_integration.py`. Use that script only for configuration changes
  (new env vars or secret versions); routine code releases go through `main`.

## Frontend workflow

- Triggered by changes in `frontend/` or `.github/workflows/frontend.yml`.
- Checks: `npm ci`, `npm run test:server`, and `npm run build`.
- Deployment: builds `frontend/Dockerfile`, pushes a commit-tagged Artifact
  Registry image, updates the frontend Kubernetes deployment image in GKE, and
  waits for rollout completion.

## Authentication and permissions

GCP Workload Identity Federation exchanges GitHub's OIDC token for short-lived
credentials as `bharat-sourcer-deploy@hackathon-510415.iam.gserviceaccount.com`.
No service-account JSON key, Gemini key or integration key is stored in GitHub.
The workflow contains nonsecret project/provider identifiers directly.

The backend deploy identity needs `roles/run.developer` on the service,
`roles/artifactregistry.writer` on `cloud-run-source-deploy`, and
`roles/iam.serviceAccountUser` on runtime identity `bharat-sourcer-api`; all are granted
by `scripts/setup_github_deploy.py`. The frontend workflow still targets GKE and needs
the same migration (owned by the frontend teammate).

## Setup and first run

GCP provisioning is reproducible with `backend/scripts/setup_github_deploy.py`
from the backend directory using an authorized local gcloud identity.

Push/merge the workflow changes to `main` to activate deployment. Alternatively,
run each workflow from GitHub → Actions after the workflow is on `main`.

The local GitHub CLI needs `gh auth login` before this assistant can push or
inspect private Actions runs. The workflow has not been executed on GitHub during
setup; its first run must confirm federated access and deployment end to end.
