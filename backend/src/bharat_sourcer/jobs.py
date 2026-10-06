"""Atomic job transitions. External I/O stays outside storage transactions."""

import secrets
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from hashlib import sha256
from uuid import UUID, uuid4

from bharat_sourcer.actions import complete_refresh
from bharat_sourcer.compat import assess, resolve_part
from bharat_sourcer.costing import update_costs
from bharat_sourcer.extraction import ExtractionError, Extractor
from bharat_sourcer.identity import Principal
from bharat_sourcer.intake import extract_sources, validate_sources
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
    ProjectContext,
    RefreshOffers,
    RemoveLine,
    Report,
    ReportLine,
    SelectOffers,
    Status,
    UpdateJobSpecs,
    UpdateProject,
    now,
)
from bharat_sourcer.sourcing.research import check_requirements
from bharat_sourcer.sourcing.service import SourcingService
from bharat_sourcer.storage import JobStore, MemoryJobStore, StoredJob


class JobError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int = 60):
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after


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
        sourcing_parallelism: int = 1,
    ):
        self.extractor = extractor
        self.model = model
        self.store = store or MemoryJobStore()
        self.lease_seconds = lease_seconds
        self.sourcing = sourcing
        self.sourcing_max_parts = sourcing_max_parts
        self.sourcing_lease_seconds = sourcing_lease_seconds
        self.sourcing_parallelism = max(1, min(sourcing_parallelism, 4))

    @staticmethod
    def _transition(job: Job, status: Status, message: str) -> None:
        job.status = status
        job.updated_at = now()
        job.events.append(Event(seq=len(job.events) + 1, status=status, message=message))

    def create(
        self, request: CreateJob, principal: Principal | None = None, part_limit: int | None = None
    ) -> tuple[Job, str]:
        kind, count = "demo", 1
        if self.extractor:
            try:
                sources = validate_sources([str(url) for url in [request.url, *request.sources]])
            except ExtractionError as exc:
                raise JobError(400, exc.code, exc.message) from exc
            kind, count = sources[0][0], len(sources)
        job = Job(
            job_id=str(uuid4()),
            input=request,
            demo=self.extractor is None,
            extraction_model=self.model,
            sourcing_enabled=self.sourcing is not None and self.extractor is not None,
        )
        token = secrets.token_urlsafe(32)
        message = {
            "demo": "Demo job queued.",
            "video": "Video queued.",
            "project_page": "Project page queued.",
        }[kind]
        if count > 1:
            more = count - 1
            message = message.removesuffix(".") + f" with {more} more source{'s' * (more > 1)}."
        self._transition(job, "queued", message)
        self.store.create(
            StoredJob(
                job=job,
                token_hash=self._hash(token),
                owner_id=principal.owner if principal else None,
                part_limit=part_limit,
            )
        )
        return job.model_copy(deep=True), token

    @staticmethod
    def _hash(token: str | None) -> str:
        return sha256((token or "").encode()).hexdigest()

    def _authorized(self, record: StoredJob | None, token: str | None) -> Job:
        if isinstance(token, Principal):
            if token.expires_at is not None and token.expires_at <= time.time():
                raise JobError(401, "IDENTITY_EXPIRED", "Session expired; refresh your credentials")
            if record is None or record.owner_id != token.owner:
                raise JobError(404, "JOB_NOT_FOUND", "Project not found")
            return record.job
        if record is not None and record.owner_id is not None:
            raise JobError(404, "JOB_NOT_FOUND", "Project not found")
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
        project = None
        reports = []
        try:
            if claimed.job.demo:
                items = [
                    BomItem(line_id="L01", raw_name="ESP32 development board"),
                    BomItem(line_id="L02", raw_name="BME280 sensor module"),
                    BomItem(line_id="L03", raw_name="Jumper wire", qty=4),
                ]
                project = ProjectContext(
                    title="Demo: ESP32 weather station (sample)",
                    description="Fixed demo project. Not extracted from the submitted link.",
                    summary="Demo sample: an ESP32 reads a BME280 sensor over jumper wires.",
                )
            else:
                job_input = claimed.job.input
                result = extract_sources(
                    self.extractor, [str(url) for url in [job_input.url, *job_input.sources]]
                )
                items, project, reports = result.items, result.project, result.sources
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
                record.job.project = project
                record.job.source_reports = reports
                for item in record.job.items:
                    item.clarifications = resolve_part(item).clarifications
                self._transition(record.job, "awaiting_confirmation", "Review parts and evidence.")

        self.store.mutate(job_id, complete)

    def recover(self, job_id: str | None = None, *, execute: bool = True) -> None:
        keys = [job_id] if job_id else self.store.pending()
        for job_id in keys:
            record = self.store.get(job_id)
            if record is None:
                continue
            if record.job.status == "queued":
                if execute:
                    self.extract(job_id)
            elif record.job.status == "resolving":
                if execute:
                    self.finish(job_id)
            elif record.job.status in {"extracting", "sourcing"}:

                def expire(current: StoredJob):
                    if current.job.status not in {"extracting", "sourcing"}:
                        return
                    if current.lease_until and current.lease_until > now():
                        return
                    current.run_id = None
                    current.lease_until = None
                    if current.job.status == "sourcing" and current.job.pause_requested:
                        self._pause_at_checkpoint(current)
                        return
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
                    if current.job.status == "sourcing":
                        complete_refresh(current.job, failed=True)
                    self._transition(current.job, "failed", current.job.error.message)

                self.store.mutate(job_id, expire)

    def _pause_at_checkpoint(self, record: StoredJob) -> None:
        record.run_id = None
        record.lease_until = None
        self._transition(record.job, "paused", "Sourcing paused; saved results are preserved.")

    def pause(self, job_id: str, token: str | None) -> Job:
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            if job.status not in {"resolving", "sourcing", "paused"} or not job.sourcing_enabled:
                raise JobError(409, "INVALID_STATE", "Pause requires active live sourcing")
            if job.pause_requested:
                return
            job.pause_requested = True
            if job.status == "resolving":
                self._pause_at_checkpoint(record)
            else:
                self._transition(job, "sourcing", "Pause requested; current part may finish first.")

        record = self.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job.model_copy(deep=True)

    def resume(self, job_id: str, token: str | None) -> Job:
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            if job.status in {"resolving", "sourcing"} and not job.pause_requested:
                return
            if job.status != "paused":
                raise JobError(409, "INVALID_STATE", "Wait for paused before resuming")
            if self.sourcing is None:
                raise JobError(
                    503, "SOURCING_UNAVAILABLE", "Sourcing is unavailable on this worker"
                )
            job.pause_requested = False
            self._transition(job, "resolving", "Resuming remaining sourcing work.")

        record = self.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job.model_copy(deep=True)

    def refresh_offers(self, job_id: str, token: str | None, request: RefreshOffers) -> None:
        self._validate_id(job_id)

        def change(record: StoredJob):
            self._authorized(record, token)
            if record.part_limit and len(request.line_ids) > record.part_limit:
                raise JobError(422, "PART_LIMIT", "Choose fewer parts for this account tier")
            self.prepare_refresh(record, request)

        if self.store.mutate(job_id, change) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")

    def prepare_refresh(self, record: StoredJob, request: RefreshOffers) -> None:
        """Validate and queue a refresh inside an existing transaction; no external I/O."""
        job = record.job
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
            raise JobError(503, "SOURCING_UNAVAILABLE", "Sourcing is unavailable on this worker")
        if job.refresh_count >= 2:
            raise JobError(409, "REFRESH_LIMIT", "Two refresh batches have already been used")
        wanted = set(request.line_ids)
        items = {item.line_id: item for item in job.items}
        if (
            len(wanted) != len(request.line_ids)
            or not wanted.issubset(items)
            or any(items[key].user_has_it for key in wanted)
            or len(wanted)
            > min(self.sourcing_max_parts, record.part_limit or self.sourcing_max_parts)
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
                lines.append(ReportLine(item=item.model_copy(deep=True), sourcing_status="not_run"))
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

    def apply_spec_updates(self, job: Job, request: UpdateJobSpecs) -> None:
        """Validate and apply spec/requirement updates to a completed live report in place."""
        if job.status != "done" or job.report is None or job.demo:
            raise JobError(409, "INVALID_STATE", "Update specs in a completed live report")
        items = {item.line_id: item for item in job.items}
        lines = {line.item.line_id: line for line in job.report.lines}
        seen, changed = set(), []
        for update in request.updates:
            key = update.line_id
            if key in seen or key not in items or key not in lines:
                raise JobError(422, "INVALID_EDIT", "Unknown or repeated line")
            seen.add(key)
            item = items[key]
            try:
                merged = PartSpecs(
                    **(
                        item.specs.model_dump()
                        | (update.specs.model_dump(exclude_unset=True) if update.specs else {})
                    )
                )
                requirements = (
                    update.requirements if update.requirements is not None else item.requirements
                )
                candidate = item.model_copy(
                    update={"specs": merged, "requirements": requirements}, deep=True
                )
                resolution = resolve_part(candidate)
            except ValueError as exc:
                raise JobError(422, "INVALID_SPECS", "Conflicting part specifications") from exc
            if merged == item.specs and requirements == item.requirements:
                continue
            item.specs = merged
            item.requirements = requirements
            item.user_edited = True
            item.clarifications = resolution.clarifications
            line = lines[key]
            line.item = item.model_copy(deep=True)
            line.resolution = resolution
            for offer in line.offers:
                offer.compatibility = assess(resolution.specs, offer.specs)
                offer.compatibility.references.append(str(offer.url))
                offer.compatibility_status = offer.compatibility.status
            line.selected_offer_url = None
            line.price_inr = line.grade = None
            line.changes_accepted = False
            line.research_accepted = False
            changed.append(key)
        if changed:
            # Every LLM assessment used project context; sibling edits can invalidate it.
            for line in job.report.lines:
                if line.research:
                    line.research.status = "stale"
                    line.research.summary = "Project requirements changed; refresh to reassess."
                    for candidate in line.research.candidates:
                        candidate.assessment.status = "stale"
                        candidate.assessment.explanation = (
                            "Project context changed. Refresh for a new AI assessment."
                        )
                        candidate.assessment.conditions = []
                        candidate.assessment.checks = check_requirements(
                            line.item.requirements, candidate.facts
                        )
                for offer in line.offers:
                    if offer.research_assessment:
                        offer.research_assessment.status = "stale"
                        offer.research_assessment.explanation = (
                            "Project context changed. Refresh for a new AI assessment."
                        )
                        offer.research_assessment.conditions = []
                        offer.research_assessment.checks = []
                if line.research_accepted:
                    line.selected_offer_url = None
                    line.price_inr = line.grade = None
                    line.research_accepted = False
                    line.changes_accepted = False
            update_costs(job.report)
            self._transition(job, "done", "Updated required specs for " + ", ".join(changed))

    def update_project(self, job_id: str, token: str | None, request: UpdateProject) -> Job:
        """Owner edits to the AI-written title/description; the summary stays the model's."""
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            project = job.project or ProjectContext()
            if request.title is not None:
                project.title, project.title_source = request.title, "user"
            if request.description is not None:
                project.description, project.description_source = request.description, "user"
            job.project = project
            job.updated_at = now()

        record = self.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job.model_copy(deep=True)

    def update_specs(self, job_id: str, token: str | None, request: UpdateJobSpecs) -> Job:
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            self.apply_spec_updates(job, request)

        record = self.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job.model_copy(deep=True)

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
                    line.research_accepted = False
                    continue
                offer = next((o for o in line.offers if o.url == selection.offer_url), None)
                if offer is None:
                    raise JobError(422, "INVALID_SELECTION", "Offer is not in this report")
                if offer.stock != "in_stock":
                    raise JobError(422, "OFFER_UNAVAILABLE", "Offer must be reported in stock")
                if offer.checked_at < now() - timedelta(hours=24):
                    raise JobError(409, "OFFER_STALE", "Offer is over 24 hours old; source again")
                compat = offer.compatibility
                if line.item.requirements:
                    candidate = (
                        next((c for c in line.research.candidates if c.url == offer.url), None)
                        if line.research and line.research.status == "ready"
                        else None
                    )
                    checks = check_requirements(
                        line.item.requirements, candidate.facts if candidate else []
                    )
                    if any(c.status != "meets" for c in checks):
                        raise JobError(
                            422,
                            "REQUIREMENTS_UNRESOLVED",
                            "This offer has missing or conflicting requirement evidence",
                        )
                reviewed = False
                if compat is None or compat.grade not in {"A", "B"}:
                    review = offer.research_assessment
                    reviewed = bool(
                        selection.accept_research_assessment
                        and line.research
                        and line.research.status == "ready"
                        and review
                        and review.status == "potential_match"
                        and all(c.status == "meets" for c in review.checks)
                        and (compat is None or compat.status in {"unknown"})
                    )
                    if not reviewed:
                        raise JobError(
                            422,
                            "COMPATIBILITY_UNRESOLVED",
                            "Resolve specifications or explicitly approve a current research match",
                        )
                if compat and compat.grade == "B" and not selection.accept_changes:
                    raise JobError(422, "CHANGES_REQUIRED", "Acknowledge the listed changes")
                line.selected_offer_url = offer.url
                line.price_inr = offer.price_inr
                line.grade = None if reviewed else compat.grade
                line.changes_accepted = bool(compat and compat.grade == "B")
                line.research_accepted = reviewed
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
            self.edit_draft(job, request, finalize=True)
            if (
                record.part_limit
                and sum(not item.user_has_it for item in job.items) > record.part_limit
            ):
                raise JobError(
                    422, "PART_LIMIT", "Remove parts or mark owned parts before confirming"
                )

        if self.store.mutate(job_id, change) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")

    def edit_draft(self, job: Job, request: ConfirmJob, *, finalize: bool = False) -> None:
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
                    qty=edit.qty or 1,
                    qty_source="user" if edit.qty else "inferred",
                    qty_reason=None if edit.qty else "Count not given; assumed one.",
                    user_edited=True,
                    specs=edit.specs,
                    requirements=edit.requirements,
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
                    if edit.raw_name != items[edit.line_id].raw_name:
                        # Evidence was assessed for the extracted name, not the new one.
                        items[edit.line_id].confidence = None
                        items[edit.line_id].confidence_reason = None
                    items[edit.line_id].raw_name = edit.raw_name
                if edit.qty is not None and edit.qty != items[edit.line_id].qty:
                    items[edit.line_id].qty = edit.qty
                    items[edit.line_id].qty_source = "user"
                    items[edit.line_id].qty_reason = None
                if edit.requirements is not None:
                    items[edit.line_id].requirements = edit.requirements
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
        if finalize:
            # Never block a maker on a count the source omitted (older snapshots can hold null).
            for item in items.values():
                if item.qty is None:
                    item.qty, item.qty_source = 1, "inferred"
                    item.qty_reason = "Count not stated; assumed one. Change it if needed."
        job.items = list(items.values())
        for item in job.items:
            try:
                item.clarifications = resolve_part(item).clarifications
            except ValueError as exc:
                raise JobError(
                    422, "INVALID_SPECS", "Name and part specifications conflict"
                ) from exc
        if finalize:
            self._transition(job, "resolving", "Confirmed edits; preparing the report.")
        else:
            self._transition(
                job,
                "awaiting_confirmation",
                "Applied reviewed chat proposal; review BOM before confirming.",
            )

    def finish(self, job_id: str, *, one_line: bool = False) -> None:
        record = self.store.get(job_id)
        if record and record.job.sourcing_enabled and not record.job.demo:
            self._source(job_id, one_line=one_line)
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

    def _source(self, job_id: str, *, one_line: bool = False) -> None:
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
        pending = [
            item
            for item in claimed.job.items
            if item.line_id not in completed and (scope is None or item.line_id in scope)
        ]

        def source_item(item, limited):
            if limited:
                return ReportLine(
                    item=item,
                    sourcing_status="not_run",
                    sourcing_error=ErrorDetail(
                        code="SOURCING_LIMIT", message="Per-job sourcing limit reached"
                    ),
                )
            try:
                project_source = getattr(self.sourcing, "source_for_project", None)
                if project_source:
                    return project_source(item, claimed.job.items)
                return self.sourcing.source(item)
            except Exception:
                return ReportLine(
                    item=item,
                    sourcing_status="failed",
                    sourcing_error=ErrorDetail(
                        code="SOURCING_FAILED", message="Could not source this part"
                    ),
                )

        for offset in range(0, len(pending), self.sourcing_parallelism):
            current = self.store.get(job_id)
            if current is None or current.run_id != run_id or current.job.status != "sourcing":
                return
            if current.job.pause_requested:

                def acknowledge(record):
                    if record.run_id == run_id and record.job.status == "sourcing":
                        self._pause_at_checkpoint(record)

                self.store.mutate(job_id, acknowledge)
                return
            batch = pending[offset : offset + self.sourcing_parallelism]
            with ThreadPoolExecutor(max_workers=self.sourcing_parallelism) as pool:
                futures = []
                for item in batch:
                    limit = min(
                        self.sourcing_max_parts, claimed.part_limit or self.sourcing_max_parts
                    )
                    limited = not item.user_has_it and searched >= limit
                    if not item.user_has_it and not limited:
                        searched += 1
                    futures.append(pool.submit(source_item, item, limited))
                for future in as_completed(futures):
                    line = future.result()

                    def checkpoint(record, result=line):
                        if record.run_id != run_id or record.job.status != "sourcing":
                            return
                        lines = {line.item.line_id: line for line in record.job.report.lines}
                        lines[result.item.line_id] = result
                        record.job.report.lines = [
                            lines[item.line_id]
                            for item in record.job.items
                            if item.line_id in lines
                        ]
                        update_costs(record.job.report)
                        record.lease_until = now() + timedelta(seconds=self.sourcing_lease_seconds)
                        self._transition(
                            record.job, "sourcing", f"Checked sourcing for {result.item.line_id}."
                        )

                    self.store.mutate(job_id, checkpoint)

            def batch_complete(record):
                if record.run_id != run_id or record.job.status != "sourcing":
                    return
                if record.job.pause_requested:
                    self._pause_at_checkpoint(record)
                elif one_line:
                    record.run_id = record.lease_until = None
                    self._transition(record.job, "resolving", "Batch saved; remaining work queued.")

            self.store.mutate(job_id, batch_complete)
            if one_line:
                return

        def complete(record: StoredJob):
            if record.run_id != run_id or record.job.status != "sourcing":
                return
            if record.job.pause_requested:
                self._pause_at_checkpoint(record)
                return
            record.run_id = None
            record.lease_until = None
            record.job.report.summary = (
                "Sourcing finished. Compatibility compares declared specs only; review evidence "
                "and missing fields. Seller trust, tax and shipping remain unverified."
            )
            update_costs(record.job.report)
            # Same transaction as the transition, so redelivered work cannot repeat it.
            complete_refresh(record.job)
            self._transition(record.job, "done", "Sourcing report ready for review.")

        self.store.mutate(job_id, complete)
