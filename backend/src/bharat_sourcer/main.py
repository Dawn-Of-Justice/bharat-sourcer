import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from google.api_core.exceptions import GoogleAPICallError

from bharat_sourcer.config import Settings
from bharat_sourcer.conversation import Assistant, ConversationService, GeminiAssistant
from bharat_sourcer.dispatch import CloudDispatcher, Work, work_once
from bharat_sourcer.extraction import Extractor, GeminiExtractor
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.schemas import (
    ConfirmationAccepted,
    ConfirmJob,
    CreatedJob,
    CreateJob,
    ErrorResponse,
    Health,
    Job,
    ProposalDecision,
    RefreshOffers,
    ResistorInputs,
    SelectOffers,
    SendMessage,
    UpdateJobSpecs,
)
from bharat_sourcer.sourcing.research import GeminiResearch
from bharat_sourcer.sourcing.service import GeminiDiscovery, SourcingService
from bharat_sourcer.storage import FirestoreJobStore, JobStore, MemoryJobStore, StorageError
from bharat_sourcer.streaming import snapshots

JobToken = Annotated[str | None, Header(alias="X-Job-Token")]


def create_app(
    settings: Settings | None = None,
    extractor: Extractor | None = None,
    store: JobStore | None = None,
    assistant: Assistant | None = None,
) -> FastAPI:
    settings = settings or Settings()
    live_extractor = None if settings.demo_mode else (extractor or GeminiExtractor(settings))
    if store is None:
        store = (
            FirestoreJobStore(
                settings.gcp_project, settings.firestore_database, settings.firestore_collection
            )
            if settings.storage_backend == "firestore"
            else MemoryJobStore()
        )
    service = JobService(
        live_extractor,
        settings.gemini_model if live_extractor else None,
        store,
        max(settings.extraction_lease_s, int(3 * settings.extraction_timeout_s + 60)),
        sourcing=(
            SourcingService(
                GeminiDiscovery(settings),
                researcher=GeminiResearch(settings) if settings.research_enabled else None,
                followup_enabled=settings.research_followup_enabled,
            )
            if settings.sourcing_enabled and not settings.demo_mode
            else None
        ),
        sourcing_max_parts=settings.sourcing_max_parts,
        sourcing_lease_seconds=settings.sourcing_lease_s,
        sourcing_parallelism=settings.sourcing_parallelism,
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
                try:
                    await asyncio.wait_for(stop.wait(), settings.recovery_interval_s)
                except TimeoutError:
                    pass

        async def chat_recovery():
            while not stop.is_set():
                try:
                    await asyncio.to_thread(conversation.recover)
                except Exception as exc:
                    logging.getLogger(__name__).error(
                        "Chat recovery failed: %s", type(exc).__name__
                    )
                try:
                    await asyncio.wait_for(stop.wait(), settings.recovery_interval_s)
                except TimeoutError:
                    pass

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
        version="0.16.1",
        description="Demo or live YouTube extraction with optional Firestore job persistence.",
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    app.state.job_service = service
    app.state.conversation_service = conversation

    @app.exception_handler(StorageError)
    @app.exception_handler(GoogleAPICallError)
    async def storage_error_handler(request: Request, exc: StorageError):
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "STORAGE_ERROR", "message": "Job storage operation failed"}},
        )

    @app.middleware("http")
    async def integration_access(request: Request, call_next):
        if settings.integration_key and request.url.path.startswith("/v1/"):
            supplied = request.headers.get("X-Integration-Key", "")
            if not secrets.compare_digest(supplied, settings.integration_key.get_secret_value()):
                return JSONResponse(
                    status_code=401,
                    content={
                        "error": {
                            "code": "INTEGRATION_KEY_REQUIRED",
                            "message": "Integration key required",
                        }
                    },
                )
        return await call_next(request)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Job-Token", "X-Integration-Key"],
    )

    @app.exception_handler(JobError)
    async def job_error_handler(request: Request, exc: JobError):
        return JSONResponse(
            status_code=exc.status,
            content={"error": {"code": exc.code, "message": exc.message}},
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
    def create_job(body: CreateJob, tasks: BackgroundTasks):
        job, token = service.create(body)
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
        complete = work_once(service, conversation, body)
        return JSONResponse(status_code=200 if complete else 503, content={"complete": complete})

    @app.post("/internal/sweep", include_in_schema=False)
    def internal_sweep(request: Request):
        authorize_worker(request)
        for key in service.store.pending():
            record = service.store.get(key)
            if record is None:
                continue
            if record.job.status in {"queued", "extracting", "resolving", "sourcing"}:
                dispatcher.enqueue(key, "workflow", sweep=True)
            if record.job.chat_state in {"queued", "thinking"}:
                dispatcher.enqueue(key, "chat", sweep=True)
        return {"status": "ok"}

    return app


app = create_app()
