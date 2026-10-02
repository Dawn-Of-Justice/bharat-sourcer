from datetime import UTC, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


def now() -> datetime:
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Name = Annotated[str, Field(min_length=1, max_length=200)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=10000)]
Status = Literal[
    "queued", "extracting", "awaiting_confirmation", "resolving", "sourcing", "done", "failed"
]


class CreateJob(Model):
    url: HttpUrl
    pin: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")
    lang: Literal["en", "hi", "ta", "ml"] = "en"
    user_level: Literal["beginner", "intermediate"] = "beginner"
    visibility: Literal["unlisted"] = "unlisted"


class Evidence(Model):
    timestamp: str = Field(pattern=r"^\d{2,}:[0-5]\d$")
    observation: str = Field(min_length=1, max_length=1000)


class PartSpecs(Model):
    family: Literal["pro_micro", "oled", "ttp223", "usb_cable"] | None = None
    controller: Literal["atmega32u4", "ssd1306", "sh1106", "ttp223"] | None = None
    logic_v: Literal[3.3, 5.0] | None = None
    clock_mhz: Literal[8, 16] | None = None
    interface: Literal["i2c", "spi", "digital", "usb"] | None = None
    resolution: Literal["128x32", "128x64"] | None = None
    pinout: str | None = Field(default=None, min_length=1, max_length=200)
    supply_min_v: float | None = Field(default=None, ge=0, le=24, allow_inf_nan=False)
    supply_max_v: float | None = Field(default=None, ge=0, le=24, allow_inf_nan=False)
    i2c_address: Literal["0x3c", "0x3d"] | None = None
    output_mode: Literal["momentary", "toggle"] | None = None
    active_level: Literal["high", "low"] | None = None
    connector_a: Literal["usb_a", "usb_c", "micro_b", "mini_b"] | None = None
    connector_b: Literal["usb_a", "usb_c", "micro_b", "mini_b"] | None = None
    data_support: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def ordered_range(self):
        controllers = {
            "pro_micro": {"atmega32u4"},
            "oled": {"ssd1306", "sh1106"},
            "ttp223": {"ttp223"},
            "usb_cable": set(),
        }
        if self.family and self.controller and self.controller not in controllers[self.family]:
            raise ValueError("Controller does not belong to the declared part family")
        if self.family == "pro_micro" and self.logic_v is not None and self.clock_mhz is not None:
            if (self.logic_v, self.clock_mhz) not in {(3.3, 8), (5.0, 16)}:
                raise ValueError("Unsupported Pro Micro voltage/clock combination")
        if (
            self.supply_min_v is not None
            and self.supply_max_v is not None
            and self.supply_min_v > self.supply_max_v
        ):
            raise ValueError("Supply minimum must not exceed maximum")
        return self


class SpecEvidence(Model):
    field: str
    value: str
    source: Literal["part_name", "user", "seller_title", "seller_property"]
    locator: str


class Clarification(Model):
    field: str
    question: str


class Compatibility(Model):
    status: Literal["unknown", "compatible", "changes_required", "incompatible"]
    grade: Literal["A", "B", "C", "D", "X"] | None = None
    scope: Literal["declared_specs_only"] = "declared_specs_only"
    reasons: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class BomItem(Model):
    line_id: str
    raw_name: Name
    qty: Quantity | None = 1
    qty_unit: Literal["pcs"] = "pcs"
    user_has_it: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    user_edited: bool = False
    specs: PartSpecs = Field(default_factory=PartSpecs)
    clarifications: list[Clarification] = Field(default_factory=list)


class UpdateLine(Model):
    op: Literal["update"]
    line_id: str
    raw_name: Name | None = None
    qty: Quantity | None = None
    specs: PartSpecs | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.raw_name is None and self.qty is None and self.specs is None:
            raise ValueError("An update requires raw_name, qty or specs")
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
    specs: PartSpecs = Field(default_factory=PartSpecs)


Edit = Annotated[UpdateLine | RemoveLine | HaveLine | AddLine, Field(discriminator="op")]


class ConfirmJob(Model):
    edits: list[Edit] = Field(default_factory=list, max_length=100)


class Event(Model):
    seq: int
    status: Status
    message: str
    timestamp: datetime = Field(default_factory=now)


class PartResolution(Model):
    query: str
    missing_specs: list[str] = Field(default_factory=list)
    compatibility_status: Literal["not_checked"] = "not_checked"
    specs: PartSpecs = Field(default_factory=PartSpecs)
    evidence: list[SpecEvidence] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)


class VerifiedOffer(Model):
    url: HttpUrl
    seller: str
    title: str
    price_inr: str = Field(pattern=r"^\d+\.\d{2}$")
    currency: Literal["INR"] = "INR"
    stock: Literal["in_stock", "out_of_stock", "preorder", "unknown"] = "unknown"
    checked_at: datetime = Field(default_factory=now)
    verification: Literal["seller_structured_data"] = "seller_structured_data"
    seller_trust: Literal["unverified"] = "unverified"
    tax_included: None = None
    shipping_inr: None = None
    compatibility_status: Literal[
        "not_checked", "unknown", "compatible", "changes_required", "incompatible"
    ] = "not_checked"
    specs: PartSpecs = Field(default_factory=PartSpecs)
    spec_evidence: list[SpecEvidence] = Field(default_factory=list)
    compatibility: Compatibility | None = None


class SearchAttribution(Model):
    source_urls: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    search_suggestions_html: str | None = None


class ReportLine(Model):
    item: BomItem
    sourcing_status: Literal[
        "not_run", "already_owned", "offers_found", "no_verified_offers", "failed"
    ]
    resolution: PartResolution | None = None
    offers: list[VerifiedOffer] = Field(default_factory=list)
    attribution: SearchAttribution | None = None
    sourcing_error: "ErrorDetail | None" = None
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
    sourcing_enabled: bool = False


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
