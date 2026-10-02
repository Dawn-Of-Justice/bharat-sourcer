"""Local job service. Replace storage and workflow when cloud integration lands."""

import secrets
from threading import RLock
from uuid import uuid4

from bharat_sourcer.schemas import (
    AddLine,
    BomItem,
    ConfirmJob,
    CreateJob,
    Event,
    HaveLine,
    Job,
    RemoveLine,
    Report,
    ReportLine,
    Status,
    now,
)


class JobError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


class JobService:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._tokens: dict[str, str] = {}
        self._lock = RLock()

    @staticmethod
    def _transition(job: Job, status: Status, message: str) -> None:
        job.status = status
        job.updated_at = now()
        job.events.append(Event(seq=len(job.events) + 1, status=status, message=message))

    def create(self, request: CreateJob) -> tuple[Job, str]:
        with self._lock:
            job = Job(job_id=str(uuid4()), input=request)
            token = secrets.token_urlsafe(32)
            self._transition(job, "queued", "Demo job queued; the URL will not be fetched.")
            self._jobs[job.job_id] = job
            self._tokens[job.job_id] = token
            return job.model_copy(deep=True), token

    def _authorized(self, job_id: str, token: str | None) -> Job:
        expected = self._tokens.get(job_id)
        if expected is None or not secrets.compare_digest(
            expected.encode(), (token or "").encode()
        ):
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return self._jobs[job_id]

    def get(self, job_id: str, token: str | None) -> Job:
        with self._lock:
            return self._authorized(job_id, token).model_copy(deep=True)

    def extract_demo(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status != "queued":
                return
            self._transition(job, "extracting", "Loading the sample weather-station BOM.")
            job.items = [
                BomItem(line_id="L01", raw_name="ESP32 development board"),
                BomItem(line_id="L02", raw_name="BME280 sensor module"),
                BomItem(line_id="L03", raw_name="Jumper wire", qty=4),
            ]
            self._transition(job, "awaiting_confirmation", "Sample BOM ready for confirmation.")

    def confirm(self, job_id: str, token: str | None, request: ConfirmJob) -> None:
        with self._lock:
            job = self._authorized(job_id, token)
            if job.status != "awaiting_confirmation":
                raise JobError(409, "INVALID_STATE", "Job is not awaiting confirmation")
            # Work on a copy so any invalid edit rolls back the entire confirmation.
            items = {item.line_id: item.model_copy(deep=True) for item in job.items}
            next_id = max((int(key[1:]) for key in items), default=0) + 1
            for edit in request.edits:
                if isinstance(edit, AddLine):
                    line_id = f"L{next_id:02d}"
                    next_id += 1
                    items[line_id] = BomItem(line_id=line_id, raw_name=edit.raw_name, qty=edit.qty)
                    continue
                if edit.line_id not in items:
                    raise JobError(422, "INVALID_EDIT", f"Unknown line: {edit.line_id}")
                if isinstance(edit, RemoveLine):
                    del items[edit.line_id]
                elif isinstance(edit, HaveLine):
                    items[edit.line_id].user_has_it = edit.user_has_it
                else:
                    if edit.raw_name is not None:
                        items[edit.line_id].raw_name = edit.raw_name
                    if edit.qty is not None:
                        items[edit.line_id].qty = edit.qty
            if not items:
                raise JobError(422, "EMPTY_BOM", "Keep at least one BOM line")
            job.items = list(items.values())
            self._transition(job, "resolving", "Confirmed edits; preparing a demo report.")

    def finish_demo(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs[job_id]
            if job.status != "resolving":
                return
            job.report = Report(
                summary="Demo only. Extraction, sourcing and compatibility checks have not run.",
                lines=[
                    ReportLine(
                        item=item.model_copy(deep=True),
                        sourcing_status="already_owned" if item.user_has_it else "not_run",
                    )
                    for item in job.items
                ],
            )
            self._transition(job, "done", "Demo report ready. Prices and grades are unavailable.")
