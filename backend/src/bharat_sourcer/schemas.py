from collections import Counter
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from bharat_sourcer.countries import COUNTRIES, DEFAULT_COUNTRY


def now() -> datetime:
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Name = Annotated[str, Field(min_length=1, max_length=200)]
# A BOM line id sent by a client (server ids look like L01); bounded, never trusted.
LineRef = Annotated[str, Field(min_length=1, max_length=64)]
Quantity = Annotated[int, Field(strict=True, ge=1, le=10000)]
Money = Annotated[str, Field(pattern=r"^\d+\.\d{2}$")]
Status = Literal[
    "queued",
    "extracting",
    "awaiting_confirmation",
    "resolving",
    "sourcing",
    "paused",
    "done",
    "failed",
]


def supported_country(code: str) -> str:
    if code not in COUNTRIES:
        raise ValueError(f"country {code} is not supported yet; supported: {', '.join(COUNTRIES)}")
    return code


# ISO 3166-1 alpha-2 code of a country in `countries.COUNTRIES`.
CountryCode = Annotated[
    str, Field(pattern=r"^[A-Z]{2}$", examples=["IN"]), AfterValidator(supported_country)
]


class CreateJob(Model):
    url: HttpUrl
    # Where the parts are delivered. When omitted, a signed-in account's saved country is
    # used, else the default (India).
    country: CountryCode = DEFAULT_COUNTRY
    lang: Literal["en", "hi", "ta", "ml"] = "en"
    user_level: Literal["beginner", "intermediate"] = "beginner"
    visibility: Literal["unlisted"] = "unlisted"
    # Extra sources about the same build (e.g. its project page or repository), fused into
    # one BOM with the primary `url`. Same validation as `url`; at most one video in total.
    sources: list[HttpUrl] = Field(default_factory=list, max_length=3)

    @model_validator(mode="before")
    @classmethod
    def drop_legacy_pin(cls, data):
        # The PIN code was never used for sourcing and was removed in v0.23. Snapshots saved
        # earlier and older clients may still carry it; ignore it rather than fail them.
        if isinstance(data, dict) and "pin" in data:
            data = {key: value for key, value in data.items() if key != "pin"}
        return data


class Evidence(Model):
    """Model-reported provenance for an extracted BOM line.

    `source` defaults to `video` so snapshots saved before project-page support still
    validate. Video evidence carries a timestamp. Project-page evidence carries the fetched
    document `url` and a `quote` the server found verbatim (whitespace-normalised) in it.
    Code evidence is deterministic: the repository `file` and 1-based `line`, the line's
    text as `quote`, and a `url` to that line. YouTube description evidence carries a
    `quote` (at most 300 characters) the server found verbatim in the video's description
    and the canonical video `url`; it is dropped from responses 30 days after
    `Job.video_meta.fetched_at` (YouTube API Services retention policy).
    """

    timestamp: str | None = Field(default=None, pattern=r"^\d{2,}:[0-5]\d$")
    observation: str = Field(min_length=1, max_length=1000)
    source: Literal["video", "project_page", "code", "youtube_description"] = "video"
    quote: str | None = Field(default=None, min_length=3, max_length=500)
    url: HttpUrl | None = None
    file: str | None = Field(default=None, min_length=1, max_length=300)
    line: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def locator_matches_source(self):
        if self.source != "code" and (self.file is not None or self.line is not None):
            raise ValueError("Only code evidence has a file and line")
        if self.source == "video":
            if self.timestamp is None or self.quote is not None or self.url is not None:
                raise ValueError("Video evidence needs a timestamp and no page quote or URL")
        elif self.source == "code":
            if self.timestamp is not None or None in (self.quote, self.url, self.file, self.line):
                raise ValueError("Code evidence needs a quote, URL, file and line")
        elif self.timestamp is not None or self.quote is None or self.url is None:
            raise ValueError("Project-page evidence needs a quote and URL and no timestamp")
        elif self.source == "youtube_description" and len(self.quote) > 300:
            raise ValueError("Description quotes are at most 300 characters")
        return self


class PartSpecs(Model):
    family: str | None = Field(default=None, min_length=1, max_length=100)
    controller: Literal["atmega32u4", "ssd1306", "sh1106", "ttp223"] | None = None
    # Float literals are valid for pydantic (enum in OpenAPI) but not in the typing spec.
    logic_v: Literal[3.3, 5.0] | None = None  # type: ignore[valid-type]
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
        if (
            self.family in controllers
            and self.controller
            and (self.controller not in controllers[self.family])
        ):
            raise ValueError("Controller does not belong to the declared part family")
        if (
            self.family == "pro_micro"
            and self.logic_v is not None
            and self.clock_mhz is not None
            and (self.logic_v, self.clock_mhz) not in {(3.3, 8), (5.0, 16)}
        ):
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
    # "catalog" values come from the curated parts catalogue, never from a seller.
    # "ai_inferred" values were decided by the model from project context (BomItem.ai_specs).
    source: Literal[
        "part_name",
        "user",
        "seller_title",
        "seller_property",
        "seller_table",
        "catalog",
        "ai_inferred",
    ]
    locator: str


class SpecConflict(Model):
    """Seller sources disagree; the field is left unknown rather than picked."""

    field: str
    candidates: list[SpecEvidence] = Field(default_factory=list, max_length=20)


class Clarification(Model):
    field: str
    question: str


class PartRequirement(Model):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=40)
    operator: Literal["equals", "at_least", "at_most"] = "equals"
    # "inferred" values were proposed by the model from project context, not stated by
    # the source or the user; they guide research and must stay reviewable.
    origin: Literal["user", "inferred"] = "user"
    reason: str | None = Field(default=None, max_length=300)


ProjectTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]
ProjectDescription = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)
]


class ProjectContext(Model):
    """The model's reading of what the project is; AI-inferred, never verified.

    `title` and `description` are written by the model and editable by the owner
    (`*_source` records who wrote the current value). `summary` stays the model's own
    understanding after analysing the source and is not editable.
    """

    title: ProjectTitle | None = None
    title_source: Literal["ai", "user"] = "ai"
    description: ProjectDescription | None = None
    description_source: Literal["ai", "user"] = "ai"
    summary: str | None = Field(default=None, min_length=1, max_length=1000)
    power: str | None = Field(default=None, max_length=200)
    controller: str | None = Field(default=None, max_length=200)
    interfaces: list[str] = Field(default_factory=list, max_length=10)
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    origin: Literal["ai_inferred"] = "ai_inferred"


class ResearchFact(Model):
    name: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=200)
    unit: str | None = Field(default=None, max_length=40)
    quote: str = Field(min_length=3, max_length=1000)


class RequirementCheck(Model):
    requirement: PartRequirement
    status: Literal["meets", "does_not_meet", "unknown"]
    reason: str


class ResearchAssessment(Model):
    status: Literal["potential_match", "needs_information", "not_suitable", "stale"]
    explanation: str = Field(min_length=1, max_length=1500)
    conditions: list[Annotated[str, Field(min_length=1, max_length=400)]] = Field(
        default_factory=list, max_length=10
    )
    questions: list[Annotated[str, Field(min_length=1, max_length=400)]] = Field(
        default_factory=list, max_length=10
    )
    method: Literal["llm_evidence_review"] = "llm_evidence_review"
    checks: list[RequirementCheck] = Field(default_factory=list)


