# Workspace boundaries

- Backend code, dependencies, tests and runtime configuration belong in `backend/`.
- `frontend/` is owned by the frontend teammate. Do not scaffold or edit its app unless the task calls for frontend work.
- Shared API artifacts belong in `docs/contracts/`. Regenerate OpenAPI after changing public schemas or routes.
- Keep each application's installation and commands independent; do not add a root package manager project.
- Architecture documents describe the target system. `backend/README.md` and `docs/contracts/README.md` describe implemented behavior.
- Demo data must be labelled. Never present fixture prices, compatibility or evidence as verified results.
- Do not commit secrets, local environments, caches or generated runtime data.
