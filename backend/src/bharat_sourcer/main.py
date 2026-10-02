from typing import Annotated

from fastapi import BackgroundTasks, FastAPI, Header, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from bharat_sourcer.config import Settings
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

JobToken = Annotated[str | None, Header(alias="X-Job-Token")]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    if not settings.demo_mode:
        raise RuntimeError("Only demo mode is implemented. Set BS_DEMO_MODE=true.")
    service = JobService()
    app = FastAPI(
        title="Bharat Sourcer API",
        version="0.1.0",
        description="Local demo API. Sample data only; jobs are lost on process restart.",
        responses={422: {"model": ErrorResponse}},
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
        return Health()

    @app.post("/v1/jobs", status_code=202, response_model=CreatedJob, tags=["jobs"])
    def create_job(body: CreateJob, tasks: BackgroundTasks):
        job, token = service.create(body)
        tasks.add_task(service.extract_demo, job.job_id)
        return CreatedJob(job_id=job.job_id, job_token=token, watch=f"/v1/jobs/{job.job_id}")

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
        tasks.add_task(service.finish_demo, job_id)
        return ConfirmationAccepted()

    return app


app = create_app()
