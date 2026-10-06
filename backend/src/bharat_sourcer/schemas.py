from datetime import UTC, date, datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints, model_validator


def now() -> datetime:
    return datetime.now(UTC)


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


Name = Annotated[str, Field(min_length=1, max_length=200)]
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


class CreateJob(Model):
    url: HttpUrl
    pin: str | None = Field(default=None, pattern=r"^[1-9][0-9]{5}$")
    lang: Literal["en", "hi", "ta", "ml"] = "en"
    user_level: Literal["beginner", "intermediate"] = "beginner"
    visibility: Literal["unlisted"] = "unlisted"
    # Extra sources about the same build (e.g. its project page or repository), fused into
    # one BOM with the primary `url`. Same validation as `url`; at most one video in total.
    sources: list[HttpUrl] = Field(default_factory=list, max_length=3)


class Evidence(Model):
    """Model-reported provenance for an extracted BOM line.

    `source` defaults to `video` so snapshots saved before project-page support still
    validate. Video evidence carries a timestamp. Project-page evidence carries the fetched
    document `url` and a `quote` the server found verbatim (whitespace-normalised) in it.
    Code evidence is deterministic: the repository `file` and 1-based `line`, the line's
    text as `quote`, and a `url` to that line.
    """

    timestamp: str | None = Field(default=None, pattern=r"^\d{2,}:[0-5]\d$")
    observation: str = Field(min_length=1, max_length=1000)
    source: Literal["video", "project_page", "code"] = "video"
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
        return self