class ResearchCandidate(Model):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=100)
    kind: Literal["seller", "manufacturer", "reference"]
    identity_quote: str = Field(min_length=3, max_length=1000)
    match: Literal["exact", "possible"]
    facts: list[ResearchFact] = Field(default_factory=list, max_length=20)
    assessment: ResearchAssessment
    evidence_method: Literal["llm_extraction_quote_checked"] = "llm_extraction_quote_checked"


class ResearchSource(Model):
    url: HttpUrl
    status: Literal["read", "unavailable"]
    reason: str | None = None
    reviewed: bool = False


class PartResearch(Model):
    # "skipped": no Gemini review ran, because a verified in-stock compatible offer made it
    # unnecessary or the job budget was reached (see `summary`).
    status: Literal["ready", "no_evidence", "failed", "stale", "skipped"]
    summary: str
    candidates: list[ResearchCandidate] = Field(default_factory=list, max_length=8)
    sources: list[ResearchSource] = Field(default_factory=list, max_length=32)
    questions: list[Annotated[str, Field(min_length=1, max_length=400)]] = Field(
        default_factory=list, max_length=10
    )
    model: str | None = None
    checked_at: datetime = Field(default_factory=now)


class CompatFinding(Model):
    """One deterministic rule result; `grade` is the floor this finding imposes."""

    rule: str
    grade: Literal["A", "B", "C", "D", "X"]
    area: Literal["wiring", "code", "power", "safety", "verify"]
    message: str
    change: str | None = None
    basis: list[str] = Field(default_factory=list)


class WhatChanges(Model):
    wiring: list[str] = Field(default_factory=list)
    code: list[str] = Field(default_factory=list)
    power: list[str] = Field(default_factory=list)
    safety: list[str] = Field(default_factory=list)
    verify: list[str] = Field(default_factory=list)


class Compatibility(Model):
    status: Literal["unknown", "compatible", "changes_required", "incompatible"]
    grade: Literal["A", "B", "C", "D", "X"] | None = None
    scope: Literal["declared_specs_only"] = "declared_specs_only"
    reasons: list[str] = Field(default_factory=list)
    missing_fields: list[str] = Field(default_factory=list)
    changes: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)
    # Added by the catalogue rules engine; absent fields mean the original comparison ran.
    method: Literal["declared_specs", "catalog_rules"] = "declared_specs"
    grade_label: str | None = None
    findings: list[CompatFinding] = Field(default_factory=list)
    what_changes: WhatChanges | None = None
    required_catalog_id: str | None = None
    offered_catalog_id: str | None = None


class Lookalike(Model):
    """A part easily confused with this line; a warning, never a suggested substitute."""

    name: Name
    note: str | None = Field(default=None, max_length=300)
    # table: the server's curated confusables list; ai: named by the extraction model.
    origin: Literal["table", "ai"]


class ConflictValue(Model):
    value: str = Field(min_length=1, max_length=200)
    source: Literal["video", "project_page", "code", "youtube_description"]
    url: HttpUrl | None = None
    locator: str | None = Field(default=None, max_length=300)


class ExtractionStep(Model):
    """One live step of reading a job's sources (jobs.py); shown while `extracting`.

    key: `description` (the video's description), `source:<url>` (one per source, read in
    parallel), `reconcile` (checking the list as one build), `spec_fill` (part details).
    There is no model-reported percentage: clients estimate progress from the steps.
    """

    key: str = Field(min_length=1, max_length=600)
    label: str = Field(min_length=1, max_length=200)
    status: Literal["pending", "running", "done", "failed", "skipped"] = "pending"
    detail: str | None = Field(default=None, max_length=200)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ReconciledLine(Model):
    """A line the reconcile pass folded into another or left out (reconcile.py); AI-decided."""

    raw_name: str = Field(min_length=1, max_length=200)
    action: Literal["merged", "removed"]
    # removed only: built_in (part of another listed part), tool or not_a_part.
    kind: Literal["built_in", "tool", "not_a_part"] | None = None
    # merged: the kept line's name; removed built_in: the part it is built into.
    into: str | None = Field(default=None, max_length=200)
    reason: str = Field(min_length=1, max_length=300)


class ItemConflict(Model):
    """Sources disagree about this line; nothing is picked silently (see multi-source-intake)."""

    kind: Literal["identity_mismatch", "qty_mismatch"]
    message: str = Field(min_length=1, max_length=500)
    values: list[ConflictValue] = Field(default_factory=list, max_length=6)


PartCategory = Literal[
    "resistor",
    "capacitor_electrolytic",
    "capacitor_ceramic",
    "led",
    "ldr",
    "wire",
    "diode",
    "transistor",
    "ic",
    "module",
    "board",
    "sensor",
    "connector",
    "switch",
    "battery",
    "other",
]
ShortText = Annotated[str, Field(min_length=1, max_length=120)]


class SpecParam(Model):
    """One buyable parameter. `si_value` is filled by the server's unit normaliser."""

    name: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=80)
    operator: Literal["equals", "at_least", "at_most", "between"] = "equals"
    value_max: str | None = Field(default=None, max_length=80)
    unit: str | None = Field(default=None, max_length=10)
    si_value: float | None = Field(default=None, allow_inf_nan=False)
    si_value_max: float | None = Field(default=None, allow_inf_nan=False)
    # Required params must match a listing; others only add confidence.
    required: bool = True
    # stated: the source names it; inferred: decided from project context, with a reason.
    origin: Literal["stated", "inferred", "user"] = "inferred"
    reason: str | None = Field(default=None, max_length=300)


class BuyableSpec(Model):
    """What to buy for a BOM line, stated the way Indian sellers list parts.

    `ai_inferred` specs come from the extraction call (one call per job, not per line);
    `seed` specs are the deterministic fallback built from the part name only. Every
    inferred value carries a reason and the whole spec is editable (`origin: user`).
    """

    origin: Literal["seed", "ai_inferred", "user"] = "seed"
    # The BOM line's own name, so the judge always sees what the maker asked for.
    part_name: ShortText | None = None
    category: PartCategory = "other"
    mount: Literal["tht", "smd", "any"] = "any"
    mount_origin: Literal["stated", "inferred", "user", "default"] = "default"
    mount_reason: str | None = Field(default=None, max_length=300)
    params: list[SpecParam] = Field(default_factory=list, max_length=12)
    # Names of required params; derived by the server from `params[].required`.
    must: list[str] = Field(default_factory=list, max_length=12)
    # Descriptive words ("clear", "bare"): they add confidence but never block a match.
    prefer: list[ShortText] = Field(default_factory=list, max_length=10)
    exclude: list[ShortText] = Field(default_factory=list, max_length=12)
    synonyms: list[ShortText] = Field(default_factory=list, max_length=10)
    queries: list[ShortText] = Field(default_factory=list, max_length=4)
    needs_value: bool = False
    needs_value_reason: str | None = Field(default=None, max_length=300)
    reasons: list[str] = Field(default_factory=list, max_length=6)


Fabrication = Literal["none", "3d_print", "pcb"]


