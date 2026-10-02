"""Atomic job transitions. External I/O stays outside storage transactions."""

import secrets
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from bharat_sourcer.compat import resolve_part
from bharat_sourcer.costing import update_costs
from bharat_sourcer.extraction import ExtractionError, Extractor, youtube_url
from bharat_sourcer.schemas import (
    AddLine,
    BomItem,
    ConfirmJob,
    CreateJob,
    ErrorDetail,
    Event,
    HaveLine,
    Job,
    PartSpecs,
    RefreshOffers,
    RemoveLine,
    Report,
    ReportLine,
    SelectOffers,
    Status,
    now,
)
from bharat_sourcer.sourcing.service import SourcingService
from bharat_sourcer.storage import JobStore, MemoryJobStore, StoredJob


class JobError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status = status
        self.code = code
        self.message = message


class JobService:
    def __init__(
        self,
        extractor: Extractor | None = None,
        model: str | None = None,
        store: JobStore | None = None,
        lease_seconds: int = 600,
        sourcing: SourcingService | None = None,
        sourcing_max_parts: int = 10,
        sourcing_lease_seconds: int = 1800,
    ):
        self.extractor = extractor
        self.model = model
        self.store = store or MemoryJobStore()
        self.lease_seconds = lease_seconds
        self.sourcing = sourcing
        self.sourcing_max_parts = sourcing_max_parts
        self.sourcing_lease_seconds = sourcing_lease_seconds

    @staticmethod
    def _transition(job: Job, status: Status, message: str) -> None:
        job.status = status
        job.updated_at = now()
        job.events.append(Event(seq=len(job.events) + 1, status=status, message=message))

    def create(self, request: CreateJob) -> tuple[Job, str]:
        if self.extractor:
            try:
                youtube_url(str(request.url))
            except ExtractionError as exc:
                raise JobError(400, exc.code, exc.message) from exc
        job = Job(
            job_id=str(uuid4()),
            input=request,
            demo=self.extractor is None,
            extraction_model=self.model,
            sourcing_enabled=self.sourcing is not None and self.extractor is not None,
        )
        token = secrets.token_urlsafe(32)
        message = "Demo job queued." if job.demo else "Video queued."
        self._transition(job, "queued", message)
        self.store.create(StoredJob(job=job, token_hash=self._hash(token)))
        return job.model_copy(deep=True), token

    @staticmethod
    def _hash(token: str | None) -> str:
        return sha256((token or "").encode()).hexdigest()

    def _authorized(self, record: StoredJob | None, token: str | None) -> Job:
        if record is None or not secrets.compare_digest(record.token_hash, self._hash(token)):
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job

    def get(self, job_id: str, token: str | None) -> Job:
        self._validate_id(job_id)
        return self._authorized(self.store.get(job_id), token).model_copy(deep=True)

    @staticmethod
    def _validate_id(job_id: str) -> None:
        try:
            if str(UUID(job_id)) != job_id:
                raise ValueError
        except ValueError as exc:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid") from exc

    def extract_demo(self, job_id: str) -> None:
        self.extract(job_id)

    def extract(self, job_id: str) -> None:
        run_id = str(uuid4())

        def claim(record: StoredJob):
            if record.job.status != "queued":
                return
            if not record.job.demo and self.extractor is None:
                return
            if not record.job.demo:
                record.job.extraction_model = self.model
            record.run_id = run_id
            record.lease_until = now() + timedelta(seconds=self.lease_seconds)
            self._transition(record.job, "extracting", "Extracting parts.")

        claimed = self.store.mutate(job_id, claim)
        if claimed is None or claimed.run_id != run_id:
            return
        error = None
        items = []
        try:
            if claimed.job.demo:
                items = [
                    BomItem(line_id="L01", raw_name="ESP32 development board"),
                    BomItem(line_id="L02", raw_name="BME280 sensor module"),
                    BomItem(line_id="L03", raw_name="Jumper wire", qty=4),
                ]
            else:
                items = self.extractor.extract(str(claimed.job.input.url))
        except Exception as exc:
            error = (
                exc
                if isinstance(exc, ExtractionError)
                else ExtractionError(
                    "EXTRACTION_FAILED", "Extraction failed; start a new job to retry"
                )
            )

        def complete(record: StoredJob):
            if record.run_id != run_id or record.job.status != "extracting":
                return
            record.run_id = None
            record.lease_until = None
            if error:
                record.job.error = ErrorDetail(code=error.code, message=error.message)
                self._transition(record.job, "failed", error.message)
            else:
                record.job.items = items
                for item in record.job.items:
                    item.clarifications = resolve_part(item).clarifications
                self._transition(record.job, "awaiting_confirmation", "Review parts and evidence.")

        self.store.mutate(job_id, complete)

    def recover(self) -> None:
        for job_id in self.store.pending():
            record = self.store.get(job_id)
            if record is None:
                continue
            if record.job.status == "queued":
                self.extract(job_id)
            elif record.job.status == "resolving":
                self.finish(job_id)
            elif record.job.status in {"extracting", "sourcing"}:

                def expire(current: StoredJob):
                    if current.job.status not in {"extracting", "sourcing"}:
                        return
                    if current.lease_until and current.lease_until > now():
                        return
                    current.run_id = None
                    current.lease_until = None
                    if current.job.recovery_attempts < 1:
                        current.job.recovery_attempts += 1
                        current.job.error = None
                        target = "resolving" if current.job.status == "sourcing" else "queued"
                        self._transition(
                            current.job,
                            target,
                            "Interrupted work queued for one automatic recovery.",
                        )
                        return
                    current.job.error = ErrorDetail(
                        code=(
                            "SOURCING_INTERRUPTED"
                            if current.job.status == "sourcing"
                            else "EXTRACTION_INTERRUPTED"
                        ),
                        message="Processing was interrupted or expired; create a new job to retry",
                    )
                    self._transition(current.job, "failed", current.job.error.message)

                self.store.mutate(job_id, expire)

    def refresh_offers(self, job_id: str, token: str | None, request: RefreshOffers) -> None:
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            interrupted = (
                job.status == "failed" and job.error and job.error.code == "SOURCING_INTERRUPTED"
            )
            if (
                (job.status != "done" and not interrupted)
                or job.demo
                or not job.sourcing_enabled
                or job.report is None
            ):
                raise JobError(
                    409, "INVALID_STATE", "Refresh requires a completed or interrupted live report"
                )
            if self.sourcing is None:
                raise JobError(
                    503, "SOURCING_UNAVAILABLE", "Sourcing is unavailable on this worker"
                )
            if job.refresh_count >= 2:
                raise JobError(409, "REFRESH_LIMIT", "Two refresh batches have already been used")
            wanted = set(request.line_ids)
            items = {item.line_id: item for item in job.items}
            if (
                len(wanted) != len(request.line_ids)
                or not wanted.issubset(items)
                or any(items[key].user_has_it for key in wanted)
                or len(wanted) > self.sourcing_max_parts
            ):
                raise JobError(
                    422,
                    "INVALID_REFRESH",
                    "Choose distinct unowned lines within the sourcing limit",
                )
            previous = {line.item.line_id: line for line in job.report.lines}
            lines = []
            for item in job.items:
                if item.line_id in wanted:
                    lines.append(
                        ReportLine(item=item.model_copy(deep=True), sourcing_status="not_run")
                    )
                elif item.line_id in previous:
                    lines.append(previous[item.line_id])
                else:
                    lines.append(
                        ReportLine(
                            item=item.model_copy(deep=True),
                            sourcing_status="already_owned" if item.user_has_it else "not_run",
                            sourcing_error=None
                            if item.user_has_it
                            else ErrorDetail(
                                code="SOURCING_INTERRUPTED",
                                message="Not completed; select this line to refresh",
                            ),
                        )
                    )
            job.report.lines = lines
            job.report.summary = (
                "Refreshing selected parts; previous quotes for these parts were cleared."
            )
            update_costs(job.report)
            job.error = None
            job.refresh_count += 1
            record.sourcing_scope = request.line_ids.copy()
            record.run_id = None
            record.lease_until = None
            self._transition(
                job, "resolving", "Offer refresh queued for " + ", ".join(request.line_ids)
            )

        if self.store.mutate(job_id, change) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")

    def select_offers(self, job_id: str, token: str | None, request: SelectOffers) -> Job:
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            if job.status != "done" or job.report is None or job.demo:
                raise JobError(409, "INVALID_STATE", "Select offers in a completed live report")
            lines = {line.item.line_id: line for line in job.report.lines}
            seen = set()
            for selection in request.selections:
                if selection.line_id not in lines or selection.line_id in seen:
                    raise JobError(422, "INVALID_SELECTION", "Unknown or repeated line")
                seen.add(selection.line_id)
                line = lines[selection.line_id]
                if line.item.user_has_it:
                    raise JobError(422, "INVALID_SELECTION", "Owned parts do not need offers")
                if selection.offer_url is None:
                    line.selected_offer_url = None
                    line.price_inr = line.grade = None
                    line.changes_accepted = False
                    continue
                offer = next((o for o in line.offers if o.url == selection.offer_url), None)
                if offer is None:
                    raise JobError(422, "INVALID_SELECTION", "Offer is not in this report")
                if offer.stock != "in_stock":
                    raise JobError(422, "OFFER_UNAVAILABLE", "Offer must be reported in stock")
                if offer.checked_at < now() - timedelta(hours=24):
                    raise JobError(409, "OFFER_STALE", "Offer is over 24 hours old; source again")
                compat = offer.compatibility
                if compat is None or compat.grade not in {"A", "B"}:
                    raise JobError(422, "COMPATIBILITY_UNRESOLVED", "Offer needs supported specs")
                if compat.grade == "B" and not selection.accept_changes:
                    raise JobError(422, "CHANGES_REQUIRED", "Acknowledge the listed changes")
                line.selected_offer_url = offer.url
                line.price_inr = offer.price_inr
                line.grade = compat.grade
                line.changes_accepted = compat.grade == "B"
            update_costs(job.report)
            job.updated_at = now()

        record = self.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job.model_copy(deep=True)

    def confirm(self, job_id: str, token: str | None, request: ConfirmJob) -> None:
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            if job.status != "awaiting_confirmation":
                raise JobError(409, "INVALID_STATE", "Job is not awaiting confirmation")
            # Work on a copy so any invalid edit rolls back the entire confirmation.
            items = {item.line_id: item.model_copy(deep=True) for item in job.items}
            next_id = max((int(key[1:]) for key in items), default=0) + 1
            for edit in request.edits:
                if isinstance(edit, AddLine):
                    line_id = f"L{next_id:02d}"
                    next_id += 1
                    items[line_id] = BomItem(
                        line_id=line_id,
                        raw_name=edit.raw_name,
                        qty=edit.qty,
                        user_edited=True,
                        specs=edit.specs,
                    )
                    continue
                if edit.line_id not in items:
                    raise JobError(422, "INVALID_EDIT", f"Unknown line: {edit.line_id}")
                if isinstance(edit, RemoveLine):
                    del items[edit.line_id]
                elif isinstance(edit, HaveLine):
                    items[edit.line_id].user_has_it = edit.user_has_it
                else:
                    items[edit.line_id].user_edited = True
                    if edit.raw_name is not None:
                        items[edit.line_id].raw_name = edit.raw_name
                    if edit.qty is not None:
                        items[edit.line_id].qty = edit.qty
                    if edit.specs is not None:
                        try:
                            items[edit.line_id].specs = PartSpecs(
                                **(
                                    items[edit.line_id].specs.model_dump()
                                    | edit.specs.model_dump(exclude_unset=True)
                                )
                            )
                        except ValueError as exc:
                            raise JobError(
                                422, "INVALID_SPECS", "Conflicting part specifications"
                            ) from exc
            if not items:
                raise JobError(422, "EMPTY_BOM", "Keep at least one BOM line")
            if len(items) > 100:
                raise JobError(422, "BOM_TOO_LARGE", "Keep at most 100 BOM lines")
            if any(item.qty is None for item in items.values()):
                raise JobError(422, "UNKNOWN_QUANTITY", "Set a quantity for every retained part")
            job.items = list(items.values())
            for item in job.items:
                try:
                    item.clarifications = resolve_part(item).clarifications
                except ValueError as exc:
                    raise JobError(
                        422, "INVALID_SPECS", "Name and part specifications conflict"
                    ) from exc
            self._transition(job, "resolving", "Confirmed edits; preparing the report.")

        if self.store.mutate(job_id, change) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")

    def finish(self, job_id: str) -> None:
        record = self.store.get(job_id)
        if record and record.job.sourcing_enabled and not record.job.demo:
            self._source(job_id)
            return

        def change(record: StoredJob):
            job = record.job
            if job.status != "resolving":
                return
            job.report = Report(
                demo=job.demo,
                summary=(
                    "Demo only. Extraction, sourcing and compatibility checks have not run."
                    if job.demo
                    else "Extraction complete. Sourcing and compatibility checks have not run."
                ),
                lines=[
                    ReportLine(
                        item=item.model_copy(deep=True),
                        sourcing_status="already_owned" if item.user_has_it else "not_run",
                    )
                    for item in job.items
                ],
            )
            update_costs(job.report)
            self._transition(job, "done", "Report ready. Prices and grades are unavailable.")

        self.store.mutate(job_id, change)

    def _source(self, job_id: str) -> None:
        if self.sourcing is None:
            return
        run_id = str(uuid4())

        def claim(record: StoredJob):
            if record.job.status != "resolving":
                return
            record.run_id = run_id
            record.lease_until = now() + timedelta(seconds=self.sourcing_lease_seconds)
            if record.job.report is None:
                record.job.report = Report(
                    demo=False,
                    summary="Sourcing in progress; compatibility is not checked.",
                    lines=[],
                )
            self._transition(
                record.job, "sourcing", "Discovering and checking seller product pages."
            )

        claimed = self.store.mutate(job_id, claim)
        if claimed is None or claimed.run_id != run_id:
            return
        scope = set(claimed.sourcing_scope) if claimed.sourcing_scope is not None else None
        completed = {
            line.item.line_id
            for line in claimed.job.report.lines
            if line.sourcing_status != "not_run" or line.sourcing_error is not None
        }
        searched = sum(
            not line.item.user_has_it and line.sourcing_status != "not_run"
            for line in claimed.job.report.lines
            if scope is None or line.item.line_id in scope
        )
        for item in claimed.job.items:
            if item.line_id in completed or (scope is not None and item.line_id not in scope):
                continue
            current = self.store.get(job_id)
            if current is None or current.run_id != run_id or current.job.status != "sourcing":
                return
            if not item.user_has_it and searched >= self.sourcing_max_parts:
                line = ReportLine(
                    item=item,
                    sourcing_status="not_run",
                    sourcing_error=ErrorDetail(
                        code="SOURCING_LIMIT", message="Per-job sourcing limit reached"
                    ),
                )
            else:
                try:
                    line = self.sourcing.source(item)
                except Exception:
                    line = ReportLine(
                        item=item,
                        sourcing_status="failed",
                        sourcing_error=ErrorDetail(
                            code="SOURCING_FAILED", message="Could not source this part"
                        ),
                    )
                if not item.user_has_it:
                    searched += 1

            def checkpoint(record: StoredJob, result=line):
                if record.run_id != run_id or record.job.status != "sourcing":
                    return
                lines = {line.item.line_id: line for line in record.job.report.lines}
                lines[result.item.line_id] = result
                record.job.report.lines = [
                    lines[item.line_id] for item in record.job.items if item.line_id in lines
                ]
                if scope is not None:
                    update_costs(record.job.report)
                record.lease_until = now() + timedelta(seconds=self.sourcing_lease_seconds)
                self._transition(
                    record.job, "sourcing", f"Checked sourcing for {result.item.line_id}."
                )

            self.store.mutate(job_id, checkpoint)

        def complete(record: StoredJob):
            if record.run_id != run_id or record.job.status != "sourcing":
                return
            record.run_id = None
            record.lease_until = None
            record.job.report.summary = (
                "Sourcing finished. Compatibility compares declared specs only; review evidence "
                "and missing fields. Seller trust, tax and shipping remain unverified."
            )
            update_costs(record.job.report)
            self._transition(record.job, "done", "Sourcing report ready for review.")

        self.store.mutate(job_id, complete)
