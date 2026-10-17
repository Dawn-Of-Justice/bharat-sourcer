import asyncio
import logging
import os
import re
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import timedelta

from fastapi import BackgroundTasks, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse
from google.api_core.exceptions import GoogleAPICallError

from bharat_sourcer import compile_check
from bharat_sourcer.access import Access, ProjectAccess, add_access_routes
from bharat_sourcer.build_guide import BuildGuideService
from bharat_sourcer.code_patches import CodePatchService
from bharat_sourcer.compile_check import CompileService, RunnerResult
from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import Assistant, ConversationService, GeminiAssistant
from bharat_sourcer.dispatch import CloudDispatcher, Work, work_once
from bharat_sourcer.extraction import Extractor, GeminiExtractor
from bharat_sourcer.gemini_extras import GeminiExtras, add_extras_routes
from bharat_sourcer.guards import BodyLimit
from bharat_sourcer.identity import Principal
from bharat_sourcer.images import PartImageService
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.markets import MarketsService, add_markets_routes
from bharat_sourcer.observability import (
    TraceMiddleware,
    configure_logging,
    fields,
    log_event,
    scope_trace,
    use_trace,
)
from bharat_sourcer.overview import OverviewService
from bharat_sourcer.plans import cart_plans, set_import_references
from bharat_sourcer.reconcile import GeminiReconciler
from bharat_sourcer.schemas import (
    BuildGuide,
    BuildProgress,
    CartPlans,
    CodePatch,
    CodePatchRequest,
    CompileBoards,
    CompileRequest,
    ConfirmationAccepted,
    ConfirmJob,
    CreatedJob,
    CreateJob,
    ErrorResponse,
    Health,
    ImageRequest,
    Job,
    PartImages,
    ProjectOverview,
    ProposalDecision,
    RefreshOffers,
    ResistorInputs,
    SelectOffers,
    SendMessage,
    SetImportReferences,
    UpdateJobSpecs,
    UpdateProject,
    now,
)
from bharat_sourcer.sharing import add_share_routes
from bharat_sourcer.sourcing import seller_search
from bharat_sourcer.sourcing.buyer import GeminiBuyer
from bharat_sourcer.sourcing.cache import build_cache
from bharat_sourcer.sourcing.cart_engine import CartEngine
from bharat_sourcer.sourcing.fabrication import FabricationFinder
from bharat_sourcer.sourcing.fetch import SafeFetcher
from bharat_sourcer.sourcing.judge import GeminiJudge
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.sourcing.research import GeminiResearch
from bharat_sourcer.sourcing.service import GeminiDiscovery, SourcingService
from bharat_sourcer.sourcing.spec_writer import GeminiSpecWriter
from bharat_sourcer.sourcing.trust import TrustChecker
from bharat_sourcer.spec_fill import GeminiSpecFiller
from bharat_sourcer.storage import (
    FirestoreJobStore,
    JobStore,
    MemoryJobStore,
    Retention,
    StorageError,
)
from bharat_sourcer.streaming import snapshots

JobToken = ProjectAccess
# Body cap for the parts-bin scan route: above ScanRequest's 7,000,000-character photo.
SCAN_BODY_BYTES = 8_388_608

# Sent on every API response (the web server in frontend/server.mjs adds its own set too).
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}


