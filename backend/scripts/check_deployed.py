"""Verify the deployed integration API and a live extraction/chat/SSE round trip."""

import json
import time
from pathlib import Path
from uuid import uuid4

import httpx


def main():
    access = json.loads(Path(".data/integration-access.json").read_text(encoding="utf-8"))
    base, key = access["base_url"], access["integration_key"]
    with httpx.Client(base_url=base, timeout=90) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("Health:", health.json(), flush=True)
        assert client.get("/openapi.json").json()["info"]["version"] == "0.18.0"
        assert client.post("/v1/jobs", json={"url": "https://example.com"}).status_code == 401
        for origin in ["http://localhost:5173", "http://localhost:3000"]:
            preflight = client.options(
                "/v1/jobs",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "Content-Type,X-Integration-Key,X-Job-Token",
                },
            )
            assert preflight.status_code == 200
            assert preflight.headers["access-control-allow-origin"] == origin
        headers = {"X-Integration-Key": key}
        created = client.post(
            "/v1/jobs", headers=headers, json={"url": "https://www.youtube.com/shorts/En4KD0c3XXs"}
        )
        created.raise_for_status()
        job_id = created.json()["job_id"]
        headers["X-Job-Token"] = created.json()["job_token"]
        # Store credentials only in ignored local runtime data, never logs or documentation.
        Path(".data/deployed-smoke-access.json").write_text(
            json.dumps({"job_id": job_id, "job_token": headers["X-Job-Token"]}), encoding="utf-8"
        )
        path = f"/v1/jobs/{job_id}"
        print("Created live integration test job:", job_id, flush=True)

        def poll(field, terminal):
            deadline = time.monotonic() + 420
            previous = None
            while time.monotonic() < deadline:
                response = client.get(path, headers=headers)
                response.raise_for_status()
                job = response.json()
                if job[field] != previous:
                    print(field + ":", job[field], flush=True)
                    previous = job[field]
                if job[field] in terminal:
                    return job
                time.sleep(3)
            raise RuntimeError("Integration polling timed out")

        job = poll("status", {"awaiting_confirmation", "failed"})
        assert job["status"] == "awaiting_confirmation", job.get("error")
        assert job["items"]
        reply = client.post(
            path + "/messages",
            headers=headers,
            json={
                "message_id": str(uuid4()),
                "text": "What parts did you find? Cite their line IDs. Do not edit anything.",
            },
        )
        reply.raise_for_status()
        job = poll("chat_state", {"idle", "failed"})
        assert job["chat_state"] == "idle", job.get("chat_error")
        with client.stream("GET", path + "/stream", headers=headers) as stream:
            stream.raise_for_status()
            assert "text/event-stream" in stream.headers["content-type"]
            for line in stream.iter_lines():
                if line.startswith("data: "):
                    snapshot = json.loads(line[6:])
                    assert snapshot["job_id"] == job_id
                    assert snapshot["messages"][-1]["role"] == "assistant"
                    break
            else:
                raise RuntimeError("No SSE snapshot received")
        Path(".data/deployed-smoke-result.json").write_text(
            json.dumps(job, indent=2), encoding="utf-8"
        )
        print("PASS: health, access, CORS, live extraction, persisted chat and remote SSE.")


if __name__ == "__main__":
    main()