class BomItem(Model):
    line_id: str
    raw_name: Name
    qty: Quantity | None = 1
    qty_unit: Literal["pcs"] = "pcs"
    # stated: the source gives the count; inferred: decided from project context; user: edited.
    qty_source: Literal["stated", "inferred", "user"] = "stated"
    qty_reason: str | None = Field(default=None, max_length=300)
    # A count is not meaningful for this line (wire, heat shrink, solder, a printed case):
    # decided by the reconcile pass (reconcile.py). `qty` stays one pack for sourcing; the
    # UI shows "As needed". Cleared when the maker sets a quantity.
    qty_as_needed: bool = False
    # Made to order rather than bought from stock: a 3D-printed part or a custom PCB.
    # Decided by the reconcile pass from project context (reconcile.py); sourcing then
    # links a fabrication service instead of searching sellers (sourcing/fabrication.py).
    fabrication: Fabrication = "none"
    user_has_it: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    user_edited: bool = False
    specs: PartSpecs = Field(default_factory=PartSpecs)
    # Required spec values the model inferred from project context after extraction
    # (spec_fill.py), never verified. Name, catalogue and user values take precedence.
    ai_specs: PartSpecs = Field(default_factory=PartSpecs)
    requirements: list[PartRequirement] = Field(default_factory=list, max_length=20)
    clarifications: list[Clarification] = Field(default_factory=list)
    lookalikes: list[Lookalike] = Field(default_factory=list, max_length=10)
    conflicts: list[ItemConflict] = Field(default_factory=list, max_length=10)
    # Deterministic, from evidence at extraction time; None for lines without an assessment
    # (user-added, renamed or saved before confidence existed).
    confidence: Literal["verified", "likely", "check"] | None = None
    confidence_reason: str | None = Field(default=None, max_length=300)
    # AI-inferred or user-edited buying spec; None means sourcing uses a seed spec.
    buyable_spec: BuyableSpec | None = None


class UpdateLine(Model):
    op: Literal["update"]
    line_id: LineRef
    raw_name: Name | None = None
    qty: Quantity | None = None
    specs: PartSpecs | None = None
    requirements: list[PartRequirement] | None = Field(default=None, max_length=20)
    # Replaces the line's buying spec; saved with origin "user".
    buyable_spec: BuyableSpec | None = None

    @model_validator(mode="after")
    def require_change(self):
        if all(
            v is None
            for v in (self.raw_name, self.qty, self.specs, self.requirements, self.buyable_spec)
        ):
            raise ValueError(
                "An update requires raw_name, qty, specs, requirements or buyable_spec"
            )
        return self


class RemoveLine(Model):
    op: Literal["remove"]
    line_id: LineRef


class HaveLine(Model):
    op: Literal["have_it"]
    line_id: LineRef
    user_has_it: bool = True


class AddLine(Model):
    op: Literal["add"]
    raw_name: Name
    qty: Quantity = 1
    specs: PartSpecs = Field(default_factory=PartSpecs)
    requirements: list[PartRequirement] = Field(default_factory=list, max_length=20)


Edit = Annotated[UpdateLine | RemoveLine | HaveLine | AddLine, Field(discriminator="op")]


class ConfirmJob(Model):
    edits: list[Edit] = Field(default_factory=list, max_length=100)


class SelectOffer(Model):
    line_id: LineRef
    offer_url: HttpUrl | None = None
    accept_changes: bool = False
    accept_research_assessment: bool = False


class SelectOffers(Model):
    selections: list[SelectOffer] = Field(min_length=1, max_length=100)


class RefreshOffers(Model):
    line_ids: list[LineRef] = Field(min_length=1, max_length=30)


class UpdatePartSpecs(Model):
    line_id: LineRef
    specs: PartSpecs | None = None
    requirements: list[PartRequirement] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def require_fields(self):
        if not (self.specs and self.specs.model_fields_set) and self.requirements is None:
            raise ValueError("Provide specification fields or requirements")
        return self


class UpdateJobSpecs(Model):
    updates: list[UpdatePartSpecs] = Field(min_length=1, max_length=100)


class Event(Model):
    seq: int
    status: Status
    message: str
    timestamp: datetime = Field(default_factory=now)


class SendMessage(Model):
    message_id: UUID
    text: str = Field(min_length=1, max_length=4000)


class ProposalDecision(Model):
    action: Literal["accept", "reject"]


class ResistorQuestion(Model):
    line_id: LineRef
    purpose: Literal["unknown", "led_series", "piezo_input", "pull_up", "other"] = "unknown"
    question: str = Field(min_length=1, max_length=1000)


class ResistorInputs(Model):
    line_id: LineRef
    purpose: Literal["led_series"]
    supply_max_v: float = Field(gt=0, le=24, allow_inf_nan=False)
    led_forward_min_v: float = Field(gt=0, le=24, allow_inf_nan=False)
    target_max_ma: float = Field(gt=0, le=20, allow_inf_nan=False)
    driver_limit_ma: float = Field(gt=0, le=100, allow_inf_nan=False)
    confirmed: Literal[True]


class ResistorAdvice(Model):
    advice_id: str
    inputs: ResistorInputs
    created_at: datetime = Field(default_factory=now)
    status: Literal["suggestion", "unavailable"]
    rule_version: str
    recovery: Literal["none", "validated_fallback", "blocked"] = "none"
    resistance_ohm: str | None = None
    worst_case_current_ma: str | None = None
    worst_case_power_w: str | None = None
    minimum_rated_power_w: str | None = None
    tolerance_percent: Literal[5] = 5
    explanation: str
    limitations: list[str] = Field(default_factory=list)
    references: list[str] = Field(default_factory=list)


class ChatReply(Model):
    text: str = Field(min_length=1, max_length=4000)
    cited_line_ids: list[str] = Field(default_factory=list, max_length=100)
    edits: list[Edit] = Field(default_factory=list, max_length=20)
    resistor_question: ResistorQuestion | None = None
    refresh: RefreshOffers | None = None
    spec_update: UpdateJobSpecs | None = None

    @model_validator(mode="after")
    def one_action(self):
        if sum(bool(action) for action in (self.edits, self.refresh, self.spec_update)) > 1:
            raise ValueError("Propose only one of draft edits, a refresh or a spec update")
        return self


class ChatProposal(Model):
    edits: list[Edit]
    status: Literal["pending", "accepted", "rejected"] = "pending"
    base_fingerprint: str


class RefreshProposal(Model):
    request: RefreshOffers
    status: Literal["pending", "accepted", "rejected"] = "pending"
    base_fingerprint: str
    refresh_count: int | None = None
    result_message_id: str | None = None


# fabrication_service: a made-to-order line linked to a fabrication service, not a seller.
SourcingStatus = Literal[
    "not_run",
    "already_owned",
    "offers_found",
    "no_verified_offers",
    "failed",
    "fabrication_service",
]


class RefreshLineResult(Model):
    """Snapshot of one refreshed line when its batch ended; later refreshes do not edit it."""

    line_id: str
    sourcing_status: SourcingStatus
    offer_count: int = Field(default=0, ge=0)
    lowest_listed_price_inr: Money | None = None
    lowest_listed_stock: Literal["in_stock", "out_of_stock", "preorder", "unknown"] | None = None
    price_source: Literal["seller_published"] = "seller_published"
    error_code: str | None = None


class SpecProposal(Model):
    request: UpdateJobSpecs
    status: Literal["pending", "accepted", "rejected"] = "pending"
    base_fingerprint: str


class ChatMessage(Model):
    message_id: str
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime = Field(default_factory=now)
    cited_line_ids: list[str] = Field(default_factory=list)
    proposal: ChatProposal | None = None
    refresh_proposal: RefreshProposal | None = None
    spec_proposal: SpecProposal | None = None
    resistor_question: ResistorQuestion | None = None
    completes_message_id: str | None = None
    refresh_results: list[RefreshLineResult] = Field(default_factory=list, max_length=100)


ActionKind = Literal["edit", "refresh", "spec_update"]
ActionStatus = Literal["accepted", "rejected", "completed", "failed"]