def create_app(
    settings: Settings | None = None,
    extractor: Extractor | None = None,
    store: JobStore | None = None,
    assistant: Assistant | None = None,
    identity_verifier=None,
) -> FastAPI:
    settings = settings or Settings()
    # Uvicorn configures its own loggers, not the root logger. Without a handler, Python's
    # WARNING-only lastResort handler silently drops search diagnostics. JSON lines for Cloud
    # Logging on Cloud Run, plain text locally (observability.py).
    configure_logging(settings.gcp_project, os.getenv("BS_LOG_LEVEL", "INFO"))
    live_extractor = None if settings.demo_mode else (extractor or GeminiExtractor(settings))
    retention = Retention(settings.guest_retention_days, settings.account_retention_days)
    if store is None:
        store = (
            FirestoreJobStore(
                settings.gcp_project,
                settings.firestore_database,
                settings.firestore_collection,
                retention,
            )
            if settings.storage_backend == "firestore"
            else MemoryJobStore(retention)
        )
    else:
        store.retention = retention
    # Cross-job cache for paid sourcing results, beside the job store (cost-controls.md).
    shared_cache = build_cache(settings, store)
    searcher = seller_search.from_settings(settings, cache=shared_cache)
    polite = (
        searcher.politeness
        if searcher
        else Politeness(page_ttl_s=settings.seller_page_cache_s, cache=shared_cache)
    )
    service = JobService(
        live_extractor,
        settings.gemini_model if live_extractor else None,
        store,
        max(settings.extraction_lease_s, int(3 * settings.extraction_timeout_s + 60)),
        refresh_unlimited_uids=settings.refresh_unlimited_uids,
        sourcing=(
            SourcingService(
                GeminiDiscovery(settings),
                researcher=GeminiResearch(settings, cache=shared_cache)
                if settings.research_enabled
                else None,
                followup_enabled=settings.research_followup_enabled,
                trust=TrustChecker(fetcher=polite.wrap(None))
                if settings.seller_trust_enabled
                else None,
                seller_search=searcher,
                fetcher=polite.wrap(None),
                seller_fetch_budget=settings.seller_search_fetch_budget,
                seller_limit=settings.seller_search_per_seller,
                judge=GeminiJudge(settings, cache=shared_cache) if settings.judge_enabled else None,
                spec_writer=GeminiSpecWriter(settings, cache=shared_cache)
                if settings.spec_writer_enabled
                else None,
                buyer=GeminiBuyer(settings) if settings.buyer_enabled else None,
                buyer_rounds=settings.buyer_search_rounds,
                carts=CartEngine(settings, cache=shared_cache)
                if settings.cart_engine_enabled
                else None,
                fabrication=FabricationFinder(settings, polite.wrap(None), cache=shared_cache)
                if settings.fabrication_enabled
                else None,
            )
            if settings.sourcing_enabled and not settings.demo_mode
            else None
        ),
        sourcing_max_parts=settings.sourcing_max_parts,
        sourcing_lease_seconds=settings.sourcing_lease_s,
        sourcing_parallelism=settings.sourcing_parallelism,
        seller_penalty_inr=settings.recommend_seller_penalty_inr,
        gemini_budget_usd=settings.job_gemini_budget_usd,
        spec_filler=GeminiSpecFiller(settings, cache=shared_cache)
        if live_extractor and settings.spec_fill_enabled and settings.gemini_api_key
        else None,
        reconciler=GeminiReconciler(settings, cache=shared_cache)
        if live_extractor and settings.reconcile_enabled and settings.gemini_api_key
        else None,
    )

    conversation = ConversationService(
        service, assistant or (GeminiAssistant(settings) if not settings.demo_mode else None)
    )

    dispatcher = CloudDispatcher(settings) if settings.dispatch_backend == "cloud_tasks" else None

    def dispatch(tasks, function, key, kind="workflow"):
        if dispatcher:
            dispatcher.notify(key, kind)
        else:
            tasks.add_task(function, key)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if dispatcher:
            yield
            return
        stop = asyncio.Event()

        async def recovery():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(service.recover)
                except Exception as exc:
                    logging.getLogger(__name__).error("Recovery failed: %s", type(exc).__name__)
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), settings.recovery_interval_s)

        async def chat_recovery():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(conversation.recover)
                except Exception as exc:
                    logging.getLogger(__name__).error(
                        "Chat recovery failed: %s", type(exc).__name__
                    )
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), settings.recovery_interval_s)

        task = asyncio.create_task(recovery())
        chat_task = asyncio.create_task(chat_recovery())
        try:
            yield
        finally:
            stop.set()
            await task
            await chat_task

    app = FastAPI(
        title="Bharat Sourcer API",
        version="0.43.0",
        description=(
            "Demo or live YouTube and project-page extraction with optional Firestore job "
            "persistence."
        ),
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    app.state.job_service = service
    app.state.shared_cache = shared_cache
    images = PartImageService(settings, service)
    code_patches = CodePatchService(settings, service, SafeFetcher())
    app.state.code_patch_service = code_patches
    # Project overview: drawn after extraction (inline locally, its own Cloud Task in cloud
    # mode so the extraction task stays short) and on the owner's request.
    overviews = OverviewService(settings, service, SafeFetcher(), cache=shared_cache)
    if dispatcher:
        overviews.launch = lambda key: dispatcher.notify(key, "overview")
    service.overviews = overviews
    app.state.overview_service = overviews
    # Build guide: written only on the owner's request (inline locally, a Cloud Task in
    # cloud mode).
    guides = BuildGuideService(settings, service, cache=shared_cache)
    if dispatcher:
        guides.launch = lambda key: dispatcher.notify(key, "build_guide")
    app.state.build_guide_service = guides
    compiles = CompileService(settings, service, code_patches)
    app.state.compile_service = compiles
    app.state.image_service = images
    app.state.conversation_service = conversation
    access = Access(settings, service, identity_verifier)
    app.state.access = access
    add_access_routes(app, access)
    add_share_routes(app, service, access)
    extras = GeminiExtras(settings, service)
    app.state.extras = extras
    add_extras_routes(app, extras)
    markets = MarketsService(settings, service, shared_cache)
    app.state.markets = markets
    add_markets_routes(app, markets)

    @app.exception_handler(StorageError)
    @app.exception_handler(GoogleAPICallError)
    async def storage_error_handler(request: Request, exc: StorageError):
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "STORAGE_ERROR", "message": "Job storage operation failed"}},
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception):
        # Never echo exception text or tracebacks; the server log keeps the traceback.
        route = getattr(request.scope.get("route"), "path", "unmatched")
        # Runs outside the trace middleware (Starlette's outermost error layer).
        with use_trace(scope_trace(request.scope)):
            logging.getLogger(__name__).error(
                "UNHANDLED_ERROR route=%s type=%s",
                route,
                type(exc).__name__,
                extra=fields(route=route, type=type(exc).__name__),
            )
        return JSONResponse(
            status_code=500,
            content={"error": {"code": "INTERNAL_ERROR", "message": "Internal server error"}},
        )

    @app.middleware("http")
    async def integration_access(request: Request, call_next):
        if settings.integration_key and request.url.path.startswith("/v1/"):
            # Header values are latin-1 decoded; compare bytes so non-ASCII input is a
            # plain mismatch (compare_digest raises TypeError on non-ASCII str).
            supplied = request.headers.get("X-Integration-Key", "").encode("latin-1")
            expected = settings.integration_key.get_secret_value().encode()
            if not secrets.compare_digest(supplied, expected):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "INTEGRATION_KEY_REQUIRED",
                            "message": "Integration key required",
                        }
                    },
                )
        if settings.auth_enabled and request.url.path.startswith("/v1/"):
            try:
                if request.method in {"POST", "DELETE"} and request.url.path.startswith("/v1/jobs"):
                    access.csrf(request)
                    principal = await asyncio.to_thread(access.identity, request)
                    parts = request.url.path.split("/")
                    if len(parts) > 3:
                        await asyncio.to_thread(service.get, parts[3], principal)
                    # Users must always be able to stop work after exhausting their quota.
                    # Image fallbacks have separate generation quotas; broken-image retries
                    # must not consume the project action budget; nor do title/description edits
                    # or creating/revoking a read-only share link (no work is started).
                    # Gemini extras (explain, zoom, scan) are charged by their own quotas.
                    if not request.url.path.endswith(
                        (
                            "/pause",
                            "/image",
                            "/project",
                            "/share",
                            "/explain",
                            "/zoom",
                            "/scan",
                            "/code-patch/accept",
                        )
                    ):
                        await asyncio.to_thread(access.charge, request, principal)
            except JobError as exc:
                return JSONResponse(
                    status_code=exc.status,
                    content={"error": {"code": exc.code, "message": exc.message}},
                    headers={"Retry-After": str(exc.retry_after)} if exc.status == 429 else {},
                )
            except (StorageError, GoogleAPICallError):
                return JSONResponse(
                    status_code=503,
                    content={
                        "error": {
                            "code": "USAGE_STORE_UNAVAILABLE",
                            "message": "Usage checks unavailable; retry later",
                        }
                    },
                )
        result = await call_next(request)
        if request.url.path.startswith("/v1/"):
            result.headers["Cache-Control"] = "no-store"
        return result

    # Inside CORS so a 413 still carries CORS headers for allowed origins.
    app.add_middleware(
        BodyLimit,
        limit=settings.max_body_bytes,
        # The scan photo is base64 JSON (ScanRequest caps it at 7,000,000 characters).
        overrides=((r"/v1/jobs/[^/]+/scan", SCAN_BODY_BYTES),),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=[
            "Content-Type",
            "X-Job-Token",
            "X-Integration-Key",
            "Authorization",
            "X-Requested-With",
        ],
        allow_credentials=True,
        expose_headers=["Retry-After"],
    )

    # Registered last so it wraps CORS and the access checks: preflights, 401s and errors get it.
    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        result = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            result.headers.setdefault(name, value)
        return result

    # Outermost: every log line of a request (middleware, routes, background tasks) carries
    # its X-Cloud-Trace-Context / traceparent trace. Adds no headers.
    app.add_middleware(TraceMiddleware)

    @app.exception_handler(JobError)
    async def job_error_handler(request: Request, exc: JobError):
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
            headers={"Retry-After": str(exc.retry_after)} if exc.status == 429 else {},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError):
        message = "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}" for error in exc.errors()
        )
        return JSONResponse(
            status_code=422, content={"error": {"code": "VALIDATION_ERROR", "message": message}}
        )

    @app.get("/health", response_model=Health, tags=["health"])
    @app.get("/healthz", response_model=Health, tags=["health"])
    def health():
        return Health(
            mode="demo" if settings.demo_mode else "live", storage=settings.storage_backend
        )

    @app.post(
        "/v1/jobs",
        status_code=202,
        response_model=CreatedJob,
        tags=["jobs"],
        responses={400: {"model": ErrorResponse}},
    )
    def create_job(body: CreateJob, tasks: BackgroundTasks, x_job_token: JobToken = None):
        principal = x_job_token if isinstance(x_job_token, Principal) else None
        job, token = service.create(
            body,
            principal,
            settings.guest_part_limit if principal and principal.guest else None,
        )
        dispatch(tasks, service.extract, job.job_id)
        return CreatedJob(
            job_id=job.job_id, job_token=token, watch=f"/v1/jobs/{job.job_id}", demo=job.demo
        )

    @app.get(
        "/v1/jobs/{job_id}",
        response_model=Job,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}},
    )
    def get_job(job_id: str, x_job_token: JobToken = None):
        return service.get(job_id, x_job_token)

    @app.get("/v1/jobs/{job_id}/parts/{line_id}/image", response_model=PartImages, tags=["images"])
    def get_image(job_id: str, line_id: str, x_job_token: JobToken = None):
        return images.resolve(job_id, line_id, x_job_token)

    @app.post("/v1/jobs/{job_id}/parts/{line_id}/image", response_model=PartImages, tags=["images"])
    def fallback_image(job_id: str, line_id: str, body: ImageRequest, x_job_token: JobToken = None):
        return images.resolve(job_id, line_id, x_job_token, body.failed_urls, generate=True)

    @app.get(
        "/v1/jobs/{job_id}/overview",
        response_model=ProjectOverview,
        tags=["overview"],
        responses={404: {"model": ErrorResponse}},
    )
    def get_overview(job_id: str, x_job_token: JobToken = None):
        return overviews.get(job_id, x_job_token)

    @app.post(
        "/v1/jobs/{job_id}/overview",
        response_model=ProjectOverview,
        tags=["overview"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def request_overview(job_id: str, tasks: BackgroundTasks, x_job_token: JobToken = None):
        overview, started = overviews.request(job_id, x_job_token)
        if started:
            dispatch(tasks, overviews.generate, job_id, "overview")
        return overview

    @app.post(
        "/v1/jobs/{job_id}/build-progress",
        response_model=Job,
        tags=["build"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def set_build_progress(job_id: str, body: BuildProgress, x_job_token: JobToken = None):
        return service.set_build_progress(job_id, x_job_token, body)

    @app.get(
        "/v1/jobs/{job_id}/build-guide",
        response_model=BuildGuide,
        tags=["build"],
        responses={404: {"model": ErrorResponse}},
    )
    def get_build_guide(job_id: str, x_job_token: JobToken = None):
        return guides.get(job_id, x_job_token)

    @app.post(
        "/v1/jobs/{job_id}/build-guide",
        response_model=BuildGuide,
        tags=["build"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def request_build_guide(job_id: str, tasks: BackgroundTasks, x_job_token: JobToken = None):
        guide, started = guides.request(job_id, x_job_token)
        if started:
            dispatch(tasks, guides.generate, job_id, "build_guide")
        return guide

    @app.post(
        "/v1/jobs/{job_id}/lines/{line_id}/code-patch",
        response_model=CodePatch,
        tags=["code"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def create_code_patch(
        job_id: str, line_id: str, body: CodePatchRequest, x_job_token: JobToken = None
    ):
        return code_patches.create(job_id, line_id, x_job_token, body)

    @app.post(
        "/v1/jobs/{job_id}/lines/{line_id}/code-patch/accept",
        response_model=CodePatch,
        tags=["code"],
        responses={404: {"model": ErrorResponse}},
    )
    def accept_code_patch(job_id: str, line_id: str, x_job_token: JobToken = None):
        return code_patches.accept(job_id, line_id, x_job_token)

    @app.get(
        "/v1/jobs/{job_id}/lines/{line_id}/code-patch.zip",
        response_class=Response,
        tags=["code"],
        responses={
            200: {"content": {"application/zip": {}}},
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
        },
    )
    def download_code_patch(job_id: str, line_id: str, x_job_token: JobToken = None):
        content = code_patches.download(job_id, line_id, x_job_token)
        name = re.sub(r"[^A-Za-z0-9_-]", "_", line_id)[:40]
        return Response(
            content,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="code-patch-{name}.zip"'},
        )

    @app.get("/v1/compile/boards", response_model=CompileBoards, tags=["code"])
    def compile_boards():
        return compiles.boards()

    @app.post(
        "/v1/jobs/{job_id}/lines/{line_id}/code-patch/compile",
        status_code=202,
        response_model=CodePatch,
        tags=["code"],
        responses={
            404: {"model": ErrorResponse},
            409: {"model": ErrorResponse},
            429: {"model": ErrorResponse},
        },
    )
    def compile_code_patch(
        job_id: str, line_id: str, body: CompileRequest, x_job_token: JobToken = None
    ):
        return compiles.request(job_id, line_id, x_job_token, body)

    @app.get("/internal/compile/{run_id}", include_in_schema=False)
    def compile_bundle(run_id: str, request: Request):
        compile_check.authorize_runner(compiles, request.headers.get("Authorization"))
        return compiles.bundle(run_id)

    @app.post("/internal/compile/{run_id}/result", include_in_schema=False)
    def compile_result(run_id: str, body: RunnerResult, request: Request):
        compile_check.authorize_runner(compiles, request.headers.get("Authorization"))
        return compiles.result(run_id, body)

    @app.post(
        "/v1/jobs/{job_id}/confirm",
        status_code=202,
        response_model=ConfirmationAccepted,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def confirm_job(
        job_id: str, body: ConfirmJob, tasks: BackgroundTasks, x_job_token: JobToken = None
    ):
        service.confirm(job_id, x_job_token, body)
        dispatch(tasks, service.finish, job_id)
        return ConfirmationAccepted()

    @app.post(
        "/v1/jobs/{job_id}/pause",
        response_model=Job,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def pause_job(job_id: str, x_job_token: JobToken = None):
        return service.pause(job_id, x_job_token)

    @app.post(
        "/v1/jobs/{job_id}/resume",
        status_code=202,
        response_model=Job,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def resume_job(job_id: str, tasks: BackgroundTasks, x_job_token: JobToken = None):
        job = service.resume(job_id, x_job_token)
        dispatch(tasks, service.finish, job_id)
        return job

    @app.post(
        "/v1/jobs/{job_id}/selections",
        response_model=Job,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def select_offers(job_id: str, body: SelectOffers, x_job_token: JobToken = None):
        return service.select_offers(job_id, x_job_token, body)

    @app.get(
        "/v1/jobs/{job_id}/plans",
        response_model=CartPlans,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def get_plans(job_id: str, x_job_token: JobToken = None):
        return cart_plans(service, job_id, x_job_token)

    @app.post(
        "/v1/jobs/{job_id}/import-references",
        response_model=Job,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def import_references(job_id: str, body: SetImportReferences, x_job_token: JobToken = None):
        return set_import_references(service, job_id, x_job_token, body)

    @app.post(
        "/v1/jobs/{job_id}/refresh",
        status_code=202,
        response_model=ConfirmationAccepted,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def refresh_offers(
        job_id: str, body: RefreshOffers, tasks: BackgroundTasks, x_job_token: JobToken = None
    ):
        service.refresh_offers(job_id, x_job_token, body)
        dispatch(tasks, service.finish, job_id)
        return ConfirmationAccepted()

    @app.post(
        "/v1/jobs/{job_id}/project",
        response_model=Job,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
    )
    def update_project(job_id: str, body: UpdateProject, x_job_token: JobToken = None):
        return service.update_project(job_id, x_job_token, body)

    @app.post(
        "/v1/jobs/{job_id}/specs",
        response_model=Job,
        tags=["jobs"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def update_specs(job_id: str, body: UpdateJobSpecs, x_job_token: JobToken = None):
        return service.update_specs(job_id, x_job_token, body)

    @app.post(
        "/v1/jobs/{job_id}/messages",
        status_code=202,
        response_model=Job,
        tags=["conversation"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def send_message(
        job_id: str, body: SendMessage, tasks: BackgroundTasks, x_job_token: JobToken = None
    ):
        job = conversation.send(job_id, x_job_token, body)
        dispatch(tasks, conversation.process, job_id, "chat")
        return job

    @app.post(
        "/v1/jobs/{job_id}/messages/{message_id}/decision",
        response_model=Job,
        tags=["conversation"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def decide_proposal(
        job_id: str,
        message_id: str,
        body: ProposalDecision,
        tasks: BackgroundTasks,
        x_job_token: JobToken = None,
    ):
        job = conversation.decide(job_id, x_job_token, message_id, body)
        if body.action == "accept" and job.status == "resolving":
            dispatch(tasks, service.finish, job_id)
        return job

    @app.get(
        "/v1/jobs/{job_id}/stream",
        tags=["conversation"],
        response_class=StreamingResponse,
        responses={
            200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}},
            404: {"model": ErrorResponse},
        },
    )
    def stream_job(job_id: str, request: Request, x_job_token: JobToken = None):
        service.get(job_id, x_job_token)
        return StreamingResponse(
            snapshots(service, job_id, x_job_token, request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.post(
        "/v1/jobs/{job_id}/resistor-advice",
        response_model=Job,
        tags=["conversation"],
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def resistor_advice(job_id: str, body: ResistorInputs, x_job_token: JobToken = None):
        return conversation.resistor_advice(job_id, x_job_token, body)

    def authorize_worker(request):
        if not dispatcher or not dispatcher.authorize(request.headers.get("Authorization")):
            raise JobError(401, "WORKER_AUTH_REQUIRED", "Worker identity required")

    @app.post("/internal/work", include_in_schema=False)
    def internal_work(body: Work, request: Request):
        authorize_worker(request)
        complete = work_once(service, conversation, body, overviews, guides)
        return JSONResponse(status_code=200 if complete else 503, content={"complete": complete})

    @app.post("/internal/sweep", include_in_schema=False)
    def internal_sweep(request: Request):
        authorize_worker(request)
        return sweep_pending()

    def sweep_pending():
        """Bounded redispatch; one failing job or enqueue never blocks the rest."""
        log = logging.getLogger(__name__)
        keys = service.store.pending(settings.sweep_limit + 1)
        stats = {
            "dispatched": 0,
            "failed": 0,
            "stale": 0,
            "truncated": len(keys) > settings.sweep_limit,
        }
        threshold = now() - timedelta(minutes=settings.queue_age_alert_minutes)
        for key in keys[: settings.sweep_limit]:
            try:
                record = service.store.get(key)
                if record is None:
                    continue
                kinds = []
                if record.job.status in {"queued", "extracting", "resolving", "sourcing"}:
                    kinds.append("workflow")
                if record.job.chat_state in {"queued", "thinking"}:
                    kinds.append("chat")
                if kinds and record.job.updated_at < threshold:
                    stats["stale"] += 1
                    age = int((now() - record.job.updated_at).total_seconds())
                    log.warning(
                        "QUEUE_AGE_EXCEEDED job=%s kinds=%s age_s=%d",
                        key,
                        ",".join(kinds),
                        age,
                        extra=fields(job_id=key, kinds=kinds, age_s=age),
                    )
                for kind in kinds:
                    try:
                        dispatcher.enqueue(key, kind, sweep=True)
                        stats["dispatched"] += 1
                    except Exception as exc:
                        stats["failed"] += 1
                        log.error(
                            "TASK_ENQUEUE_FAILED job=%s kind=%s type=%s",
                            key,
                            kind,
                            type(exc).__name__,
                            extra=fields(job_id=key, kind=kind, type=type(exc).__name__),
                        )
            except (StorageError, GoogleAPICallError) as exc:
                stats["failed"] += 1
                log.error(
                    "SWEEP_READ_FAILED job=%s type=%s",
                    key,
                    type(exc).__name__,
                    extra=fields(job_id=key, type=type(exc).__name__),
                )
        if stats["truncated"]:
            log.warning(
                "SWEEP_TRUNCATED limit=%d",
                settings.sweep_limit,
                extra=fields(limit=settings.sweep_limit),
            )
        return {"status": "ok"} | stats | {"retention": retention_pass()}

    def retention_pass():
        """Bounded retention batch (docs/contracts/retention-and-deletion.md); a failure
        never fails the redispatch sweep. Events: backend/infra/observability.md."""
        try:
            result = service.store.retention_pass(settings.retention_batch)
        except (StorageError, GoogleAPICallError) as exc:
            log_event("RETENTION_PASS_FAILED", logging.ERROR, type=type(exc).__name__)
            return {"failed": True}
        log_event(
            "RETENTION_PASS",
            deleted=result["deleted"],
            backfilled=result["backfilled"],
            scanned=result["scanned"],
            complete=result["complete"],
        )
        return result

    return app


app = create_app()
