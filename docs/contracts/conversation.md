# Conversation integration — v0.9

The project conversation sits beside the bill of materials (BOM). Users can ask about
saved parts and evidence, review proposed draft edits, and accept or reject them.
The backend owns the conversation and job state. Render snapshots from the backend;
do not infer that an assistant message has changed the BOM.

Use [the generated OpenAPI contract](openapi.json) for exact request and response types.
The existing extraction, confirmation, sourcing, selection, refresh and spec-update
endpoints remain available; see [the API guide](README.md).

## UI flow

1. Create a job and retain its private token as described in the API guide.
2. Show the BOM and a chat panel together. Open the snapshot stream below, or poll the
   existing job GET endpoint. Keep watching after extraction finishes: chat has its
   own state, separate from the extraction/sourcing job status.
3. Submit a question with a fresh UUID. Render persisted user messages and a waiting
   indicator while `chat_state` is `queued` or `thinking`. Disable another send while
   a turn is active. Other backend changes may arrive while the answer is being prepared.
4. Render the assistant's text as text or sanitized Markdown. Resolve each
   `cited_line_ids` entry to the matching BOM line and let users inspect its evidence.
   A line reference identifies context; it does not independently verify the claim.
5. If an assistant message contains a pending proposal, show the proposed operations
   with **Accept edits** and **Reject** buttons. Explain quantities, ownership and spec
   changes before acceptance. Refresh the UI from the returned snapshot.
6. Keep **Confirm BOM and find offers** as a separate explicit action. Accepting a
   proposal edits the draft; it does not confirm the BOM or start a seller search.

Read-only questions work in every job state. Proposals can change the draft only while
the job is `awaiting_confirmation`. A question such as “What does this board do?” does
not itself authorize a change.

## Send a message

```http
POST /v1/jobs/{job_id}/messages
X-Job-Token: <private job token>
Content-Type: application/json

{"message_id":"2c174fbe-268f-46b2-85d5-c233b785cdb9","text":"I already have the board. Can you update the draft?"}
```

- `message_id`: client-generated UUID; retain it when retrying an uncertain submission.
- `text`: 1–4,000 characters.
- Response: HTTP 202 with the current job snapshot. Generation runs in the background.
- At most 20 user turns per job, with one active turn at a time.
- Retrying the same UUID and text returns the existing state without another generation.
  Reusing that UUID with different text returns 409. A genuinely new question gets a new UUID.
- All conversation, decision and streaming calls require `X-Job-Token`. Missing or
  incorrect tokens return 404. Do not put tokens in URLs, logs or analytics.

Job snapshots include `chat_state` (`idle`, `queued`, `thinking` or `failed`) and
`messages`. Each persisted message contains:

| Field | Use |
| --- | --- |
| `message_id` | Stable message identifier |
| `role` | `user` or `assistant` |
| `text` | Message content |
| `created_at` | Timestamp |
| `cited_line_ids` | References to BOM lines used in the answer |
| `proposal` | Nullable proposed draft edits with a decision status |

A proposal uses the existing confirmation edit operations: `add`, `update`, `remove`
and `have_it`. Its status is `pending`, `accepted` or `rejected`. Treat
`base_fingerprint` as opaque revision metadata; send the decision against the assistant
message ID.

## Decide on proposed edits

```http
POST /v1/jobs/{job_id}/messages/{message_id}/decision
X-Job-Token: <private job token>
Content-Type: application/json

{"action":"accept"}
```

Use `{"action":"reject"}` to dismiss the proposal. The response is the updated job.
Acceptance applies the draft edits atomically. The backend validates the operation and
checks that the draft still matches the proposal's base. Invalid or stale proposals
return 409 or 422; fetch the latest job and explain that the proposal could not be applied.
Do not silently recreate a stale proposal against a different BOM.

## Receive live snapshots

`GET /v1/jobs/{job_id}/stream` returns Server-Sent Events (SSE):

- `snapshot` events contain the complete job as JSON, including chat and progress.
- Heartbeats keep the connection active; they are not conversation messages.
- `stream_error` carries `{"code":"STREAM_UNAVAILABLE"}` before a storage failure closes
  the stream. Show a connection warning and reconnect; this is not a job failure.
- Connections are bounded to approximately 60 seconds. Reconnect while the view is open.
- This streams saved state, not individual model tokens. An assistant answer appears
  once it has been validated and persisted.

Use `fetch`, because the browser's native `EventSource` cannot supply the required
custom authentication header. Replace the current UI state with each snapshot rather
than appending all of its messages again. Use message IDs as component keys.

The following browser example handles fragmented UTF-8, events split across network
chunks and multi-line SSE data. It aborts reads and reconnect delays when the view closes.
The callbacks should update UI state without logging private tokens or message content.

