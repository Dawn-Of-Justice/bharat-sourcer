"""Account and guest access, project listing, claiming and shared usage limits."""

import hashlib
import hmac
import ipaddress
import math
import time
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Query, Request, Response
from pydantic import Field

from bharat_sourcer.identity import FirebaseVerifier, GuestSessions
from bharat_sourcer.jobs import JobError
from bharat_sourcer.schemas import Job, Model, Status


def credential(request: Request, x_job_token: str | None = Header(default=None)):
    access = request.app.state.access
    if not access.settings.auth_enabled:
        return x_job_token
    return access.identity(request)


ProjectAccess = Annotated[object, Depends(credential)]


class SessionInfo(Model):
    kind: str
    expires_at: int | None = None
    daily_action_limit: int
    part_limit: int


class UsageWindow(Model):
    limit: int
    used: int
    remaining: int
    resets_at: int


class SessionUsage(Model):
    daily_actions: UsageWindow
    daily_projects: UsageWindow
    minute_actions: UsageWindow


class ProjectSummary(Model):
    job_id: str
    url: str
    status: Status
    created_at: datetime
    updated_at: datetime
    part_count: int


class ProjectList(Model):
    projects: list[ProjectSummary]
    next_cursor: str | None = None


class ClaimProject(Model):
    job_token: str | None = Field(default=None, max_length=200)


