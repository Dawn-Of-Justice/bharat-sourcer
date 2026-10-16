# Release checklist

Merging to `main` deploys automatically ([GitHub deployments](github-actions.md)):

- `backend/**` or `docs/contracts/**` changes: `.github/workflows/backend.yml` checks, builds
  and runs `gcloud run services update bharat-sourcer-integration --image ...`, then checks
  the image and the `/openapi.json` version. `backend/compile/**` also rebuilds the compile
  runner images.
- `frontend/**` changes: `.github/workflows/frontend.yml` builds and updates
  `bharat-sourcer-web`, then checks `/` answers.
- Image deploys change only the image. Env vars, secrets, scaling and queue settings stay.
  Config changes go through `scripts/deploy_integration.py` (backend) or
  `frontend/scripts/deploy_cloud_run.ps1` (web), which **reset scaling** (see
  [cost guardrails](cost-guardrails.md#max-instances)).

## Pre-deploy (before merging)

- [ ] CI green on the PR (backend: ruff, mypy, pytest, pip-audit, OpenAPI check;
      frontend: lint, format, build, server and preview tests).
- [ ] `backend/pyproject.toml` version bumped for backend releases (the deploy job compares
      it with the live `/openapi.json`).
- [ ] Public schema or route change: `python scripts/export_openapi.py` run and
      `docs/contracts/openapi.json` committed; contract doc updated.
- [ ] Error-budget state allows this change ([policy](slos.md#error-budget-policy)).
- [ ] New env var or secret: set it on the service **before** merging code that needs it
      (`gcloud run services update ... --update-env-vars` / `--update-secrets`), or make the
      code default safely when it is missing.
- [ ] New Gemini call site or model: cost estimated (`gemini-cost.md`), behind a flag that
      can be turned off without a deploy.
- [ ] Firestore: new collection group with `expires_at` has a TTL policy plan
      ([README](README.md#firestore-ttl-policies)); no change makes job documents approach
      800 KB.
- [ ] Traffic is not pinned to an old revision (otherwise the new revision gets no traffic
      and the deploy check fails):

      ```sh
      gcloud run services describe bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415 --format='yaml(status.traffic)'
      ```

- [ ] Note the current serving revisions (the rollback targets):

      ```sh
      gcloud run revisions list --service=bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415 --limit=3
      gcloud run revisions list --service=bharat-sourcer-web --region=asia-south1 --project=hackathon-510415 --limit=3
      ```

- [ ] Avoid merging while long jobs run if the change touches leases or dispatch
      (a new revision can interrupt work; recovery runs once per job).

## Post-deploy

- [ ] Deploy job succeeded in [Actions](https://github.com/Dawn-Of-Justice/bharat-sourcer/actions)
      (image matches, version matches).
- [ ] Smoke test:

      ```sh
      curl -fsS https://bharat-sourcer-integration-diahnrbuna-el.a.run.app/health
      curl -fsS https://bharatsourcer.web.app/api/health
      curl -fsS -o /dev/null -w '%{http_code}\n' https://bharatsourcer.web.app/
      curl -fsS https://bharat-sourcer-integration-diahnrbuna-el.a.run.app/openapi.json | python -c "import json,sys; print(json.load(sys.stdin)['info']['version'])"
      ```

      `/health` reports `mode` and `storage`; expect `live` and `firestore`. Use `/health`
      on the `run.app` URL (`/healthz` is intercepted by Google's edge there; the web proxy
      maps `/api/healthz` to `/health`).
      From `backend/`, read-only, no model calls: `.venv/Scripts/python scripts/check_release.py`
      (checks it against the backend's expected schema; its schema assertions may lag the
      current release).
- [ ] Demo job: production runs with `BS_DEMO_MODE=false`, so there is no fixture job in
      production. Run one small real job through <https://bharatsourcer.web.app> as a guest
      with a public project you know (for example a small GitHub repository), confirm it
      reaches the parts review, then stop before sourcing. This makes a few Gemini calls
      (cents). For a fixture-only check, run the backend locally with the default
      `BS_DEMO_MODE=true` and label results as demo data.
- [ ] Watch the dashboard for 15 minutes
      ([dashboards](https://console.cloud.google.com/monitoring/dashboards?project=hackathon-510415)):
      5xx rate, p95 latency, instance count, `JOB_FINISHED` failures, `GEMINI_CALL` errors,
      error log volume. Compare with the hour before the deploy.

      ```sh
      gcloud logging read 'resource.type="cloud_run_revision" AND severity>=ERROR' --project=hackathon-510415 --freshness=15m --limit=30 --format='table(timestamp,resource.labels.revision_name,jsonPayload.event,jsonPayload.type)'
      ```

- [ ] No new alert incident opened
      ([alerting](https://console.cloud.google.com/monitoring/alerting?project=hackathon-510415)).

## Rollback

Trigger: any smoke test fails, a new error class appears on the new revision, or an alert
fires in the watch window. Roll back first, investigate second.

```sh
gcloud run revisions list --service=bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415 --limit=5
gcloud run services update-traffic bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415 --to-revisions=PREVIOUS_REVISION=100
# web: same commands with bharat-sourcer-web
```

Then:

1. Re-run the smoke test against the old revision.
2. Revert the PR on `main` (`git revert <merge-commit>`, PR, merge). Its deploy creates a
   new revision that gets no traffic while pinned.
3. Return traffic to the latest revision once it is the revert or a fix:
   `gcloud run services update-traffic bharat-sourcer-integration --region=asia-south1 --project=hackathon-510415 --to-latest`.
4. Keep old Secret Manager versions while any rollback target pins them.
5. Do not roll back past the v0.13 queued-dispatch migration
   (`docs/contracts/queued-dispatch.md`).

Details: [runbooks](runbooks.md#roll-back-a-cloud-run-revision).
