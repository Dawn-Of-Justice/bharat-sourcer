from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def now() -> datetime:
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Name = Annotated[str, Field(min_length=1, max_length=200)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=10000)]
Status = Literal["queued", "extracting", "awaiting_confirmation", "resolving", "done", "failed"]


class CreateJob(Model):
    url: HttpUrl
    pin: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")
    lang: Literal["en", "hi", "ta", "ml"] = "en"
    user_level: Literal["beginner", "intermediate"] = "beginner"
    visibility: Literal["unlisted"] = "unlisted"


class Evidence(Model):
    timestamp: str = Field(pattern=r"^\d{2,}:[0-5]\d$")
    observation: str = Field(min_length=1, max_length=1000)


class BomItem(Model):
    line_id: str
    raw_name: Name
    qty: Quantity | None = 1
    qty_unit: Literal["pcs"] = "pcs"
    user_has_it: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    user_edited: bool = False


class UpdateLine(Model):
    op: Literal["update"]
    line_id: str
    raw_name: Name | None = None
    qty: Quantity | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.raw_name is None and self.qty is None:
            raise ValueError("An update requires raw_name or qty")
        return self


class RemoveLine(Model):
    op: Literal["remove"]
    line_id: str


class HaveLine(Model):
    op: Literal["have_it"]
    line_id: str
    user_has_it: bool = True


class AddLine(Model):
    op: Literal["add"]
    raw_name: Name
    qty: Quantity = 1


Edit = Annotated[UpdateLine | RemoveLine | HaveLine | AddLine, Field(discriminator="op")]


class ConfirmJob(Model):
    edits: list[Edit] = Field(default_factory=list, max_length=100)


class Event(Model):
    seq: int
    status: Status
    message: str
    timestamp: datetime = Field(default_factory=now)


class ReportLine(Model):
    item: BomItem
    sourcing_status: Literal["not_run", "already_owned"]
    price_inr: None = None
    grade: None = None


class Report(Model):
    demo: bool = True
    summary: str
    lines: list[ReportLine]
    total_inr: None = None


class Job(Model):
    job_id: str
    status: Status = "queued"
    demo: bool = True
    input: CreateJob
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    items: list[BomItem] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    report: Report | None = None
    error: "ErrorDetail | None" = None
    extraction_model: str | None = None


class CreatedJob(Model):
    job_id: str
    status: Literal["queued"] = "queued"
    cached: Literal[False] = False
    demo: bool = True
    job_token: str
    watch: str


class ConfirmationAccepted(Model):
    status: Literal["resolving"] = "resolving"


class ErrorDetail(Model):
    code: str
    message: str


class ErrorResponse(Model):
    error: ErrorDetail


class Health(Model):
    status: Literal["ok"] = "ok"
    mode: Literal["demo", "live"] = "demo"
    storage: Literal["memory", "firestore"] = "memory"