class ActionRecord(Model):
    """One append-only history entry for a decided or finished chat action."""

    kind: ActionKind
    message_id: str
    status: ActionStatus
    created_at: datetime = Field(default_factory=now)
    line_ids: list[str] = Field(default_factory=list, max_length=100)
    summary: str = Field(default="", max_length=500)
    refresh_count: int | None = None
    result_message_id: str | None = None


class CatalogCandidate(Model):
    id: str
    name: str
    confidence: float = Field(ge=0, le=1)


class CatalogMatch(Model):
    """Deterministic catalogue lookup of a part name; reference facts, not seller facts."""

    status: Literal["matched", "ambiguous", "unmatched"]
    id: str | None = None
    name: str | None = None
    category: str | None = None
    chip: str | None = None
    confidence: float = Field(default=0, ge=0, le=1)
    candidates: list[CatalogCandidate] = Field(default_factory=list, max_length=6)
    facts: dict[str, str] = Field(default_factory=dict)
    requirements: list[PartRequirement] = Field(default_factory=list, max_length=20)
    lookalikes: list[str] = Field(default_factory=list)
    verify: str | None = None
    notes: str | None = None
    source_url: str | None = None
    verified: bool = False
    origin: Literal["curated_catalog"] = "curated_catalog"


class PartResolution(Model):
    query: str
    missing_specs: list[str] = Field(default_factory=list)
    compatibility_status: Literal["not_checked"] = "not_checked"
    specs: PartSpecs = Field(default_factory=PartSpecs)
    evidence: list[SpecEvidence] = Field(default_factory=list)
    clarifications: list[Clarification] = Field(default_factory=list)
    catalog: CatalogMatch | None = None


StorePlatform = Literal[
    "shopify",
    "woocommerce",
    "magento",
    "opencart",
    "bigcommerce",
    "prestashop",
    "wix",
    "dukaan",
    "instamojo",
    "jsonld",
    "unknown",
]


class TrustSignals(Model):
    """Deterministic, free seller checks. Absent evidence is recorded, never assumed."""

    domain: str | None = None
    https: bool = False
    # Curated seed list maintained by the project, not a fact reported by the seller.
    known_seller: bool = False
    platform: StorePlatform | None = None
    domain_registered: datetime | None = None
    domain_age_days: int | None = None
    # Format and checksum only; not verified against the GST portal.
    gstin: str | None = None
    policies: list[Literal["returns", "shipping", "contact"]] = Field(default_factory=list)
    price_anomaly: bool = False
    web_risk: Literal["not_checked"] = "not_checked"
    unavailable: list[Literal["domain_age", "policies", "all"]] = Field(default_factory=list)


class SellerTrust(Model):
    label: Literal["established", "verified_basics", "unverified"]
    new_seller: bool = False
    reasons: list[str] = Field(default_factory=list)
    signals: TrustSignals = Field(default_factory=TrustSignals)
    checked_at: datetime = Field(default_factory=now)


class MatchClaim(Model):
    claim: str = Field(min_length=1, max_length=200)
    # Verbatim from the listing text the judge was shown; checked by the server.
    quote: str = Field(min_length=3, max_length=300)


class OfferMatch(Model):
    """How well a listing matches the line's buyable spec. A judgement, not a verification.

    `llm_judge` verdicts keep only claims whose quotes appear verbatim in the listing;
    `deterministic_shortcut` is used only when structured data states every spec param.
    """

    status: Literal["exact", "compatible", "partial", "mismatch"]
    score: float = Field(ge=0, le=1)
    matched: list[str] = Field(default_factory=list, max_length=12)
    missing: list[str] = Field(default_factory=list, max_length=12)
    conflicts: list[str] = Field(default_factory=list, max_length=12)
    reasons: list[str] = Field(default_factory=list, max_length=6)
    claims: list[MatchClaim] = Field(default_factory=list, max_length=8)
    # Claims returned by the model whose quote was not found in the listing.
    dropped_claims: int = Field(default=0, ge=0)
    variant: str | None = Field(default=None, max_length=300)
    pack_qty: int | None = Field(default=None, ge=1, le=100000)
    # llm_buyer: chosen by the AI buyer from the whole project when nothing was accepted.
    method: Literal["llm_judge", "deterministic_shortcut", "llm_buyer"] = "llm_judge"
    model: str | None = None


class CartRecipe(Model):
    """How a shopper's browser adds items to one store's cart by opening a link.

    Decided by an LLM from the store's own add-to-cart form, checked by code, cached per
    store. Not verified by placing an order: the link may still fail at the store.
    """

    # https URL templates on the store's host: `single_url` takes {id} and {qty};
    # `multi_url` takes {items}, each rendered as `multi_item` ({id}, {qty}) and joined.
    single_url: str = Field(max_length=300)
    multi_url: str | None = Field(default=None, max_length=300)
    multi_item: str | None = Field(default=None, max_length=40)
    multi_join: str | None = Field(default=None, max_length=3)
    # Opening the link empties the store's cart first (e.g. Shopify cart permalinks).
    replaces_cart: bool = False
    method: Literal["llm_form_review"] = "llm_form_review"
    model: str | None = None


class VerifiedOffer(Model):
    url: HttpUrl
    seller: str
    seller_domain: str | None = None
    seller_name: str | None = None
    seller_kind: Literal["direct", "marketplace", "platform_hosted"] | None = None
    title: str
    image_url: HttpUrl | None = None
    price_inr: str = Field(pattern=r"^\d+\.\d{2}$")
    currency: Literal["INR"] = "INR"
    stock: Literal["in_stock", "out_of_stock", "preorder", "unknown"] = "unknown"
    checked_at: datetime = Field(default_factory=now)
    verification: Literal[
        "seller_structured_data",
        "shopify_storefront_json",
        "woocommerce_store_api",
        # Seller-declared OpenGraph product meta tags or microdata (one INR price).
        "seller_meta_tags",
        # The seller's own product API (robu.in GraphQL), read where its pages are challenged.
        "seller_product_api",
    ] = "seller_structured_data"
    seller_trust: Literal["unverified"] = "unverified"
    # Seller-declared only (JSON-LD or fixed page phrases); None means unknown or conflicting.
    tax_included: bool | None = None
    tax_evidence: str | None = Field(default=None, max_length=300)
    shipping_inr: None = None
    compatibility_status: Literal[
        "not_checked", "unknown", "compatible", "changes_required", "incompatible"
    ] = "not_checked"
    specs: PartSpecs = Field(default_factory=PartSpecs)
    spec_evidence: list[SpecEvidence] = Field(default_factory=list)
    spec_conflicts: list[SpecConflict] = Field(default_factory=list)
    compatibility: Compatibility | None = None
    research_assessment: ResearchAssessment | None = None
    trust: SellerTrust | None = None
    # Spec match for this line (None: not judged, e.g. the judge is disabled).
    match: OfferMatch | None = None
    # Pieces per listing when the listing is a pack ("pack of 10"); None: not stated.
    pack_qty: int | None = Field(default=None, ge=1, le=100000)
    # Add-to-cart support worked out by the cart engine (sourcing/cart_engine.py): the
    # product id read from this listing's own add-to-cart form, and the store's link recipe.
    cart_id: str | None = Field(default=None, pattern=r"^[\w-]{1,40}$")
    cart_recipe: CartRecipe | None = None


class SearchAttribution(Model):
    source_urls: list[str] = Field(default_factory=list)
    search_queries: list[str] = Field(default_factory=list)
    search_suggestions_html: str | None = None


class PartImage(Model):
    url: str
    kind: Literal["seller", "source", "category", "generated", "placeholder"]
    label: str
    source_url: HttpUrl | None = None


