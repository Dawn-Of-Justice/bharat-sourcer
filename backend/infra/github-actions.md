# Backend GitHub deployment

Workflow: `.github/workflows/backend.yml` in `Dawn-Of-Justice/bharat-sourcer`.

- Changes under `backend/`, `docs/contracts/` or the workflow run lint, format,
  tests and OpenAPI consistency checks. Frontend-only pushes do not trigger it.
- Pull requests and non-main branches run checks only.
- Successful checks on a push to `main` deploy the backend. Manual workflow
  dispatch on `main` also checks and deploys.
- Deployments are serialized without cancelling an active deployment.
- GitHub builds the Dockerfile, pushes a commit-tagged image to Artifact Registry,
  resolves its digest, and deploys that immutable digest to Cloud Run.
- It verifies `/health` and that `/openapi.json` reports the checked-in version.
  It does not make paid Gemini calls. A failed smoke check fails the workflow;
  automatic rollback is not implemented.

## Authentication and permissions

GCP Workload Identity Federation exchanges GitHub's OIDC token for short-lived
credentials as `bharat-sourcer-deploy@hackathon-510415.iam.gserviceaccount.com`.
No service-account JSON key, Gemini key or integration key is stored in GitHub.
The workflow contains nonsecret project/provider identifiers directly.

The provider restricts repository name, owner, `refs/heads/main`, the exact
`backend.yml` workflow reference, and push/manual event types. GitHub CLI was not
authenticated during setup, so numeric repository/owner IDs could not be read;
add numeric claim restrictions when repository access is available. Renaming or
transferring this repository requires updating the provider conditions.

The deploy identity has Cloud Run Developer on this service, Artifact Registry
Writer on the existing image repository and Service Account User on the API
runtime account. It can change the deployed backend, so protect `main` and review
workflow changes. It has no direct secret-access grant.

Deploy preserves the existing runtime environment and pinned Secret Manager
bindings. It explicitly maintains request billing, minimum zero, maximum one and
the 1,800-second task timeout. Queue/Scheduler provisioning remains separate.

## Setup and first run

GCP provisioning is reproducible with `backend/scripts/setup_github_deploy.py`
from the backend directory using an authorized local gcloud identity.

Push/merge this workflow and backend changes to `main` to activate deployment.
Alternatively use GitHub → Actions → Backend → Run workflow after the workflow
is on `main`. No repository variables or secrets are required.

The local GitHub CLI needs `gh auth login` before this assistant can push or
inspect private Actions runs. The workflow has not been executed on GitHub during
setup; its first run must confirm federated access and deployment end to end.
