"""Owner exports and revocable, read-only share links.

A share token is `<job_id>.<secret>`; only its SHA-256 hash is stored on the job, so a
lookup reads one document by id and needs no query or index. Shared reads never charge
the owner's quotas and never start work; they are bounded per client IP instead.
"""

import secrets
import time
from datetime import UTC, datetime
from hashlib import sha256

from fastapi import Request, Response
from fastapi.responses import HTMLResponse

from bharat_sourcer.access import ProjectAccess
from bharat_sourcer.export import SharedProject, redact, to_csv, to_html
from bharat_sourcer.jobs import JobError
from bharat_sourcer.schemas import ErrorResponse, Model, now

SHARED_DAILY_READS = 300
SHARED_MINUTE_READS = 30
# Uniform response for unknown, malformed and revoked tokens.
NOT_FOUND = (404, "SHARE_NOT_FOUND", "Share link not found or revoked")


class ShareLink(Model):
    share_token: str
    path: str
    created_at: datetime


class ShareStatus(Model):
    active: bool
    created_at: datetime | None = None


def token_hash(token: str) -> str:
    return sha256(token.encode()).hexdigest()


def filename(view: SharedProject, extension: str) -> str:
    return f"bharat-sourcer-bom{'-demo' if view.demo else ''}.{extension}"


def csv_response(view: SharedProject) -> Response:
    return Response(
        content=to_csv(view).encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename(view, "csv")}"'},
    )


def html_response(view: SharedProject) -> HTMLResponse:
    return HTMLResponse(
        to_html(view),
        headers={
            "Content-Disposition": f'inline; filename="{filename(view, "html")}"',
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'self'"
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


def add_share_routes(app, service, access):
    def shared(request: Request, share_token: str) -> SharedProject:
        timestamp = time.time()
        day = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d")
        ip = access.ip_key(request)
        limits = {
            f"shared-{day}-{ip}": SHARED_DAILY_READS,
            f"shared-burst-{int(timestamp) // 60}-{ip}": SHARED_MINUTE_READS,
        }
        if not service.store.consume(limits):
            raise JobError(429, "USAGE_LIMIT", "Too many shared-link reads; retry later")
        job_id, _, secret = share_token.partition(".")
        if len(share_token) > 128 or not secret:
            raise JobError(*NOT_FOUND)
        try:
            service._validate_id(job_id)
        except JobError as exc:
            raise JobError(*NOT_FOUND) from exc
        record = service.store.get(job_id)
        if (
            record is None
            or record.share_token_hash is None
            or not secrets.compare_digest(record.share_token_hash, token_hash(share_token))
        ):
            raise JobError(*NOT_FOUND)
        return redact(record.job)

    @app.get(
        "/v1/jobs/{job_id}/export.csv",
        tags=["export"],
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}, 404: {"model": ErrorResponse}},
    )
    def export_csv(job_id: str, x_job_token: ProjectAccess = None):
        return csv_response(redact(service.get(job_id, x_job_token)))

    @app.get(
        "/v1/jobs/{job_id}/export.html",
        tags=["export"],
        response_class=HTMLResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def export_html(job_id: str, x_job_token: ProjectAccess = None):
        return html_response(redact(service.get(job_id, x_job_token)))

    @app.get(
        "/v1/jobs/{job_id}/share",
        response_model=ShareStatus,
        tags=["export"],
        responses={404: {"model": ErrorResponse}},
    )
    def share_status(job_id: str, x_job_token: ProjectAccess = None):
        service._validate_id(job_id)
        record = service.store.get(job_id)
        service._authorized(record, x_job_token)
        active = bool(record.share_token_hash)
        return ShareStatus(active=active, created_at=record.shared_at if active else None)

    @app.post(
        "/v1/jobs/{job_id}/share",
        status_code=201,
        response_model=ShareLink,
        tags=["export"],
        responses={404: {"model": ErrorResponse}},
    )
    def create_share(job_id: str, x_job_token: ProjectAccess = None):
        service._validate_id(job_id)
        token = f"{job_id}.{secrets.token_urlsafe(32)}"
        created = now()

        def change(record):
            service._authorized(record, x_job_token)
            # Creating again rotates the link; the previous token stops working.
            record.share_token_hash = token_hash(token)
            record.shared_at = created

        if service.store.mutate(job_id, change) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return ShareLink(share_token=token, path=f"/v1/shared/{token}", created_at=created)

    @app.delete(
        "/v1/jobs/{job_id}/share",
        status_code=204,
        tags=["export"],
        responses={404: {"model": ErrorResponse}},
    )
    def revoke_share(job_id: str, x_job_token: ProjectAccess = None):
        service._validate_id(job_id)

        def change(record):
            service._authorized(record, x_job_token)
            record.share_token_hash = None
            record.shared_at = None

        if service.store.mutate(job_id, change) is None:
            raise JobError(404, "JOB_NOT_FOUND", "Job not found or token invalid")
        return Response(status_code=204)

    shared_headers = {"Referrer-Policy": "no-referrer"}

    @app.get(
        "/v1/shared/{share_token}",
        response_model=SharedProject,
        tags=["export"],
        responses={404: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def shared_project(share_token: str, request: Request, response: Response):
        response.headers.update(shared_headers)
        return shared(request, share_token)

    @app.get(
        "/v1/shared/{share_token}/export.csv",
        tags=["export"],
        response_class=Response,
        responses={200: {"content": {"text/csv": {}}}, 404: {"model": ErrorResponse}},
    )
    def shared_csv(share_token: str, request: Request):
        result = csv_response(shared(request, share_token))
        result.headers.update(shared_headers)
        return result

    @app.get(
        "/v1/shared/{share_token}/export.html",
        tags=["export"],
        response_class=HTMLResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def shared_html(share_token: str, request: Request):
        result = html_response(shared(request, share_token))
        result.headers.update(shared_headers)
        return result