class PartImages(Model):
    candidates: list[PartImage] = Field(default_factory=list)
    fallback: PartImage
    generation_status: Literal["not_needed", "not_requested", "ready", "pending", "unavailable"]


class ImageRequest(Model):
    failed_urls: list[Annotated[str, Field(max_length=4096)]] = Field(
        default_factory=list, max_length=10
    )


CostStatus = Literal["known", "estimated", "unknown"]
SignedMoney = Annotated[str, Field(pattern=r"^-?\d+\.\d{2}$")]


class CostAmount(Model):
    """An auditable amount; `unknown` has no amount, only the parts that could be estimated."""

    amount_inr: Money | None = None
    status: CostStatus = "unknown"
    partial_inr: Money | None = None
    assumptions: list[str] = Field(default_factory=list)


class ShippingPolicyRef(Model):
    seller: str
    free_above_inr: Money | None = None
    free_when: Literal["above", "at_or_above"] = "above"
    flat_fee_inr: Money | None = None
    fee_plus_gst: bool = False
    unverified: bool = False
    source_url: HttpUrl | None = None
    checked_on: date | None = None
    note: str | None = None


class SellerCost(Model):
    seller: str
    line_ids: list[str] = Field(default_factory=list)
    parts: CostAmount
    gst: CostAmount
    shipping: CostAmount
    total: CostAmount
    free_shipping_gap_inr: Money | None = None
    policy: ShippingPolicyRef | None = None


class ImportReference(Model):
    """Unit price from a US/global distributor, used only for the import comparison."""

    price_usd: Money
    source: Literal["user", "research_fact"] = "user"
    source_url: HttpUrl | None = None
    quote: str | None = Field(default=None, max_length=1000)


class ImportBaseline(Model):
    line_ids: list[str] = Field(default_factory=list)
    complete: bool = False
    goods_usd: Money
    fx_usd_inr: str
    goods_inr: CostAmount
    courier_inr: CostAmount
    duty_inr: CostAmount
    landed_inr: CostAmount
    formula: str
    sources: list[str] = Field(default_factory=list)


class SavingsEstimate(Model):
    amount_inr: SignedMoney
    status: Literal["estimated"] = "estimated"
    assumptions: list[str] = Field(default_factory=list)


class CostBreakdown(Model):
    """Estimated cost of chosen offers; never a final payable or checkout total."""

    basis: Literal["selected_offers", "plan"] = "selected_offers"
    complete: bool = False
    sellers: list[SellerCost] = Field(default_factory=list)
    parts: CostAmount
    gst: CostAmount
    shipping: CostAmount
    total: CostAmount
    excluded_line_ids: list[str] = Field(default_factory=list)
    import_baseline: ImportBaseline | None = None
    savings_vs_import: SavingsEstimate | None = None
    rates_checked_on: date | None = None
    disclaimer: str = (
        "Estimate from seller-published prices and dated policy and tax assumptions; "
        "not a final payable total. Check the seller's checkout."
    )


class PlanPick(Model):
    line_id: str
    offer_url: HttpUrl
    seller: str
    price_inr: Money
    # Cheapest and fewest-seller plans only use A/B offers; the recommended plan can include
    # an offer whose compatibility is still unknown (None) or graded C/D.
    grade: Literal["A", "B", "C", "D"] | None
    changes_required: bool = False
    qty: int | None = None
    packs: int | None = None


class CartPlan(Model):
    kind: Literal["cheapest", "fewest_sellers", "recommended"]
    picks: list[PlanPick] = Field(default_factory=list)
    seller_count: int = 0
    costing: CostBreakdown
    matches_selection: bool = False


class CartPlans(Model):
    """Suggestions only: plans never change the user's selection."""

    plans: list[CartPlan] = Field(default_factory=list)
    method: Literal["exhaustive", "greedy", "none"] = "none"
    uncovered_line_ids: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    seller_penalty_inr: Money | None = None


class LineImage(Model):
    """The one image to show for a line, resolved in a fixed order (recommendations.md)."""

    url: str
    kind: Literal[
        "selected_offer", "recommended_offer", "offer", "reference", "category", "placeholder"
    ]
    label: str
    source_url: HttpUrl | None = None


