# Frontend workspace

Reserved for the frontend teammate's React + TypeScript app. Choose and maintain frontend tooling here independently of Python.

## Backend integration

- Local API: `http://127.0.0.1:8000`
- Interactive API reference: `http://127.0.0.1:8000/docs`
- Shared contract and workflow: [docs/contracts](../docs/contracts/README.md)
- Generated schema: [openapi.json](../docs/contracts/openapi.json)
- Backend startup: [backend/README.md](../backend/README.md)

The backend allows `http://localhost:5173` and `http://127.0.0.1:5173` by default. Set your own frontend API base URL to the backend origin and call `/v1/...`.

For this first local milestone, poll job snapshots. Firestore listeners are part of the planned cloud integration and are not implemented yet. Keep transport access in one frontend API module so it can be changed later.