class Access:
    def __init__(self, settings, service, verifier=None):
        self.settings, self.service = settings, service
        self.verifier = verifier or FirebaseVerifier(settings.gcp_project or "")
        self.sessions = GuestSessions(
            settings.guest_session_secret.get_secret_value()
            if settings.guest_session_secret
            else "",
            settings.guest_session_days * 86400,
        )

    def enabled(self):
        if not self.settings.auth_enabled:
            raise JobError(503, "AUTH_DISABLED", "Account access is not enabled yet")

    def identity(self, request):
        self.enabled()
        if hasattr(request.state, "principal"):
            return request.state.principal
        header = request.headers.get("Authorization")
        try:
            if header:
                scheme, token = header.split(" ", 1)
                if scheme.lower() != "bearer" or not token or len(token) > 8192:
                    raise ValueError("Invalid authorization")
                principal = self.verifier.verify(token)
            else:
                principal = self.sessions.verify(request.cookies.get(self.sessions.cookie_name))
        except Exception as exc:
            raise JobError(401, "IDENTITY_REQUIRED", "Sign in or start a guest session") from exc
        request.state.principal = principal
        return principal

    def csrf(self, request):
        # Custom header forces a CORS preflight for cross-origin browser requests.
        if request.headers.get("X-Requested-With") != "BharatSourcer":
            raise JobError(403, "REQUEST_HEADER_REQUIRED", "Missing application request header")
        origin = request.headers.get("Origin")
        if origin and origin not in self.settings.cors_origins:
            raise JobError(403, "ORIGIN_REJECTED", "Origin is not allowed")

    def ip_key(self, request):
        value = request.client.host if request.client else "unknown"
        if self.settings.trusted_proxy_ip_header:
            value = request.headers.get("X-Client-IP", "")
            try:
                value = str(ipaddress.ip_address(value))
            except ValueError as exc:
                raise JobError(
                    400, "CLIENT_IP_REQUIRED", "Trusted proxy client IP required"
                ) from exc
        return hmac.new(self.sessions.secret, value.encode(), hashlib.sha256).hexdigest()

    def charge(self, request, principal, *, session=False):
        timestamp = time.time()
        day = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d")
        ip = self.ip_key(request)
        if session:
            limits = {f"session-{day}-{ip}": 10, f"session-global-{day}": 1000}
        else:
            owner = hashlib.sha256(principal.owner.encode()).hexdigest()
            cap = (
                self.settings.guest_daily_actions
                if principal.guest
                else self.settings.account_daily_actions
            )
            limits = {
                f"actions-{day}-{owner}": cap,
                f"actions-ip-{day}-{ip}": self.settings.ip_daily_actions,
                f"actions-global-{day}": self.settings.global_daily_actions,
                f"burst-{int(timestamp) // 60}-{owner}": 5,
            }
            if request.url.path == "/v1/jobs":
                limits[f"create-{day}-{owner}"] = 1 if principal.guest else 5
        if not self.service.store.consume(limits):
            counts = self.service.store.usage_counts(list(limits))
            resets = [
                (int(timestamp) // window + 1) * window
                for key, cap in limits.items()
                if counts[key] >= cap
                for window in [60 if key.startswith("burst-") else 86400]
            ]
            raise JobError(
                429,
                "USAGE_LIMIT",
                "Usage limit reached; saved projects remain available",
                retry_after=max(1, math.ceil(max(resets, default=timestamp + 60) - time.time())),
            )

    def usage(self, principal):
        timestamp = int(time.time())
        day = datetime.fromtimestamp(timestamp, UTC).strftime("%Y%m%d")
        owner = hashlib.sha256(principal.owner.encode()).hexdigest()
        windows = {
            "daily_actions": (
                f"actions-{day}-{owner}",
                self.settings.guest_daily_actions
                if principal.guest
                else self.settings.account_daily_actions,
                86400,
            ),
            "daily_projects": (f"create-{day}-{owner}", 1 if principal.guest else 5, 86400),
            "minute_actions": (f"burst-{timestamp // 60}-{owner}", 5, 60),
        }
        counts = self.service.store.usage_counts([key for key, _, _ in windows.values()])
        return SessionUsage(
            **{
                name: UsageWindow(
                    limit=cap,
                    used=counts[key],
                    remaining=max(0, cap - counts[key]),
                    resets_at=(timestamp // duration + 1) * duration,
                )
                for name, (key, cap, duration) in windows.items()
            }
        )

    def session_info(self, principal):
        return SessionInfo(
            kind="guest" if principal.guest else "account",
            expires_at=principal.expires_at,
            daily_action_limit=self.settings.guest_daily_actions
            if principal.guest
            else self.settings.account_daily_actions,
            part_limit=self.settings.guest_part_limit
            if principal.guest
            else self.settings.sourcing_max_parts,
        )


def add_access_routes(app, access):
    @app.post("/v1/session/guest", response_model=SessionInfo, tags=["identity"])
    def guest_session(request: Request, response: Response):
        access.enabled()
        access.csrf(request)
        try:
            principal = access.sessions.verify(request.cookies.get(access.sessions.cookie_name))
        except ValueError:
            access.charge(request, None, session=True)
            cookie = access.sessions.issue()
            principal = access.sessions.verify(cookie)
            response.set_cookie(
                access.sessions.cookie_name,
                cookie,
                max_age=access.sessions.lifetime,
                httponly=True,
                secure=True,
                samesite="lax",
                path="/",
            )
        response.headers["Cache-Control"] = "no-store"
        return access.session_info(principal)

    @app.get("/v1/session", response_model=SessionInfo, tags=["identity"])
    def session(request: Request):
        return access.session_info(access.identity(request))

    @app.get("/v1/session/usage", response_model=SessionUsage, tags=["identity"])
    def usage(request: Request):
        return access.usage(access.identity(request))

    @app.post("/v1/session/logout", status_code=204, tags=["identity"])
    def logout(request: Request, response: Response):
        access.enabled()
        access.csrf(request)
        response.delete_cookie(access.sessions.cookie_name, path="/", secure=True, httponly=True)

    @app.get("/v1/projects", response_model=ProjectList, tags=["projects"])
    def projects(request: Request, cursor: str = "", limit: int = Query(default=20, ge=1, le=50)):
        principal = access.identity(request)
        if cursor:
            access.service._validate_id(cursor)
        records = access.service.store.owned(principal.owner, cursor, limit + 1)
        return ProjectList(
            projects=[
                ProjectSummary(
                    job_id=r.job.job_id,
                    url=str(r.job.input.url),
                    status=r.job.status,
                    created_at=r.job.created_at,
                    updated_at=r.job.updated_at,
                    part_count=len(r.job.items),
                )
                for r in records[:limit]
            ],
            next_cursor=records[limit - 1].job.job_id if len(records) > limit else None,
        )

    @app.post("/v1/projects/{job_id}/claim", response_model=Job, tags=["projects"])
    def claim(job_id: str, body: ClaimProject, request: Request):
        principal = access.identity(request)
        if principal.guest:
            raise JobError(401, "ACCOUNT_REQUIRED", "Sign in before claiming a project")
        access.csrf(request)
        access.service._validate_id(job_id)
        try:
            guest = access.sessions.verify(request.cookies.get(access.sessions.cookie_name))
        except ValueError:
            guest = None

        def change(record):
            if record.owner_id == principal.owner:
                return
            if record.owner_id is None:
                access.service._authorized(record, body.job_token)
            elif not guest or record.owner_id != guest.owner:
                raise JobError(404, "JOB_NOT_FOUND", "Project not found")
            record.owner_id = principal.owner
            record.part_limit = access.settings.sourcing_max_parts
            # Owning identity replaces the old capability; never trust it for an owned job.

        record = access.service.store.mutate(job_id, change)
        if record is None:
            raise JobError(404, "JOB_NOT_FOUND", "Project not found")
        return record.job