class LineRecommendation(Model):
    """Deterministic recommendation for one line; reasons explain every scoring factor."""

    status: Literal["recommended", "unsourced"]
    offer_url: HttpUrl | None = None
    seller: str | None = None
    score: float | None = Field(default=None, ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    # Why the recommendation was not applied as the selection (selection rules), if not.
    blocked_reason: str | None = None
    unsourced_reason: (
        Literal["pending", "needs_value", "no_offers", "no_acceptable_offer", "needs_quantity"]
        | None
    ) = None
    next_steps: list[str] = Field(default_factory=list)
    qty: int | None = None
    pack_qty: int | None = None
    packs: int | None = None
    method: Literal["deterministic_score"] = "deterministic_score"


class OrderPlanLine(Model):
    line_id: str
    name: str
    offer_url: HttpUrl
    title: str | None = None
    qty: int
    pack_qty: int | None = None
    packs: int
    units: int
    unit_price_inr: Money
    line_price_inr: Money
    selection_source: Literal["recommended", "user"] | None = None
    selected: bool = False
    grade: Literal["A", "B", "C", "D", "X"] | None = None
    changes_required: bool = False
    blocked_reason: str | None = None
    # Adds this line's packs to the seller's cart (cart engine recipe), when one is known.
    cart_url: HttpUrl | None = None


class OrderPlanSeller(Model):
    seller: str
    lines: list[OrderPlanLine] = Field(default_factory=list)
    subtotal_inr: Money
    gst: CostAmount
    shipping: CostAmount
    total: CostAmount
    free_shipping_gap_inr: Money | None = None
    policy: ShippingPolicyRef | None = None
    product_links: list[HttpUrl] = Field(default_factory=list)
    # One link that adds every line in `cart_line_ids` to this seller's cart, when the
    # store's recipe supports several items; `cart_replaces` when it empties the cart first.
    cart_url: HttpUrl | None = None
    cart_line_ids: list[str] = Field(default_factory=list)
    cart_replaces: bool = False


class UnsourcedLine(Model):
    line_id: str
    name: str
    reason: Literal[
        "pending",
        "needs_value",
        "no_offers",
        "no_acceptable_offer",
        "needs_quantity",
        "cleared_by_user",
    ]
    message: str
    next_steps: list[str] = Field(default_factory=list)
    research_urls: list[HttpUrl] = Field(default_factory=list)


class FabricationService(Model):
    """An online service that makes the part from the maker's files.

    `checked_live`: the page was fetched and read when the service was found (grounded
    search, sourcing/fabrication.py). False marks a curated fallback entry that was not
    checked live. Shipping to India is the service page's claim, not verified by us.
    """

    name: str = Field(min_length=1, max_length=100)
    url: HttpUrl
    note: str | None = Field(default=None, max_length=300)
    ships_to_india: Literal["yes", "unknown"] = "unknown"
    checked_live: bool = False
    checked_at: datetime | None = None


class FabricationPlan(Model):
    """How to get a made-to-order line: services to order from and the files to upload."""

    kind: Literal["3d_print", "pcb"]
    services: list[FabricationService] = Field(default_factory=list, max_length=4)
    # What the service needs, e.g. "STL or STEP file of the part".
    upload: str = Field(min_length=1, max_length=200)
    # Design files linked from the project's own sources (repository, model page).
    design_links: list[HttpUrl] = Field(default_factory=list, max_length=4)
    method: Literal["grounded_search_page_checked", "curated_fallback"]
    note: str = (
        "Made to order: upload the design files to a service and order there. Price, "
        "delivery and India shipping are set by the service; check before ordering."
    )


class MadeToOrderLine(Model):
    line_id: str
    name: str
    fabrication: FabricationPlan


class OrderPlan(Model):
    """Seller-grouped order built from selections, else recommendations; an estimate only."""

    sellers: list[OrderPlanSeller] = Field(default_factory=list)
    unsourced: list[UnsourcedLine] = Field(default_factory=list)
    # Lines ordered from a fabrication service; not in seller carts and not unsourced.
    made_to_order: list[MadeToOrderLine] = Field(default_factory=list)
    seller_count: int = 0
    costing: CostBreakdown
    ready: bool = False
    disclaimer: str = (
        "Recommendations are automatic and deterministic; check each seller page and "
        "checkout before ordering. Totals are estimates, not a payable amount."
    )


class SetImportReference(Model):
    line_id: LineRef
    price_usd: Money | None = None
    source_url: HttpUrl | None = None


class SetImportReferences(Model):
    references: list[SetImportReference] = Field(min_length=1, max_length=100)


class SellerSearchSummary(Model):
    """Direct seller-catalogue search for one line. Candidate URLs are unverified leads."""

    queries: list[str] = Field(default_factory=list, max_length=4)
    candidate_urls: list[str] = Field(default_factory=list, max_length=20)
    sellers_checked: int = 0
    # Hosts that answered with a bot-protection challenge (or are recorded as doing so).
    blocked_sellers: list[str] = Field(default_factory=list, max_length=20)
    message: str = Field(default="", max_length=500)


# research_skipped: the research review was skipped (a sufficient offer or the budget), so no
# model call was made for it.
SourcingStage = Literal[
    "seller_search",
    "provider_search",
    "judge",
    "grounded",
    "known_urls",
    "research",
    "research_skipped",
    "followup",
    # AI buyer: decided an unstated value; chose what to buy; searched again in its words.
    "buyer_value",
    "buyer",
    "buyer_search",
    # Made-to-order line: fabrication services linked instead of a seller search.
    "fabrication",
]


CodePatchReason = Literal[
    "no_code",
    "file_not_read",
    "no_substitute",
    "recipe_not_applicable",
    "no_code_change_needed",
    "ai_failed_validation",
    "out_of_scope_mcu",
    "budget",
    "source_changed",
]


class CodePatchFile(Model):
    path: str = Field(min_length=1, max_length=300)
    diff: str = Field(max_length=60_000)
    source_url: str = Field(max_length=600)
    # sha256 of the file as read; downloads re-read the file and refuse if it changed.
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


CompileReason = Literal[
    "source_changed",
    "source_unavailable",
    "sketch_not_found",
    "platformio_not_supported",
    "too_large",
    "launch_failed",
    "runner_error",
]


class CompileCheck(Model):
    """One compile-only check of a code patch in the isolated runner (code-adapt tier 3).

    queued until the runner reports. compiles / compile_failed come from arduino-cli for
    `fqbn` with the pinned `core`; a compile never uploads, runs or tests on hardware.
    unavailable always carries a reason. A queued check past `expires_at` has timed out and
    can be requested again. AI drafts that fail get at most two repair rounds (`repairs`);
    each round replaces the patch's diffs and resets `accepted`.
    """

    status: Literal["queued", "compiles", "compile_failed", "unavailable", "timeout"]
    fqbn: str = Field(max_length=100)
    board: str = Field(max_length=100)
    run_id: str = Field(max_length=200)
    attempt: int = Field(default=1, ge=1, le=3)
    repairs: int = Field(default=0, ge=0, le=2)
    reason: CompileReason | None = None
    detail: str | None = Field(default=None, max_length=500)
    # First compiler error lines (at most 40), with runner paths made sketch-relative.
    log: str | None = Field(default=None, max_length=6000)
    core: str | None = Field(default=None, max_length=100)
    size: str | None = Field(default=None, max_length=300)
    sketch: str | None = Field(default=None, max_length=300)
    requested_at: datetime = Field(default_factory=now)
    expires_at: datetime
    finished_at: datetime | None = None


class CompileRequest(Model):
    # Arduino FQBN from GET /v1/compile/boards; defaults to the board found in the BOM.
    fqbn: str | None = Field(default=None, max_length=100, pattern=r"^[\w.-]+:[\w.-]+:[\w.-]+$")


class CompileBoard(Model):
    fqbn: str
    label: str
    family: str


class CompileBoards(Model):
    enabled: bool
    boards: list[CompileBoard]


class CodePatch(Model):
    """Code changes for a substituted part; never tested on hardware.

    origin: curated (a maintained recipe) or ai_draft (model-written, validated, must be
    accepted by the owner). check: not_checked until a compile check finishes (`compile`),
    then compiles or compile_failed. status unavailable always carries a reason; notes
    always list the non-code changes.
    """

    status: Literal["ready", "unavailable"]
    origin: Literal["curated", "ai_draft"] | None = None
    check: Literal["not_checked", "compiles", "compile_failed"] = "not_checked"
    reason: CodePatchReason | None = None
    detail: str | None = Field(default=None, max_length=500)
    from_catalog_id: str | None = None
    to_catalog_id: str | None = None
    offer_url: HttpUrl | None = None
    files: list[CodePatchFile] = Field(default_factory=list, max_length=8)
    applied: list[str] = Field(default_factory=list, max_length=20)
    skipped: list[str] = Field(default_factory=list, max_length=20)
    notes: list[str] = Field(default_factory=list, max_length=20)
    assumptions: list[str] = Field(default_factory=list, max_length=10)
    accepted: bool = False
    ai_calls: int = Field(default=0, ge=0, le=10)
    created_at: datetime = Field(default_factory=now)
    compile: CompileCheck | None = None


class CodePatchRequest(Model):
    # Defaults to the line's selected offer.
    offer_url: HttpUrl | None = None


class BuyerDecision(Model):
    """What the AI buyer decided for a hard line, in plain words (docs/contracts/ai-buyer.md).

    value: a part value the source did not state, worked out from the circuit (the spec's
    param carries the same reason). fit/offer_url: the listing it chose when nothing was
    accepted (substitute offers are grade B with the changes listed). searched: extra store
    searches it asked for. Decisions are suggestions for review, never verified facts.
    """

    value: str | None = Field(default=None, max_length=150)
    value_reason: str | None = Field(default=None, max_length=400)
    value_confidence: Literal["high", "medium", "low"] | None = None
    fit: Literal["exact", "substitute", "kit"] | None = None
    offer_url: HttpUrl | None = None
    reason: str | None = Field(default=None, max_length=400)
    changes: list[str] = Field(default_factory=list, max_length=4)
    searched: list[str] = Field(default_factory=list, max_length=6)
    model: str | None = None


class ReportLine(Model):
    item: BomItem
    sourcing_status: SourcingStatus
    resolution: PartResolution | None = None
    # The spec this line was sourced with (item spec, or a seed spec from the name).
    buyable_spec: BuyableSpec | None = None
    # Set with sourcing_status "fabrication_service" (made-to-order lines).
    fabrication: FabricationPlan | None = None
    offers: list[VerifiedOffer] = Field(default_factory=list)
    image_candidates: list[PartImage] = Field(default_factory=list)
    attribution: SearchAttribution | None = None
    research: PartResearch | None = None
    sourcing_error: "ErrorDetail | None" = None
    selected_offer_url: HttpUrl | None = None
    price_inr: Money | None = None
    subtotal_inr: Money | None = None
    grade: Literal["A", "B"] | None = None
    changes_accepted: bool = False
    research_accepted: bool = False
    import_reference: ImportReference | None = None
    # recommended: applied automatically; user: chosen (or cleared) through /selections and
    # never replaced by recomputation. None: no selection yet, or saved before recommendations.
    selection_source: Literal["recommended", "user"] | None = None
    # The user's own choice, kept across refreshes and spec updates; None with
    # selection_source "user" means the user cleared the line.
    user_offer_url: HttpUrl | None = None
    # True when this line's "user" selection was copied from a shared project and the new
    # owner has not chosen an offer since; shown as "Copied choice".
    copied_choice: bool = False
    recommended_offer_url: HttpUrl | None = None
    recommendation: LineRecommendation | None = None
    line_image: LineImage | None = None
    seller_search: SellerSearchSummary | None = None
    # Sourcing stages in the order they ran, and the paid model calls the line used.
    stages: list[SourcingStage] = Field(default_factory=list, max_length=12)
    gemini_calls: int = Field(default=0, ge=0)
    buyer: BuyerDecision | None = None
    # Owner-only; removed from share links and shared exports.
    code_patch: CodePatch | None = None


class Report(Model):
    demo: bool = True
    summary: str
    lines: list[ReportLine]
    total_inr: None = None
    parts_subtotal_inr: Money | None = None
    selected_parts_subtotal_inr: Money = "0.00"
    shipping_inr: None = None
    tax_inr: None = None
    unselected_line_ids: list[str] = Field(default_factory=list)
    costing: CostBreakdown | None = None
    order_plan: OrderPlan | None = None


class SafetyTrigger(Model):
    """Which saved text made a deterministic safety rule fire."""

    line_id: str | None = None
    field: str = Field(min_length=1, max_length=100)
    matched: str = Field(min_length=1, max_length=200)


class SafetyFlag(Model):
    """Hard-coded rule output (`safety.py`) with templated text; never written by a model."""

    code: Literal["MAINS", "LIPO", "HIGH_CURRENT", "LEVEL_SHIFT"]
    severity: Literal["danger", "warning", "caution"]
    title: str
    message: str
    guidance: list[str] = Field(default_factory=list)
    line_ids: list[str] = Field(default_factory=list)
    triggers: list[SafetyTrigger] = Field(default_factory=list, max_length=20)
    method: Literal["deterministic_rules"] = "deterministic_rules"
    rule_version: str


class UpdateProject(Model):
    title: ProjectTitle | None = None
    description: ProjectDescription | None = None

    @model_validator(mode="after")
    def require_field(self):
        if self.title is None and self.description is None:
            raise ValueError("Provide a title or a description")
        return self


class SourceReport(Model):
    """How one submitted source was read during extraction."""

    url: str
    kind: Literal[
        "video", "instructables", "hackster", "github", "adafruit", "blog", "youtube_description"
    ]
    role: Literal["primary", "additional"] = "primary"
    status: Literal["read", "failed"]
    item_count: int = Field(default=0, ge=0)
    code_item_count: int = Field(default=0, ge=0)
    error: "ErrorDetail | None" = None
    # "youtube_description" when this extra source was a link in the video's description.
    found_in: Literal["youtube_description"] | None = None


class VideoLink(Model):
    """One link from a YouTube description; only project pages are followed as sources."""

    url: str = Field(min_length=1, max_length=500)
    kind: Literal["project_source", "video", "store", "other"]
    followed: bool = False


class JobVideoMeta(Model):
    """YouTube Data API snippet facts kept on a job; never the full description.

    API data must be refreshed or deleted after 30 days: once `fetched_at` is older,
    responses clear `title`, `channel`, `published_at` and `links`, drop description
    quotes from evidence and set `expired`.
    """

    video_id: str = Field(pattern=r"^[A-Za-z0-9_-]{11}$")
    title: str | None = Field(default=None, max_length=200)
    channel: str | None = Field(default=None, max_length=200)
    published_at: datetime | None = None
    fetched_at: datetime
    links: list[VideoLink] = Field(default_factory=list, max_length=20)
    expired: bool = False


class CostEstimate(Model):
    """Estimated Gemini spend for this job from logged token counts and a dated price table.

    An estimate for budgeting, not a bill: grounding queries are priced as if the monthly
    free tier were used up. `run_usd` is the current sourcing run, which the budget limits.
    """

    method: Literal["estimated_from_token_counts"] = "estimated_from_token_counts"
    total_usd: float = Field(default=0, ge=0)
    run_usd: float = Field(default=0, ge=0)
    budget_usd: float | None = None
    budget_reached: bool = False
    calls: int = Field(default=0, ge=0)
    search_queries: int = Field(default=0, ge=0)
    calls_by_site: dict[str, int] = Field(default_factory=dict)
    usd_by_site: dict[str, float] = Field(default_factory=dict)
    # Shared-cache hits by namespace (discovery, judge, page, seller_search, research).
    cache_hits: dict[str, int] = Field(default_factory=dict)
    prices_checked: str | None = None
    updated_at: datetime = Field(default_factory=now)


class CopiedFrom(Model):
    """Provenance of a copy. The source project is not identified: its owner shared a
    link, not their project id."""

    copied_at: datetime
    # When the source project was last updated; seller prices are from then or earlier.
    source_updated_at: datetime


# Project overview (docs/contracts/project-overview.md): AI-drawn parts and wiring, checked
# by rules and a second AI call. Nothing here is verified against the physical board.
OverviewVerdict = Literal["confirmed", "unverified", "disputed"]
OverviewSide = Literal["top", "bottom", "left", "right"]
Fraction = Annotated[float, Field(ge=0, le=1, allow_inf_nan=False)]


class PartBody(Model):
    width_mm: float = Field(ge=1, le=300, allow_inf_nan=False)
    height_mm: float = Field(ge=1, le=300, allow_inf_nan=False)
    color: Literal["blue", "black", "green", "red", "purple", "yellow", "white", "silver", "orange"]
    shape: Literal["rect", "rounded", "round", "pouch"]


class PartChip(Model):
    """The main chip or module can, as fractions of the body."""

    label: str = Field(min_length=1, max_length=24)
    x: Fraction
    y: Fraction
    w: Fraction
    h: Fraction


class PartFeature(Model):
    type: Literal["screen", "led", "button", "antenna", "touch_pad", "lens", "label"]
    x: Fraction
    y: Fraction
    w: Fraction
    h: Fraction
    text: str | None = Field(default=None, min_length=1, max_length=24)


class PartConnector(Model):
    type: Literal["usb_c", "micro_usb", "jst", "barrel", "screw_terminal", "pin_socket"]
    side: OverviewSide
    position: Fraction


class Pin(Model):
    """One header pin; `name` is the silkscreen label wires refer to."""

    name: str = Field(min_length=1, max_length=16)
    kind: Literal["power", "ground", "gpio", "analog", "i2c", "spi", "uart", "control", "other"]
    functions: list[Annotated[str, Field(min_length=1, max_length=24)]] = Field(
        default_factory=list, max_length=4
    )


class PinHeader(Model):
    side: OverviewSide
    pins: list[Pin] = Field(min_length=1, max_length=40)


class PartVisual(Model):
    line_id: str = Field(min_length=1, max_length=20)
    label: str = Field(min_length=1, max_length=40)
    kind: Literal[
        "board", "module", "sensor", "display", "battery", "switch", "passive", "connector", "other"
    ]
    body: PartBody
    chip: PartChip | None = None
    features: list[PartFeature] = Field(default_factory=list, max_length=8)
    connectors: list[PartConnector] = Field(default_factory=list, max_length=4)
    headers: list[PinHeader] = Field(default_factory=list, max_length=4)
    pin_source: Literal["code", "datasheet_knowledge", "ai_inferred"] = "ai_inferred"
    verdict: OverviewVerdict = "unverified"
    verdict_reason: str | None = Field(default=None, max_length=300)


class WireEnd(Model):
    line_id: str = Field(min_length=1, max_length=20)
    pin: str = Field(min_length=1, max_length=16)


class WireConnection(Model):
    # `from` is a Python keyword: the field is `from_` in code and `from` in JSON.
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        serialize_by_alias=True,
        validate_by_alias=True,
        validate_by_name=True,
    )

    id: str = Field(pattern=r"^W\d{2,3}$")
    from_: WireEnd = Field(alias="from")
    to: WireEnd
    signal: Literal[
        "power", "ground", "i2c_sda", "i2c_scl", "spi", "uart", "digital", "analog", "pwm", "other"
    ]
    label: str | None = Field(default=None, max_length=40)
    source: Literal["code", "description", "ai_inferred"] = "ai_inferred"
    evidence: str | None = Field(default=None, max_length=200)
    verdict: OverviewVerdict = "unverified"
    reason: str | None = Field(default=None, max_length=300)
    # Deterministic validator findings (overview.py), never model text.
    problems: list[str] = Field(default_factory=list, max_length=6)