class PartSpecs(Model):
    family: str | None = Field(default=None, min_length=1, max_length=100)
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
        if (
            self.family in controllers
            and self.controller
            and (self.controller not in controllers[self.family])
        ):
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
    # "catalog" values come from the curated parts catalogue, never from a seller.
    source: Literal[
        "part_name", "user", "seller_title", "seller_property", "seller_table", "catalog"
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
    source: Literal["video", "project_page", "code"]
    url: HttpUrl | None = None
    locator: str | None = Field(default=None, max_length=300)


class ItemConflict(Model):
    """Sources disagree about this line; nothing is picked silently (see multi-source-intake)."""

    kind: Literal["identity_mismatch", "qty_mismatch"]
    message: str = Field(min_length=1, max_length=500)
    values: list[ConflictValue] = Field(default_factory=list, max_length=6)


class BomItem(Model):
    line_id: str
    raw_name: Name
    qty: Quantity | None = 1
    qty_unit: Literal["pcs"] = "pcs"
    # stated: the source gives the count; inferred: decided from project context; user: edited.
    qty_source: Literal["stated", "inferred", "user"] = "stated"
    qty_reason: str | None = Field(default=None, max_length=300)
    user_has_it: bool = False
    evidence: list[Evidence] = Field(default_factory=list)
    user_edited: bool = False
    specs: PartSpecs = Field(default_factory=PartSpecs)
    requirements: list[PartRequirement] = Field(default_factory=list, max_length=20)
    clarifications: list[Clarification] = Field(default_factory=list)
    lookalikes: list[Lookalike] = Field(default_factory=list, max_length=10)
    conflicts: list[ItemConflict] = Field(default_factory=list, max_length=10)
    # Deterministic, from evidence at extraction time; None for lines without an assessment
    # (user-added, renamed or saved before confidence existed).
    confidence: Literal["verified", "likely", "check"] | None = None
    confidence_reason: str | None = Field(default=None, max_length=300)


class UpdateLine(Model):
    op: Literal["update"]
    line_id: str
    raw_name: Name | None = None
    qty: Quantity | None = None
    specs: PartSpecs | None = None
    requirements: list[PartRequirement] | None = Field(default=None, max_length=20)

    @model_validator(mode="after")
    def require_change(self):
        if all(v is None for v in (self.raw_name, self.qty, self.specs, self.requirements)):
            raise ValueError("An update requires raw_name, qty, specs or requirements")
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
    requirements: list[PartRequirement] = Field(default_factory=list, max_length=20)


Edit = Annotated[UpdateLine | RemoveLine | HaveLine | AddLine, Field(discriminator="op")]


class ConfirmJob(Model):
    edits: list[Edit] = Field(default_factory=list, max_length=100)


class SelectOffer(Model):
    line_id: str
    offer_url: HttpUrl | None = None
    accept_changes: bool = False
    accept_research_assessment: bool = False


class SelectOffers(Model):
    selections: list[SelectOffer] = Field(min_length=1, max_length=100)


class RefreshOffers(Model):
    line_ids: list[str] = Field(min_length=1, max_length=30)


class UpdatePartSpecs(Model):
    line_id: str
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
    line_id: str
    purpose: Literal["unknown", "led_series", "piezo_input", "pull_up", "other"] = "unknown"
    question: str = Field(min_length=1, max_length=1000)


class ResistorInputs(Model):
    line_id: str
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


class RefreshLineResult(Model):
    """Snapshot of one refreshed line when its batch ended; later refreshes do not edit it."""

    line_id: str
    sourcing_status: Literal[
        "not_run", "already_owned", "offers_found", "no_verified_offers", "failed"
    ]
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


StorePlatform = Literal["shopify", "woocommerce", "magento", "jsonld", "unknown"]


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


class VerifiedOffer(Model):
    url: HttpUrl
    seller: str
    title: str
    image_url: HttpUrl | None = None
    price_inr: str = Field(pattern=r"^\d+\.\d{2}$")
    currency: Literal["INR"] = "INR"
    stock: Literal["in_stock", "out_of_stock", "preorder", "unknown"] = "unknown"
    checked_at: datetime = Field(default_factory=now)
    verification: Literal[
        "seller_structured_data", "shopify_storefront_json", "woocommerce_store_api"
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
    failed_urls: list[str] = Field(default_factory=list, max_length=10)


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
    grade: Literal["A", "B"]
    changes_required: bool = False


class CartPlan(Model):
    kind: Literal["cheapest", "fewest_sellers"]
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


class SetImportReference(Model):
    line_id: str
    price_usd: Money | None = None
    source_url: HttpUrl | None = None


class SetImportReferences(Model):
    references: list[SetImportReference] = Field(min_length=1, max_length=100)


class ReportLine(Model):
    item: BomItem
    sourcing_status: Literal[
        "not_run", "already_owned", "offers_found", "no_verified_offers", "failed"
    ]
    resolution: PartResolution | None = None
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
    kind: Literal["video", "instructables", "hackster", "github", "adafruit", "blog"]
    role: Literal["primary", "additional"] = "primary"
    status: Literal["read", "failed"]
    item_count: int = Field(default=0, ge=0)
    code_item_count: int = Field(default=0, ge=0)
    error: "ErrorDetail | None" = None


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


class Job(Model):
    job_id: str
    status: Status = "queued"
    demo: bool = True
    input: CreateJob
    project: ProjectContext | None = None
    created_at: datetime = Field(default_factory=now)
    updated_at: datetime = Field(default_factory=now)
    items: list[BomItem] = Field(default_factory=list)
    events: list[Event] = Field(default_factory=list)
    report: Report | None = None
    error: "ErrorDetail | None" = None
    extraction_model: str | None = None
    sourcing_enabled: bool = False
    recovery_attempts: int = Field(default=0, ge=0)
    refresh_count: int = Field(default=0, ge=0)
    pause_requested: bool = False
    messages: list[ChatMessage] = Field(default_factory=list)
    chat_state: Literal["idle", "queued", "thinking", "failed"] = "idle"
    chat_error: "ErrorDetail | None" = None
    resistor_advice: list[ResistorAdvice] = Field(default_factory=list)
    actions: list[ActionRecord] = Field(default_factory=list)
    safety_flags: list[SafetyFlag] = Field(default_factory=list)
    source_reports: list[SourceReport] = Field(default_factory=list, max_length=4)
    cost_estimate: CostEstimate | None = None


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
