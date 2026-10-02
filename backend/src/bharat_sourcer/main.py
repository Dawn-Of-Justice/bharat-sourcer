import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from google.api_core.exceptions import GoogleAPICallError

from bharat_sourcer.config import Settings
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
)
from bharat_sourcer.storage import FirestoreJobStore, JobStore, MemoryJobStore, StorageError

JobToken = Annotated[str | None, Header(alias="X-Job-Token")]


def create_app(
    settings: Settings | None = None,
    extractor: Extractor | None = None,
    store: JobStore | None = None,
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
        settings.extraction_lease_s,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
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

        task = asyncio.create_task(recovery())
        try:
            yield
        finally:
            stop.set()
            await task

    app = FastAPI(
        title="Bharat Sourcer API",
        version="0.3.0",
        description="Demo or live YouTube extraction with optional Firestore job persistence.",
        lifespan=lifespan,
        responses={422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    app.state.job_service = service

    @app.exception_handler(StorageError)
    @app.exception_handler(GoogleAPICallError)
    async def storage_error_handler(request: Request, exc: StorageError):
        return JSONResponse(
            status_code=503,
            content={"error": {"code": "STORAGE_ERROR", "message": "Job storage operation failed"}},
        )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Job-Token"],
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
        tasks.add_task(service.extract, job.job_id)
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
        tasks.add_task(service.finish, job_id)
        return ConfirmationAccepted()

    return app


app = create_app()