class OverviewJudge(Model):
    status: Literal["passed", "issues", "skipped", "pending"] = "pending"
    summary: str | None = Field(default=None, max_length=300)
    # Final verdict counts over parts and wires (after pin-header verdicts are applied).
    confirmed: int = Field(default=0, ge=0)
    unverified: int = Field(default=0, ge=0)
    disputed: int = Field(default=0, ge=0)


class ResolvedSpec(Model):
    """An open spec question the drawing settled, so the maker is not asked it."""

    line_id: str
    field: str = Field(max_length=40)
    value: str = Field(max_length=200)
    reason: str | None = Field(default=None, max_length=300)
    # drawing: read off the drawn pin headers; wiring: decided by the wiring call from the
    # code, the wires it drew and the project context.
    source: Literal["drawing", "wiring"]


class ProjectOverview(Model):
    """AI-inferred drawing of the project; never verified against the physical board."""

    status: Literal["pending", "ready", "failed", "stale"]
    # While pending, what is being drawn; parts (then wires) already drawn are included.
    stage: Literal["parts", "wiring", "checking"] | None = None
    message: str | None = Field(default=None, max_length=300)
    generated_at: datetime | None = None
    items_hash: str | None = Field(default=None, max_length=64)
    demo: bool = False
    parts: list[PartVisual] = Field(default_factory=list, max_length=40)
    wiring: list[WireConnection] = Field(default_factory=list, max_length=120)
    judge: OverviewJudge = Field(default_factory=OverviewJudge)
    notes: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(
        default_factory=list, max_length=10
    )
    # Applied to the lines (BomItem.ai_specs) when the drawing is saved; those questions go.
    resolved: list[ResolvedSpec] = Field(default_factory=list, max_length=120)


