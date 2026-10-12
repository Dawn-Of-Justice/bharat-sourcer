"""Durable HTTP dispatch. Firestore pending states are the recoverable outbox."""

import base64
import json
import logging
import time
from hashlib import sha256
from typing import Literal
from uuid import UUID, uuid4

import google.auth
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token

from bharat_sourcer.schemas import Model


class Work(Model):
    job_id: UUID
    # overview: draw the project overview (overview.py) after extraction or on request.
    kind: Literal["workflow", "chat", "overview"]


class CloudDispatcher:
    def __init__(self, settings):
        self.settings = settings

    def enqueue(self, job_id, kind, *, sweep=False):
        settings = self.settings
        queue = (
            f"projects/{settings.gcp_project}/locations/{settings.tasks_location}"
            f"/queues/{settings.tasks_queue}"
        )
        # A sweep can be retried without adding another task in the same five-minute window.
        nonce = str(int(time.time() // 300)) if sweep else str(uuid4())
        name = sha256(f"{job_id}:{kind}:{nonce}".encode()).hexdigest()
        body = base64.b64encode(json.dumps({"job_id": job_id, "kind": kind}).encode()).decode()
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        with AuthorizedSession(credentials) as session:
            response = session.post(
                f"https://cloudtasks.googleapis.com/v2/{queue}/tasks",
                json={
                    "task": {
                        "name": f"{queue}/tasks/{name}",
                        "dispatchDeadline": "1800s",
                        "httpRequest": {
                            "httpMethod": "POST",
                            "url": settings.tasks_url + "/internal/work",
                            "headers": {"Content-Type": "application/json"},
                            "body": body,
                            "oidcToken": {
                                "serviceAccountEmail": settings.tasks_service_account,
                                "audience": settings.tasks_url,
                            },
                        },
                    }
                },
                timeout=20,
            )
            if response.status_code != 409:
                response.raise_for_status()

    def notify(self, job_id, kind):
        try:
            self.enqueue(job_id, kind)
        except Exception:
            # The persisted pending state will be redispatched by the scheduler.
            logging.getLogger(__name__).error("TASK_ENQUEUE_FAILED job=%s kind=%s", job_id, kind)

    def authorize(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            return False
        try:
            claims = id_token.verify_oauth2_token(
                authorization[7:], Request(), audience=self.settings.tasks_url
            )
            return (
                claims.get("email") == self.settings.tasks_service_account
                and claims.get("email_verified") is True
            )
        except (ValueError, google.auth.exceptions.GoogleAuthError):
            return False


def work_once(jobs, conversation, work, overviews=None):
    key = str(work.job_id)
    if work.kind == "overview":
        # Always complete: a failed drawing is stored as failed, and an expired lease lets
        # the owner restart it; Cloud Tasks retries would only repeat paid calls.
        if overviews is not None:
            overviews.generate(key)
        return True
    if work.kind == "chat":
        conversation.recover(key, execute=False)
        conversation.process(key)
    else:
        jobs.recover(key, execute=False)
        record = jobs.store.get(key)
        if record and record.job.status == "queued":
            jobs.extract(key)
        else:
            jobs.finish(key, one_line=True)
    record = jobs.store.get(key)
    if record is None:
        return True
    return (
        record.job.chat_state not in {"queued", "thinking"}
        if work.kind == "chat"
        else record.job.status not in {"queued", "extracting", "resolving", "sourcing"}
    )
