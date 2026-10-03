# Connect the local frontend

v0.12 adds [chat refresh approval controls](chat-actions.md); approval uses the
existing message decision endpoint and sourcing progress uses existing SSE snapshots.

For v0.11 sourcing controls, see [pause/resume](pause-resume.md). Render the new
`paused` status and distinguish a pending pause from an acknowledged pause.

## Connection

Base URL: `https://bharat-sourcer-integration-diahnrbuna-el.a.run.app`

- Health: `GET /health` (public).
- API explorer: `/docs`; generated schema: `/openapi.json` (public).
- Allowed browser origins: localhost and 127.0.0.1 on ports **5173** and **3000**.
- All `/v1/` calls require the team's `X-Integration-Key`.
- Job reads and mutations also require the job's `X-Job-Token` returned at creation.

The backend owner has the shared development key in the ignored local file
`backend/.data/integration-access.json`. Share that value privately with the teammate;
never commit it. It is a development access key, not the Gemini key. Browser-held keys
are visible to users of that browser; this arrangement is for team integration only.

For a Vite frontend, put this in its own ignored `.env.local` (do not add it to the repo):

```dotenv
VITE_API_BASE_URL=https://bharat-sourcer-integration-diahnrbuna-el.a.run.app
VITE_INTEGRATION_KEY=<privately-shared-team-key>
```

## Minimal client example

```js
const base = import.meta.env.VITE_API_BASE_URL;
const teamKey = import.meta.env.VITE_INTEGRATION_KEY;

async function api(path, { method = "GET", body, jobToken } = {}) {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: {
      "X-Integration-Key": teamKey,
      ...(jobToken ? { "X-Job-Token": jobToken } : {}),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error?.message || `HTTP ${response.status}`);
  return result;
}

const created = await api("/v1/jobs", {
  method: "POST",
  body: { url: "https://www.youtube.com/shorts/En4KD0c3XXs" },
});
// Retain created.job_token privately for this job. Never put it in URLs or logs.
const path = `/v1/jobs/${created.job_id}`;
const job = await api(path, { jobToken: created.job_token });

await api(`${path}/messages`, {
  method: "POST",
  jobToken: created.job_token,
  body: { message_id: crypto.randomUUID(), text: "What remains uncertain in this BOM?" },
});
```

Live creation and chat may incur charges. For rendering the current state, use the
[conversation guide's SSE client](conversation.md#receive-live-snapshots), passing
`integrationKey: teamKey`. Polling is also supported. Keep messages visible after job
status becomes `done`: chat has its own lifecycle. Generation does not stream tokens yet.

## First integration acceptance check

1. Create a job; display extracting state, then editable BOM and model-reported evidence.
2. Ask a question; show queued/thinking and then the persisted answer with line references.
3. Request a draft edit; show a review card and accept/reject actions.
4. Accept an edit and verify the BOM changes but remains awaiting confirmation.
5. Explicitly confirm the BOM; stream per-line sourcing progress and unknown specs.
6. Handle errors: 401 means team key missing/incorrect; 404 means job/token unavailable;
   409 is a state conflict or limit; 422 needs input correction; 503 is service/storage trouble.
7. Reconnect the stream and avoid duplicating messages by using their message IDs.

See [all implemented routes](README.md), [conversation integration](conversation.md),
and [agreed remaining features](backend-roadmap.md). The backend deployment does not
modify or scaffold the teammate's frontend.