class BuildStep(Model):
    """One AI-inferred build step (build_guide.py); never verified against the build."""

    title: str = Field(min_length=1, max_length=120)
    detail: str = Field(default="", max_length=600)
    # Parts used in this step; every id is a line on the job.
    line_ids: list[str] = Field(default_factory=list, max_length=40)
    # A moment in the source video (MM:SS or H:MM:SS) where the evidence shows this step;
    # always a video evidence timestamp of a line used in this step, and never shared with
    # another step of the same guide (null when the evidence has no moment of its own).
    timestamp: str | None = Field(default=None, pattern=r"^\d+:[0-5]\d(:[0-5]\d)?$")
    caution: str | None = Field(default=None, max_length=200)
    origin: Literal["ai_inferred"] = "ai_inferred"


def step_seconds(timestamp: str) -> int:
    """A BuildStep timestamp ("MM:SS" or "H:MM:SS") in seconds."""
    total = 0
    for part in timestamp.split(":"):
        total = total * 60 + int(part)
    return total


def clear_shared_timestamps(steps: list[BuildStep]) -> None:
    """Clear every timestamp that more than one step cites.

    One video moment cannot be the moment of two different steps; a shared time is a part
    sighting reused across steps, so no step keeps it (never a guess at which one owns it).
    """
    counts = Counter(step_seconds(s.timestamp) for s in steps if s.timestamp)
    for step in steps:
        if step.timestamp and counts[step_seconds(step.timestamp)] > 1:
            step.timestamp = None


class BuildGuide(Model):
    """AI-written build steps for a finished project; never verified."""

    status: Literal["pending", "ready", "failed", "stale"]
    message: str | None = Field(default=None, max_length=300)
    generated_at: datetime | None = None
    items_hash: str | None = Field(default=None, max_length=64)
    demo: bool = False
    steps: list[BuildStep] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def distinct_timestamps(self):
        # Also cleans guides stored before the build_guide.py guard existed.
        clear_shared_timestamps(self.steps)
        return self


class BuildProgress(Model):
    """Tick (or untick) one parts-checklist line as received on the build page."""

    line_id: str = Field(min_length=1, max_length=20)
    received: bool


class Job(Model):
    job_id: str
    status: Status = "queued"
    demo: bool = True
    input: CreateJob
    project: ProjectContext | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    items: list[BomItem] = Field(default_factory=list)
    # Lines the reconcile pass merged into another or left out, with reasons (reconcile.py).
    reconciled: list[ReconciledLine] = Field(default_factory=list, max_length=60)
    # Live steps while the sources are read (jobs.py); kept afterwards as a record.
    extraction_progress: list[ExtractionStep] = Field(default_factory=list, max_length=12)
    events: list[Event] = Field(default_factory=list)
    report: Report | None = None
    error: "ErrorDetail | None" = None
    extraction_model: str | None = None
    sourcing_enabled: bool = False
    recovery_attempts: int = Field(default=0, ge=0)
    refresh_count: int = Field(default=0, ge=0)
    refresh_limit: int | None = Field(
        default=2, ge=0, description="Seller refresh batch limit; null for exempt testing accounts."
    )
    pause_requested: bool = False
    messages: list[ChatMessage] = Field(default_factory=list)
    chat_state: Literal["idle", "queued", "thinking", "failed"] = "idle"
    chat_error: "ErrorDetail | None" = None
    resistor_advice: list[ResistorAdvice] = Field(default_factory=list)
    actions: list[ActionRecord] = Field(default_factory=list)
    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    source_reports: list[SourceReport] = Field(default_factory=list, max_length=5)
    video_meta: JobVideoMeta | None = None
    cost_estimate: CostEstimate | None = None
    # Set on projects created with "Copy to my projects" from a share link.
    copied_from: CopiedFrom | None = None
    # AI-drawn parts and wiring for the review step (overview.py); None until drawn.
    overview: ProjectOverview | None = None
    # Build page: line ids the maker ticked as received (POST /build-progress).
    build_received: list[str] = Field(default_factory=list, max_length=100)
    # AI-written build steps for the build page (build_guide.py); None until requested.
    build_guide: BuildGuide | None = None


class AccountSettings(Model):
    """Per-account preferences, saved by the owner (accounts only, not guests)."""

    # Default delivery country for new projects.
    country: CountryCode = DEFAULT_COUNTRY
    updated_at: datetime | None = None


class CopiedProject(Model):
    job_id: str
    job_token: str
    status: Status


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
