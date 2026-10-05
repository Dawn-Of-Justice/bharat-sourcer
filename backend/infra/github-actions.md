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
- Deployment: builds `backend/Dockerfile`, pushes a commit-tagged Artifact Registry
  image, updates the backend Kubernetes deployment image in GKE, and waits for
  rollout completion.

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

The deploy identity must be able to push Artifact Registry images and update
Kubernetes Deployments in the target GKE cluster/namespace.

## Setup and first run

GCP provisioning is reproducible with `backend/scripts/setup_github_deploy.py`
from the backend directory using an authorized local gcloud identity.

Push/merge the workflow changes to `main` to activate deployment. Alternatively,
run each workflow from GitHub → Actions after the workflow is on `main`.

The local GitHub CLI needs `gh auth login` before this assistant can push or
inspect private Actions runs. The workflow has not been executed on GitHub during
setup; its first run must confirm federated access and deployment end to end.