```js
async function watchJob({ baseUrl, jobId, token, signal, onSnapshot, onError }) {
  const url = `${baseUrl}/v1/jobs/${encodeURIComponent(jobId)}/stream`;
  let backoff = 1000;

  async function wait(ms) {
    if (signal.aborted) return;
    await new Promise(resolve => {
      const finish = () => {
        clearTimeout(timer);
        signal.removeEventListener("abort", finish);
        resolve();
      };
      const timer = setTimeout(finish, ms);
      signal.addEventListener("abort", finish, { once: true });
    });
  }

  while (!signal.aborted) {
    let reader;
    try {
      const response = await fetch(url, {
        headers: { "X-Job-Token": token, Accept: "text/event-stream" },
        cache: "no-store",
        signal,
      });
      if (!response.ok) {
        onError(`Stream unavailable (${response.status})`);
        // A missing job/token requires user action; do not retry forever.
        if (response.status >= 400 && response.status < 500 && response.status !== 429) return;
        await wait(backoff);
        backoff = Math.min(backoff * 2, 10000);
        continue;
      }
      if (!response.body) throw new Error("Streaming body unavailable");

      reader = response.body.getReader();
      const decoder = new TextDecoder();
      let pending = "";
      let event = "message";
      let data = [];

      function consume(text) {
        pending += text;
        let newline;
        while ((newline = pending.indexOf("\n")) !== -1) {
          const line = pending.slice(0, newline).replace(/\r$/, "");
          pending = pending.slice(newline + 1);
          if (line === "") {
            if (event === "snapshot" && data.length) {
              onSnapshot(JSON.parse(data.join("\n")));
              backoff = 1000;
            } else if (event === "stream_error") {
              onError("Live updates unavailable; reconnecting.");
            }
            event = "message";
            data = [];
          } else if (!line.startsWith(":")) {
            const colon = line.indexOf(":");
            const field = colon === -1 ? line : line.slice(0, colon);
            const value = colon === -1 ? "" : line.slice(colon + 1).replace(/^ /, "");
            if (field === "event") event = value;
            if (field === "data") data.push(value);
          }
        }
      }

      while (!signal.aborted) {
        const { done, value } = await reader.read();
        if (done) {
          consume(decoder.decode());
          break; // Discard an incomplete event; reconnect yields a fresh snapshot.
        }
        consume(decoder.decode(value, { stream: true }));
      }
    } catch (error) {
      if (signal.aborted) return;
      onError("Connection interrupted; reconnecting.");
      backoff = Math.min(backoff * 2, 10000);
    } finally {
      if (reader) {
        await reader.cancel().catch(() => {});
        reader.releaseLock();
      }
    }
    await wait(backoff);
  }
}

// Start once per open job view. Call controller.abort() during view cleanup.
const controller = new AbortController();
// void watchJob({ baseUrl, jobId, token, signal: controller.signal,
//   onSnapshot: renderJob, onError: showConnectionStatus });
// On unmount / job switch: controller.abort();
```

Do not make a lost stream connection look like a failed job. Show a connection indicator
and reconnect; a GET snapshot is also a valid fallback. Only one watcher should be active
per open job view. Reconnect after switching back to a suspended view and read fresh state.

## Recovery, evidence and scope

`chat_error` is separate from the job's `error`: `CHAT_FAILED` means generation or reply
validation failed; `CHAT_INTERRUPTED` means a thinking lease expired. Send a new message
UUID to retry a failed turn. The previous user message remains in history.
HTTP errors include 409 `CHAT_BUSY`, `CHAT_LIMIT`, `MESSAGE_CONFLICT`, `PROPOSAL_STALE`,
`PROPOSAL_DECIDED`; 404 `PROPOSAL_NOT_FOUND`; and 503 `CHAT_UNAVAILABLE`.
Repeating the same accept/reject decision is idempotent; reversing it returns 409.
Only the last 12 messages are supplied to Gemini, alongside saved BOM and offer data;
the full bounded history remains in snapshots. Each active stream reads storage about
once per second; avoid multiple watchers for the same view.

- Messages and pending chat work are stored with the job. Firestore provides durability
  across restarts; memory storage does not.
- Queued chat work can resume. An interrupted turn already marked `thinking` fails
  visibly after its lease expires rather than silently repeating model generation.
- Generated answers use saved project state. They are explanations, not new verified
  seller evidence. Missing information remains unknown; show the existing evidence and
  compatibility limitations alongside answers.
- Demo jobs use a labelled deterministic response, with no model generation or edit
  proposals. Never display demo content as a live agent result.
- This milestone does not implement pausing or cancelling sourcing, autonomous tool
  execution, file uploads, or conversational changes to a completed report. Existing
  report spec, refresh and selection endpoints still handle those supported actions.

For a useful frontend acceptance check: extract a BOM, ask about a cited part, request
a draft quantity/ownership change, reject one proposal, accept another, verify the BOM
changed without sourcing, and then explicitly confirm. Also test a reconnect, duplicate
message submission, stale proposal and demo job.
