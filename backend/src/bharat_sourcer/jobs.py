"""Atomic job transitions. External I/O stays outside storage transactions."""

import contextvars
import logging
import secrets
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
from typing import Protocol
from uuid import UUID, uuid4

from bharat_sourcer.actions import complete_refresh
from bharat_sourcer.compat import assess_offer, keep_buyer_substitute, reassess_report, resolve_part
from bharat_sourcer.costing import bulk_waste, cheapest_cover, update_costs
from bharat_sourcer.countries import DEFAULT_COUNTRY
from bharat_sourcer.extraction import ExtractionError, Extractor
from bharat_sourcer.identity import Principal
from bharat_sourcer.intake import extract_sources, validate_sources
from bharat_sourcer.observability import log_event, stage_finished
from bharat_sourcer.recommend import (
    SELLER_PENALTY_INR,
    apply_recommendations,
    carry_selection,
    clear_selection,
    judge_confirmed,
    release_recommendations,
)
from bharat_sourcer.reconcile import Reconciler, reconcile_items
from bharat_sourcer.safety import flags_for
from bharat_sourcer.schemas import (
    AddLine,
    BomItem,
    BuildProgress,
    ConfirmJob,
    CopiedFrom,
    CreateJob,
    ErrorDetail,
    Event,
    ExtractionStep,
    HaveLine,
    Job,
    PartSpecs,
    ProjectContext,
    ReconciledLine,
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
from bharat_sourcer.sourcing.fabrication import design_links
from bharat_sourcer.sourcing.research import check_requirements
from bharat_sourcer.sourcing.service import SourcingService
from bharat_sourcer.spec_fill import SpecFiller, fill_missing_specs
from bharat_sourcer.storage import JobStore, MemoryJobStore, StoredJob
from bharat_sourcer.usage import JobLedger, attribute
from bharat_sourcer.youtube_meta import apply_retention

log = logging.getLogger(__name__)

# Statuses that end a run of work; reaching one logs JOB_FINISHED (observability.md).
FINISHED = frozenset({"done", "failed", "paused"})


def log_finished(job: Job) -> None:
    """Log JOB_FINISHED for a job that just reached done, failed or paused."""
    log_event(
        "JOB_FINISHED",
        job_id=job.job_id,
        status=job.status,
        code=job.error.code if job.status == "failed" and job.error else None,
        total_duration_ms=max(0, round((now() - job.created_at).total_seconds() * 1000)),
        part_count=len(job.items),
        demo=job.demo,
        prior_finishes=sum(event.status in FINISHED for event in job.events[:-1]),
        usd_est=job.cost_estimate.total_usd if job.cost_estimate else None,
    )


def same_part(before: BomItem, after: BomItem) -> bool:
    """Whether seller results found for `before` still describe `after` (quantity aside)."""
    return (
        before.raw_name == after.raw_name
        and before.buyable_spec == after.buyable_spec
        and before.specs == after.specs
        and before.requirements == after.requirements
        and before.fabrication == after.fabrication
    )


def worth_rechecking(line: ReportLine) -> bool:
    """A refresh re-checks known listings only when one was usable: in stock, judged an
    exact or compatible match by the spec judge (or unjudged), on a part whose value is
    known. A part the AI buyer decided is searched again so the buyer can decide again;
    the re-check alone would judge its pick by the strict spec check only."""
    if line.buyable_spec is not None and line.buyable_spec.needs_value:
        return False
    qty = line.item.qty or 1
    cheapest = cheapest_cover(qty, line.offers)
    return any(
        offer.stock == "in_stock"
        and not bulk_waste(qty, offer, cheapest)
        and (
            offer.match is None
            or (offer.match.status in {"exact", "compatible"} and offer.match.method != "llm_buyer")
        )
        for offer in line.offers
    )


class OverviewHooks(Protocol):
    """The project overview (overview.py) hooks into extraction without an import cycle."""

    def prepare(self, record: StoredJob) -> None: ...

    def after_extraction(self, job_id: str) -> None: ...


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
        sourcing_max_parts: int = 30,
        sourcing_lease_seconds: int = 1800,
        sourcing_parallelism: int = 1,
        seller_penalty_inr: Decimal = SELLER_PENALTY_INR,
        gemini_budget_usd: float | None = None,
        refresh_unlimited_uids: str = "",
        spec_filler: SpecFiller | None = None,
        reconciler: Reconciler | None = None,
    ):
        # Decides missing required spec fields after live extraction (spec_fill.py).
        self.spec_filler = spec_filler
        # Merges duplicate lines and drops non-purchases after live extraction (reconcile.py).
        self.reconciler = reconciler
        self.refresh_unlimited_owners = frozenset(
            "user:" + uid.strip() for uid in refresh_unlimited_uids.split(",") if uid.strip()
        )
        # Per-sourcing-run ceiling on estimated Gemini spend; None disables the guard.
        self.gemini_budget_usd = gemini_budget_usd
        self.extractor = extractor
        self.model = model
        self.store = store or MemoryJobStore()
        self.lease_seconds = lease_seconds
        self.sourcing = sourcing
        self.sourcing_max_parts = sourcing_max_parts
        self.sourcing_lease_seconds = sourcing_lease_seconds
        self.sourcing_parallelism = max(1, min(sourcing_parallelism, 4))
        self.seller_penalty_inr = Decimal(seller_penalty_inr)
        # Draws the project overview once extraction completes (set by create_app).
        self.overviews: OverviewHooks | None = None

    @staticmethod
    def _transition(job: Job, status: Status, message: str) -> None:
        job.status = status
        job.updated_at = now()
        job.events.append(Event(seq=len(job.events) + 1, status=status, message=message))

    def _mutate(self, job_id: str, change: Callable[[StoredJob], None]) -> StoredJob | None:
        """`store.mutate`, logging JOB_FINISHED once the saved change moved the job into done,
        failed or paused. Logged after the commit: a transaction may run `change` again."""
        before: list[str] = []

        def tracked(record: StoredJob) -> None:
            before[:] = [record.job.status]
            change(record)

        saved = self.store.mutate(job_id, tracked)
        if (
            saved is not None
            and before
            and saved.job.status in FINISHED
            and saved.job.status != before[0]
        ):
            log_finished(saved.job)
        return saved

    def create(
        self, request: CreateJob, principal: Principal | None = None, part_limit: int | None = None
    ) -> tuple[Job, str]:
        if "country" not in request.model_fields_set and principal and not principal.guest:
            request = request.model_copy(update={"country": self.account_country(principal)})
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

    # Shared projects that can be copied: a draft parts list or a finished report.
    COPYABLE = frozenset({"awaiting_confirmation", "done"})

    def check_copyable(self, source: Job, part_limit: int | None) -> None:
        if source.status not in self.COPYABLE:
            raise JobError(
                409, "SHARE_NOT_READY", "This project is still being prepared; try again later"
            )
        if part_limit and len(source.items) > part_limit:
            raise JobError(
                422, "PART_LIMIT", f"Sign in to copy a project with more than {part_limit} parts"
            )

    def copy_shared(
        self, source: Job, principal: Principal, part_limit: int | None = None
    ) -> tuple[Job, str]:
        """A new project for `principal` from a shared one. Copies what the share link
        shows (parts, project details, order plan); never the chat, history, cost record or
        share link. Owned parts go back to "to buy" and no AI runs."""
        self.check_copyable(source, part_limit)
        source = apply_retention(source.model_copy(deep=True))
        items = [item.model_copy(update={"user_has_it": False}) for item in source.items]
        report = None
        if source.report:
            report = source.report.model_copy(deep=True)
            for line in report.lines:
                # Grounded-search attribution stays with the original, as on the share page.
                line.attribution = None
                if line.item.user_has_it:
                    line.item = line.item.model_copy(update={"user_has_it": False})
                    if line.sourcing_status == "already_owned":
                        line.sourcing_status = "not_run"
                line.copied_choice = (
                    line.selection_source == "user" and line.selected_offer_url is not None
                )
            update_costs(report)
        job = Job(
            job_id=str(uuid4()),
            input=source.input,
            demo=source.demo,
            project=source.project,
            items=items,
            report=report,
            extraction_model=source.extraction_model,
            sourcing_enabled=not source.demo and self.sourcing is not None,
            safety_flags=source.safety_flags,
            source_reports=source.source_reports,
            video_meta=source.video_meta,
            copied_from=CopiedFrom(copied_at=now(), source_updated_at=source.updated_at),
            # A finished drawing of the same parts list; an unfinished one is not copied.
            overview=source.overview
            if source.overview and source.overview.status in {"ready", "stale"}
            else None,
            # Build steps for the same parts list; the received ticks are the owner's own.
            build_guide=source.build_guide
            if source.build_guide and source.build_guide.status in {"ready", "stale"}
            else None,
        )
        self._transition(
            job,
            source.status,
            "Copied from a shared project. Seller prices are from the shared snapshot; "
            "refresh to update them.",
        )
        token = secrets.token_urlsafe(32)
        self.store.create(
            StoredJob(
                job=job,
                token_hash=self._hash(token),
                owner_id=principal.owner,
                part_limit=part_limit,
            )
        )
        return job.model_copy(deep=True), token

    def account_country(self, principal: Principal) -> str:
        """The account's saved country, or the default when unset or unreadable."""
        try:
            saved = self.store.get_account(principal.owner)
        except Exception:  # A preference must never block a new project
            log.warning("ACCOUNT_SETTINGS_UNREADABLE", exc_info=True)
            saved = None
        return saved.country if saved else DEFAULT_COUNTRY

    @staticmethod
    def _hash(token: str | None) -> str:
        return sha256((token or "").encode()).hexdigest()

    def _authorized(self, record: StoredJob | None, token: str | None) -> Job:
        if isinstance(token, Principal):
            if token.expires_at is not None and token.expires_at <= time.time():
                raise JobError(401, "IDENTITY_EXPIRED", "Session expired; refresh your credentials")
            if record is None or record.owner_id != token.owner:
                raise JobError(404, "JOB_NOT_FOUND", "Project not found")
            record.job.refresh_limit = self.refresh_limit(record)
            return record.job
        if record is not None and record.owner_id is not None:
            raise JobError(404, "JOB_NOT_FOUND", "Project not found")
        if record is None or not secrets.compare_digest(record.token_hash, self._hash(token)):
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        record.job.refresh_limit = 2
        return record.job

    def refresh_limit(self, record: StoredJob) -> int | None:
        return None if record.owner_id in self.refresh_unlimited_owners else 2

    def get(self, job_id: str, token: str | None) -> Job:
        self._validate_id(job_id)
        # store.get returns a private copy, so it is not copied again: a deep copy costs
        # several times the Firestore parse on every poll and stream tick.
        job = self._authorized(self.store.get(job_id), token)
        return apply_retention(job)  # YouTube API data older than 30 days is not served.

    @staticmethod
    def _validate_id(job_id: str) -> None:
        try:
            if str(UUID(job_id)) != job_id:
                raise ValueError
        except ValueError as exc:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid") from exc

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
            record.job.extraction_progress = []
            self._transition(record.job, "extracting", "Extracting parts.")

        claimed = self.store.mutate(job_id, claim)
        if claimed is None or claimed.run_id != run_id:
            return
        error = None
        items = []
        project = None
        reports = []
        video_meta = None
        reconciled: list[ReconciledLine] = []
        # Extraction counts toward the job's total; the budget limits sourcing runs only.
        ledger = JobLedger(job_id, previous=claimed.job.cost_estimate)
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
                progress = self._progress_writer(job_id, run_id)
                if self.reconciler is not None:
                    progress("reconcile", "pending", "Checking the list as one build", None)
                if self.spec_filler is not None:
                    progress("spec_fill", "pending", "Filling in part details", None)
                with attribute(ledger):
                    result = extract_sources(
                        self.extractor,
                        [str(url) for url in [job_input.url, *job_input.sources]],
                        progress,
                    )
                items, project, reports = result.items, result.project, result.sources
                video_meta = result.video_meta
                # One call reads the whole build and merges lines that are the same part
                # (named differently by different sources) or drops ones that are not bought.
                if self.reconciler is not None:
                    progress("reconcile", "running", None, None)
                started = time.perf_counter()
                with attribute(ledger):
                    items, reconciled = reconcile_items(self.reconciler, items, project)
                if self.reconciler is not None:
                    # reconcile_items never raises: a failed review keeps the list (and logs
                    # RECONCILE_FAILED), so the stage itself always completes.
                    stage_finished(
                        "reconcile", started, "ok", job_id=job_id, changes=len(reconciled)
                    )
                    merged = sum(change.action == "merged" for change in reconciled)
                    progress(
                        "reconcile",
                        "done",
                        None,
                        f"{merged} duplicate {'line' if merged == 1 else 'lines'} combined"
                        if merged
                        else None,
                    )
                # One batched call fills required spec fields from project context so they
                # are not asked; saved on the items, so later draft edits reuse them.
                if self.spec_filler is not None:
                    progress("spec_fill", "running", None, None)
                started = time.perf_counter()
                with attribute(ledger):
                    fill_missing_specs(self.spec_filler, items, project)
                if self.spec_filler is not None:
                    # Like reconcile, a failed fill keeps the questions and logs SPEC_FILL_FAILED.
                    stage_finished("spec_fill", started, "ok", job_id=job_id)
                    progress("spec_fill", "done", None, None)
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
            if ledger.calls:
                estimate = ledger.snapshot()
                estimate.run_usd, estimate.budget_usd = 0.0, None
                record.job.cost_estimate = estimate
            if error:
                record.job.error = ErrorDetail(code=error.code, message=error.message)
                self._transition(record.job, "failed", error.message)
            else:
                record.job.items = items
                record.job.reconciled = reconciled
                record.job.project = project
                record.job.source_reports = reports
                record.job.video_meta = video_meta
                for item in record.job.items:
                    item.clarifications = resolve_part(item).clarifications
                record.job.safety_flags = flags_for(record.job)
                self._transition(record.job, "awaiting_confirmation", "Review parts and evidence.")
                if self.overviews is not None:
                    self.overviews.prepare(record)  # pending (or the demo drawing); no I/O

        saved = self._mutate(job_id, complete)
        if self.overviews is not None and saved and saved.job.status == "awaiting_confirmation":
            # Runs after the review page is available; never fails the extraction.
            self.overviews.after_extraction(job_id)

    def _progress_writer(self, job_id: str, run_id: str):
        """progress(key, status, label, detail) saving one live extraction step on the job.

        Called from source worker threads too; a failed write is logged and never affects
        the extraction."""

        def progress(key: str, status: str, label: str | None, detail: str | None) -> None:
            def change(record: StoredJob):
                if record.run_id != run_id or record.job.status != "extracting":
                    return
                steps = record.job.extraction_progress
                step = next((s for s in steps if s.key == key[:600]), None)
                if step is None:
                    if len(steps) >= 12:
                        return
                    step = ExtractionStep(key=key[:600], label=(label or key)[:200])
                    steps.append(step)
                if label:
                    step.label = label[:200]
                step.status = status
                if detail is not None:
                    step.detail = detail[:200]
                if status == "running" and step.started_at is None:
                    step.started_at = now()
                if status in ("done", "failed", "skipped"):
                    step.finished_at = now()

            try:
                self.store.mutate(job_id, change)
            except Exception:
                log.warning("EXTRACTION_PROGRESS_FAILED key=%s", key, exc_info=True)

        return progress

    def recover(self, job_id: str | None = None, *, execute: bool = True) -> None:
        keys = [job_id] if job_id else self.store.pending()
        for key in keys:
            record = self.store.get(key)
            if record is None:
                continue
            if record.job.status == "queued":
                if execute:
                    self.extract(key)
            elif record.job.status == "resolving":
                if execute:
                    self.finish(key)
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

                self._mutate(key, expire)

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

        record = self._mutate(job_id, change)
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
        limit = self.refresh_limit(record)
        job.refresh_limit = limit
        if limit is not None and job.refresh_count >= limit:
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
                fresh = ReportLine(item=item.model_copy(deep=True), sourcing_status="not_run")
                carry_selection(previous.get(item.line_id), fresh)
                lines.append(fresh)
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
        # Known offer pages are re-fetched first; paid rediscovery runs only if all are gone.
        known = record.refresh_urls or {}  # an interrupted refresh keeps its known URLs
        # Re-checking known listings only makes sense for a part that had a usable listing;
        # a part that failed or needs a value gets the full search (and the AI buyer).
        known = {
            key: [str(offer.url) for offer in previous[key].offers]
            if key in previous and worth_rechecking(previous[key])
            else known.get(key, [])
            for key in request.line_ids
        }
        record.refresh_urls = {key: urls for key, urls in known.items() if urls} or None
        if job.cost_estimate:
            # Each refresh is a new sourcing run with its own budget.
            job.cost_estimate.run_usd, job.cost_estimate.budget_reached = 0.0, False
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
                offer.compatibility = keep_buyer_substitute(
                    offer, assess_offer(resolution, offer, job.project, job.items, item)
                )
                offer.compatibility_status = offer.compatibility.status
            clear_selection(line)
            changed.append(key)
        if changed:
            # Every LLM assessment used project context; sibling edits can invalidate it.
            for line in job.report.lines:
                if line.research:
                    line.research.status = "stale"
                    line.research.summary = "Project requirements changed; refresh to reassess."
                    for researched in line.research.candidates:
                        researched.assessment.status = "stale"
                        researched.assessment.explanation = (
                            "Project context changed. Refresh for a new AI assessment."
                        )
                        researched.assessment.conditions = []
                        researched.assessment.checks = check_requirements(
                            line.item.requirements, researched.facts
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
                    clear_selection(line)
            # Recommended lines are recomputed; user choices are restored only if still valid.
            apply_recommendations(job.report, self.seller_penalty_inr)
            job.safety_flags = flags_for(job)
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
            job.safety_flags = flags_for(job)
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
                    line.selection_source, line.user_offer_url = "user", None
                    line.copied_choice = False
                    continue
                offer = next((o for o in line.offers if o.url == selection.offer_url), None)
                if offer is None:
                    raise JobError(422, "INVALID_SELECTION", "Offer is not in this report")
                if offer.stock != "in_stock":
                    raise JobError(422, "OFFER_UNAVAILABLE", "Offer must be reported in stock")
                if offer.checked_at < now() - timedelta(hours=24):
                    raise JobError(409, "OFFER_STALE", "Offer is over 24 hours old; source again")
                compat = offer.compatibility
                confirmed = judge_confirmed(offer)
                if line.item.requirements:
                    candidate = (
                        next((c for c in line.research.candidates if c.url == offer.url), None)
                        if line.research and line.research.status == "ready"
                        else None
                    )
                    checks = check_requirements(
                        line.item.requirements, candidate.facts if candidate else []
                    )
                    if any(c.status == "does_not_meet" for c in checks) or (
                        not confirmed and any(c.status != "meets" for c in checks)
                    ):
                        raise JobError(
                            422,
                            "REQUIREMENTS_UNRESOLVED",
                            "This offer has missing or conflicting requirement evidence",
                        )
                reviewed = False
                # A judge-confirmed match with no rule grade needs no separate research approval.
                judged_only = confirmed and (compat is None or compat.grade is None)
                if not judged_only and (compat is None or compat.grade not in {"A", "B"}):
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
                line.grade = None if reviewed or judged_only else compat.grade
                line.changes_accepted = bool(compat and compat.grade == "B")
                line.research_accepted = reviewed
                line.selection_source, line.user_offer_url = "user", offer.url
                line.copied_choice = False
            update_costs(job.report)
            job.updated_at = now()

        record = self.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job.model_copy(deep=True)

    def set_build_progress(self, job_id: str, token: str | None, request: BuildProgress) -> Job:
        """Tick or untick one line as received on the build page; idempotent."""
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            if job.status != "done":
                raise JobError(
                    409, "INVALID_STATE", "The build checklist is for a finished project"
                )
            if request.line_id not in {item.line_id for item in job.items}:
                raise JobError(422, "INVALID_LINE", f"Unknown line: {request.line_id}")
            if (request.line_id in job.build_received) == request.received:
                return  # already in the requested state
            received = [i for i in job.build_received if i != request.line_id]
            if request.received:
                received.append(request.line_id)
            job.build_received = received  # at most one id per line (100 lines at most)
            job.updated_at = now()

        record = self.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return record.job.model_copy(deep=True)

    def confirm(self, job_id: str, token: str | None, request: ConfirmJob) -> None:
        self._validate_id(job_id)

        def change(record: StoredJob):
            job = self._authorized(record, token)
            previous = job.report if job.status == "done" else None
            self.edit_draft(job, request, finalize=True, reopen=previous is not None)
            if (
                record.part_limit
                and sum(not item.user_has_it for item in job.items) > record.part_limit
            ):
                raise JobError(
                    422, "PART_LIMIT", "Remove parts or mark owned parts before confirming"
                )
            if previous is not None and job.sourcing_enabled and not job.demo:
                self._keep_sourced(record, previous)

        if self.store.mutate(job_id, change) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")

    def _keep_sourced(self, record: StoredJob, previous: Report) -> None:
        """After edits to a finished report, keep seller results for unchanged parts.

        Only lines that are new, or whose name, specs or build details changed, are searched
        again; a quantity change keeps its offers and only the costs are recomputed.
        """
        job = record.job
        before = {line.item.line_id: line for line in previous.lines}
        lines, search = [], []
        for item in job.items:
            old = before.get(item.line_id)
            if item.user_has_it:
                lines.append(
                    ReportLine(item=item.model_copy(deep=True), sourcing_status="already_owned")
                )
            elif (
                old is None
                or old.sourcing_status == "already_owned"
                or not same_part(old.item, item)
            ):
                search.append(item.line_id)
            else:
                lines.append(old.model_copy(update={"item": item.model_copy(deep=True)}, deep=True))
        previous.lines = lines
        update_costs(previous)
        job.report = previous
        job.error = None
        record.refresh_urls = None
        record.run_id = record.lease_until = None
        if not search:
            reassess_report(previous, job.project)
            apply_recommendations(previous, self.seller_penalty_inr)
            self._transition(job, "done", "Saved your changes; no new parts to search.")
            return
        if job.cost_estimate:
            # Each search for added parts is a new sourcing run with its own budget.
            job.cost_estimate.run_usd, job.cost_estimate.budget_reached = 0.0, False
        record.sourcing_scope = search
        count = len(search)
        self._transition(
            job,
            "resolving",
            f"Saved your changes; searching sellers for {count} new or changed "
            + ("part." if count == 1 else "parts."),
        )

    def edit_draft(
        self, job: Job, request: ConfirmJob, *, finalize: bool = False, reopen: bool = False
    ) -> None:
        # A finished report can be edited again; confirm then searches only what changed.
        if job.status != "awaiting_confirmation" and not (reopen and job.status == "done"):
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
                        # An AI buying spec describes the old name; a seed spec replaces it.
                        spec = items[edit.line_id].buyable_spec
                        if spec is not None and spec.origin != "user":
                            items[edit.line_id].buyable_spec = None
                        # AI-filled spec values were decided for the old part too.
                        items[edit.line_id].ai_specs = PartSpecs()
                    items[edit.line_id].raw_name = edit.raw_name
                if edit.buyable_spec is not None:
                    spec = edit.buyable_spec
                    items[edit.line_id].buyable_spec = spec.model_copy(
                        update={
                            "origin": "user",
                            # The schema leaves these list items unbounded for stored AI specs;
                            # bound what a client can save (`must` is a param name).
                            "must": [name[:60] for name in spec.must],
                            "reasons": [reason[:300] for reason in spec.reasons],
                        }
                    )
                if edit.qty is not None and (
                    edit.qty != items[edit.line_id].qty or items[edit.line_id].qty_as_needed
                ):
                    items[edit.line_id].qty = edit.qty
                    items[edit.line_id].qty_source = "user"
                    items[edit.line_id].qty_reason = None
                    items[edit.line_id].qty_as_needed = False
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
        # A removed line can no longer be ticked as received on the build page.
        job.build_received = [line_id for line_id in job.build_received if line_id in items]
        for item in job.items:
            try:
                item.clarifications = resolve_part(item).clarifications
            except ValueError as exc:
                raise JobError(
                    422, "INVALID_SPECS", "Name and part specifications conflict"
                ) from exc
        job.safety_flags = flags_for(job)
        from bharat_sourcer import build_guide, overview  # both import this module

        overview.mark_stale(job)  # a drawing of a different parts list is kept but marked stale
        build_guide.mark_stale(job)  # so are build steps written for the old list
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

        self._mutate(job_id, change)

    def _write_specs(self, job_id, run_id, claimed, pending, searched, ledger, save_cost):
        """One batched call writes AI buying specs for lines without one (older jobs).

        Only lines this run will source (within the part limit) are included. The specs are
        saved on the job's items so later runs and refreshes reuse them; on any failure the
        lines keep their seed specs. Returns `pending` with the new specs applied.
        """
        write_specs = getattr(self.sourcing, "write_specs", None)
        if write_specs is None:
            return pending
        limit = min(self.sourcing_max_parts, claimed.part_limit or self.sourcing_max_parts)
        sourced = [item for item in pending if not item.user_has_it][: max(0, limit - searched)]
        # Made-to-order lines are not bought from sellers, so they need no buying spec.
        sourced = [item for item in sourced if item.fabrication == "none"]
        targets = [item for item in sourced if item.buyable_spec is None]
        if not targets:
            return pending
        with attribute(ledger):
            written = write_specs(targets, claimed.job.project)
        if not written:
            if ledger.calls:
                self.store.mutate(job_id, save_cost)
            return pending
        names = {item.line_id: item.raw_name for item in targets}

        def save_specs(record: StoredJob):
            if record.run_id != run_id or record.job.status != "sourcing":
                return
            for item in record.job.items:
                spec = written.get(item.line_id)
                # Never replace a spec saved meanwhile, or describe a renamed line.
                if spec and item.buyable_spec is None and item.raw_name == names[item.line_id]:
                    item.buyable_spec = spec.model_copy(deep=True)
            save_cost(record)

        self.store.mutate(job_id, save_specs)

        def with_spec(item: BomItem) -> BomItem:
            spec = written.get(item.line_id)
            if spec is None or item.buyable_spec is not None:
                return item
            return item.model_copy(update={"buyable_spec": spec.model_copy(deep=True)})

        claimed.job.items = [with_spec(item) for item in claimed.job.items]
        return [with_spec(item) for item in pending]

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

        ledger = JobLedger(job_id, self.gemini_budget_usd, previous=claimed.job.cost_estimate)
        known_urls = claimed.refresh_urls or {}

        def save_cost(record: StoredJob) -> None:
            # The lease makes this run the only writer, so the running ledger is authoritative.
            if ledger.calls or ledger.cache_hits or record.job.cost_estimate:
                record.job.cost_estimate = ledger.snapshot()

        pending = self._write_specs(job_id, run_id, claimed, pending, searched, ledger, save_cost)

        def source_item(item, limited):
            if limited:
                return ReportLine(
                    item=item,
                    sourcing_status="not_run",
                    sourcing_error=ErrorDetail(
                        code="SOURCING_LIMIT", message="Per-job sourcing limit reached"
                    ),
                )
            # The pool runs each item in a copy of this context (request trace); the cost
            # attribution is entered inside the worker.
            with attribute(ledger, item.line_id):
                started = time.perf_counter()
                line = attributed_source(item)
                error = getattr(line, "sourcing_error", None)
                stage_finished(
                    "sourcing",
                    started,
                    str(getattr(line, "sourcing_status", "unknown")),
                    job_id=job_id,
                    line_id=item.line_id,
                    code=getattr(error, "code", None),
                )
                return line

        def attributed_source(item):
            try:
                fabricate = getattr(self.sourcing, "fabrication_line", None)
                if fabricate is not None and item.fabrication != "none":
                    made = fabricate(item, design_links(claimed.job, item.fabrication))
                    if made is not None:
                        return made
                refresh_known = getattr(self.sourcing, "refresh_known", None)
                if refresh_known and known_urls.get(item.line_id):
                    refreshed = refresh_known(item, claimed.job.items, known_urls[item.line_id])
                    if refreshed is not None:
                        return refreshed
                project_source = getattr(self.sourcing, "source_for_project", None)
                if project_source:
                    return project_source(item, claimed.job.items, project=claimed.job.project)
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

                self._mutate(job_id, acknowledge)
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
                    context = contextvars.copy_context()  # keeps the request's trace
                    futures.append(pool.submit(context.run, source_item, item, limited))
                for future in as_completed(futures):
                    line = future.result()

                    def checkpoint(record, result=line):
                        if record.run_id != run_id or record.job.status != "sourcing":
                            return
                        lines = {line.item.line_id: line for line in record.job.report.lines}
                        carry_selection(lines.get(result.item.line_id), result)
                        lines[result.item.line_id] = result
                        record.job.report.lines = [
                            lines[item.line_id]
                            for item in record.job.items
                            if item.line_id in lines
                        ]
                        update_costs(record.job.report)
                        save_cost(record)
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

            self._mutate(job_id, batch_complete)
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
            record.refresh_urls = None
            save_cost(record)
            record.job.report.summary = (
                "Sourcing finished. Compatibility compares declared specs only; review evidence "
                "and missing fields. Seller trust, tax and shipping remain unverified."
            )
            release_recommendations(record.job.report)
            if ledger.budget_reached:
                record.job.report.summary += (
                    " Some parts skipped paid search to stay within the job budget; refresh "
                    "them to continue."
                )
            reassess_report(record.job.report, record.job.project)
            # Recommend and apply a default selection per line (user choices are kept).
            apply_recommendations(record.job.report, self.seller_penalty_inr)
            # Same transaction as the transition, so redelivered work cannot repeat it.
            complete_refresh(record.job)
            self._transition(record.job, "done", "Sourcing report ready for review.")

        self._mutate(job_id, complete)
