import re
from datetime import date
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ThinkingLevel = Literal["low", "medium", "high"]

# USD per 1M tokens (output includes thinking) and per executed grounding search query.
# Source: https://ai.google.dev/gemini-api/docs/pricing (page last modified 2026-10-01, read
# 2026-10-05; see backend/infra/gemini-cost-research-2026-10-05.md). Entries are dated so
# estimates follow the 2027-01-01 price change. These are budgeting estimates, not bills:
# the 5,000 free grounding queries per month are ignored, so search cost is an upper bound.
GEMINI_PRICES: dict[str, list[tuple[date, dict[str, float]]]] = {
    "gemini-3.8-flash": [
        (date(2026, 1, 1), {"input": 0.75, "output": 3.75, "cached": 0.075}),
        (date(2027, 1, 1), {"input": 1.50, "output": 7.50, "cached": 0.15}),
    ],
    "gemini-3.5-flash-lite": [(date(2026, 1, 1), {"input": 0.30, "output": 2.50, "cached": 0.03})],
    "gemini-3.1-flash-lite": [(date(2026, 1, 1), {"input": 0.25, "output": 1.50, "cached": 0.025})],
    "gemini-2.5-flash-lite": [(date(2026, 1, 1), {"input": 0.10, "output": 0.40, "cached": 0.01})],
}
GEMINI_SEARCH_QUERY_USD = 0.014  # $14 per 1,000 executed queries after the free tier
GEMINI_PRICES_CHECKED = "2026-10-05"
# Lower thinking where the task is classification or short structured output. Research
# keeps the model default (medium) until the evaluation harness shows low holds quality.
DEFAULT_SITE_THINKING: dict[str, ThinkingLevel] = {
    "chat_scope": "low",
    "discovery": "low",
    "judge": "low",
    "markets": "low",
    # Overview (overview.py): part drawings, wiring and judge verdicts are recall and short
    # structured output; low thinking took the Desk Buddy wiring from 53 s to 8 s.
    "overview": "low",
    "overview_judge": "low",
    "overview_wiring": "low",
    # Reconcile (reconcile.py) reasons about the whole build; low thinking missed duplicates
    # and left connections empty in the live check, medium found them.
    "reconcile": "medium",
    "spec": "low",
    "spec_fill": "low",
    # Cart engine (sourcing/cart_engine.py): one short structured answer per store.
    "cart_recipe": "low",
    # Build guide (build_guide.py): one short ordered list of steps from text context.
    "build_guide": "low",
    # Fabrication services (sourcing/fabrication.py): a grounded search, then page verdicts.
    "fabrication": "low",
}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BS_", env_file=".env", extra="ignore")

    demo_mode: bool = True
    integration_key: SecretStr | None = None
    auth_enabled: bool = False
    # Comma-separated Firebase UIDs exempt from the per-job seller-refresh batch cap.
    refresh_unlimited_uids: str = ""
    image_generation_enabled: bool = False
    image_model: str = Field(default="gemini-3.1-flash-lite-image", pattern=r"^[a-zA-Z0-9.-]+$")
    image_daily_limit: int = Field(default=30, ge=1, le=500)
    # Tier 2 of docs/plans/code-adapt: AI-drafted code patches (off until approved).
    code_adapt_ai: bool = False
    code_adapt_daily_limit: int = Field(default=50, ge=1, le=1000)
    # Tier 3: compile checks in isolated Cloud Run jobs (backend/compile, compile_check.py).
    # none: the compile route answers 503 COMPILE_UNAVAILABLE.
    compile_backend: Literal["none", "cloud_run_job"] = "none"
    compile_region: str = Field(default="asia-south1", pattern=r"^[a-z0-9-]+$")
    # Jobs are named <prefix>-<family>, one per runner image (avr, esp32, esp8266, rp2040).
    compile_job_prefix: str = Field(default="bharat-sourcer-compile", pattern=r"^[a-z][a-z0-9-]+$")
    # The runner's identity; only ID tokens for this account reach /internal/compile.
    compile_service_account: str | None = None
    # ID-token audience: this API's public URL (defaults to BS_TASKS_URL).
    compile_audience: str | None = None
    compile_daily_limit: int = Field(default=100, ge=1, le=2000)
    guest_session_secret: SecretStr | None = None
    guest_session_days: int = Field(default=14, ge=1, le=30)
    guest_part_limit: int = Field(default=3, ge=1, le=10)
    account_daily_actions: int = Field(default=40, ge=1, le=1000)
    guest_daily_actions: int = Field(default=5, ge=1, le=50)
    global_daily_actions: int = Field(default=1000, ge=1)
    ip_daily_actions: int = Field(default=100, ge=1)
    trusted_proxy_ip_header: bool = False
    dispatch_backend: Literal["local", "cloud_tasks"] = "local"
    tasks_location: str = "asia-south1"
    tasks_queue: str = "bharat-sourcer"
    tasks_url: str | None = None
    tasks_service_account: str | None = None
    sweep_limit: int = Field(default=200, ge=1, le=1000)
    queue_age_alert_minutes: int = Field(default=30, ge=5, le=1440)
    storage_backend: Literal["memory", "firestore"] = "memory"
    gcp_project: str | None = None
    firestore_database: str = "(default)"
    firestore_collection: str = Field(default="backend_jobs", pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    recovery_interval_s: float = Field(default=30, ge=1, le=300)
    extraction_lease_s: int = Field(default=600, ge=360, le=3600)
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(default="gemini-3.8-flash", pattern=r"^[a-zA-Z0-9.-]+$")
    extraction_timeout_s: float = Field(default=120, ge=1, le=300)
    project_page_chars: int = Field(default=60000, ge=5000, le=100000)
    # YouTube Data API v3 key (videos.list only); unset skips description intake (youtube_meta.py).
    youtube_api_key: SecretStr | None = None
    sourcing_enabled: bool = True
    sourcing_max_parts: int = Field(default=30, ge=1, le=30)
    sourcing_parallelism: int = Field(default=3, ge=1, le=4)
    sourcing_candidates_per_part: int = Field(default=5, ge=1, le=8)
    sourcing_lease_s: int = Field(default=1800, ge=600, le=7200)
    # Direct seller-catalogue search (sourcing/seller_search.py), run before paid discovery.
    seller_search_enabled: bool = True
    seller_search_fetch_budget: int = Field(default=8, ge=1, le=12)
    seller_search_per_seller: int = Field(default=5, ge=1, le=10)
    seller_search_cache_s: int = Field(default=21600, ge=0, le=86400)
    seller_page_cache_s: int = Field(default=900, ge=0, le=3600)
    seller_blocked_cooldown_s: int = Field(default=1800, ge=60, le=86400)
    research_enabled: bool = True
    seller_trust_enabled: bool = True
    research_followup_enabled: bool = True
    research_pages_per_part: int = Field(default=3, ge=1, le=5)
    research_page_chars: int = Field(default=12000, ge=2000, le=20000)
    # Recommendation basket: estimated ₹ cost of one more seller (an extra shipping fee plus
    # hassle); orders split across sellers only when that saves more than this.
    recommend_seller_penalty_inr: int = Field(default=60, ge=0, le=1000)
    # Total document text per research call across all pages (an input-token cap).
    research_total_chars: int = Field(default=24000, ge=4000, le=100000)
    # Cost controls (docs/contracts/cost-controls.md). Per-site overrides are JSON objects,
    # e.g. BS_GEMINI_SITE_MODELS='{"chat_scope": "gemini-3.1-flash-lite"}'. Setting
    # BS_GEMINI_SITE_THINKING replaces the whole default map.
    gemini_site_models: dict[str, str] = Field(default_factory=dict)
    gemini_site_thinking: dict[str, ThinkingLevel] = Field(
        default_factory=lambda: dict(DEFAULT_SITE_THINKING)
    )
    job_gemini_budget_usd: float = Field(default=0.25, ge=0, le=10)
    cache_enabled: bool = True
    # Spec judge (sourcing/judge.py): one call per BOM line with candidates, Flash-Lite class.
    judge_enabled: bool = True
    judge_model: str = Field(default="gemini-3.1-flash-lite", pattern=r"^[a-zA-Z0-9.-]+$")
    judge_thinking_level: Literal["low", "medium", "high"] | None = "low"
    judge_max_candidates: int = Field(default=8, ge=1, le=8)
    judge_cache_ttl_s: int = Field(default=7 * 86400, ge=0, le=30 * 86400)
    # AI buyer (sourcing/buyer.py): decides unstated part values from the circuit, and picks
    # what to buy (exact, substitute or kit) when no listing was accepted, with up to
    # `buyer_search_rounds` extra store searches. Site `buyer`, the main model.
    buyer_enabled: bool = True
    buyer_search_rounds: int = Field(default=2, ge=0, le=3)
    # Batched spec writer (sourcing/spec_writer.py): one call per job for lines without an
    # AI buying spec (jobs extracted before specs existed). Site `spec`, low thinking.
    spec_writer_enabled: bool = True
    # Spec fill (spec_fill.py): one call per extracted job decides required spec fields
    # (pinout, logic voltage, ...) from project context instead of asking. Site `spec_fill`.
    spec_fill_enabled: bool = True
    # Reconcile (reconcile.py): one call per extracted job reasons about the whole build and
    # merges lines that are the same part or drops ones that are not a purchase. Site `reconcile`.
    reconcile_enabled: bool = True
    # Work out add-to-cart links per store with one cached Gemini call (cart_engine.py).
    cart_engine_enabled: bool = True
    # Made-to-order lines (sourcing/fabrication.py): link 3D printing and PCB services found
    # by a grounded search and checked pages (site `fabrication`), cached for 30 days.
    fabrication_enabled: bool = True
    # Project overview (overview.py): after extraction, parallel calls (site `overview`) draw
    # the parts two lines at a time, one call (site `overview_wiring`) wires them, and judge
    # calls (site `overview_judge`) mark each part, pin header and wire
    # confirmed/unverified/disputed. Each part shows on the review page as soon as it is drawn.
    overview_enabled: bool = True
    # Build guide (build_guide.py): one call (site `build_guide`) writes numbered build steps
    # for a finished project when the owner opens the build page (POST /build-guide).
    build_guide_enabled: bool = True
    # Tried once when an overview call's model stays overloaded (429/5xx or timeouts) after
    # its retries; empty turns the fallback off.
    overview_fallback_model: str | None = Field(
        default="gemini-3.5-flash-lite", pattern=r"^[a-zA-Z0-9.-]+$"
    )
    # Gemini sites served by Vertex AI (gemini_api.py) when gcp_project is set: same models,
    # billed to the project, authorised by the service account (roles/aiplatform.user), on
    # a separate capacity pool from the API key. Refusals fall back to the API key.
    gemini_vertex_sites: list[str] = Field(
        default_factory=lambda: [
            "extraction",
            "overview",
            "overview_wiring",
            "overview_judge",
            "spec_fill",
            "reconcile",
            "cart_recipe",
            "build_guide",
        ]
    )
    vertex_location: str = Field(default="global", pattern=r"^[a-z0-9-]+$")
    # Opt-in Gemini extras (gemini_extras.py); each has its own per-owner daily quota.
    explain_enabled: bool = False
    explain_daily_limit: int = Field(default=10, ge=1, le=200)
    explain_max_chars: int = Field(default=900, ge=500, le=2000)
    tts_model: str = Field(default="gemini-3.8-flash-tts", pattern=r"^[a-zA-Z0-9.-]+$")
    tts_voice: str = Field(default="Kore", pattern=r"^[A-Za-z]+$")
    zoom_enabled: bool = False
    zoom_daily_limit: int = Field(default=10, ge=1, le=200)
    zoom_clip_s: int = Field(default=15, ge=10, le=20)
    scan_enabled: bool = False
    scan_daily_limit: int = Field(default=5, ge=1, le=100)
    scan_max_bytes: int = Field(default=4_000_000, ge=100_000, le=5_000_000)
    extras_global_daily_limit: int = Field(default=200, ge=1)
    # Nearby markets (markets.py): Gemini grounding with Google Maps, one lookup per
    # rounded location and category set, cached; India availability verified 2026-10-07.
    markets_enabled: bool = True
    markets_daily_limit: int = Field(default=5, ge=1, le=100)
    markets_global_daily_limit: int = Field(default=50, ge=1)
    markets_cache_ttl_s: int = Field(default=7 * 86400, ge=0, le=30 * 86400)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    # Largest accepted request body; the parts-bin scan route alone allows 8 MiB for its
    # base64 photo (main.py). Larger bodies get 413 BODY_TOO_LARGE before parsing.
    max_body_bytes: int = Field(default=1_048_576, ge=65_536, le=8_388_608)

    @model_validator(mode="after")
    def require_project(self):
        if self.auth_enabled and (
            not self.gcp_project
            or not self.guest_session_secret
            or len(self.guest_session_secret.get_secret_value()) < 32
        ):
            raise ValueError("Authentication requires a project and a 32-character guest secret")
        if self.auth_enabled and "*" in self.cors_origins:
            # Credentialed CORS with a wildcard would let any site use a visitor's session.
            raise ValueError("Authentication requires explicit CORS origins, not '*'")
        if self.trusted_proxy_ip_header and not self.integration_key:
            raise ValueError("Trusted proxy IP requires integration authentication")
        if self.dispatch_backend == "cloud_tasks" and (
            self.storage_backend != "firestore"
            or not self.tasks_url
            or not self.tasks_service_account
            or not self.gcp_project
        ):
            raise ValueError(
                "Cloud Tasks requires Firestore, project, target URL and service account"
            )
        if self.compile_backend == "cloud_run_job" and (
            not self.gcp_project
            or not self.compile_service_account
            or not (self.compile_audience or self.tasks_url)
        ):
            raise ValueError(
                "Compile jobs require a project, a runner service account and an audience URL"
            )
        if self.storage_backend == "firestore" and not self.gcp_project:
            raise ValueError("BS_GCP_PROJECT is required for Firestore storage")
        if any(not re.fullmatch(r"[a-zA-Z0-9.-]+", m) for m in self.gemini_site_models.values()):
            raise ValueError("Invalid per-site Gemini model name")
        return self


def site_model(settings: Settings, site: str) -> str:
    """The model for one call site (BS_GEMINI_SITE_MODELS, else BS_GEMINI_MODEL)."""
    return settings.gemini_site_models.get(site) or settings.gemini_model


def site_generation(settings: Settings, site: str) -> dict:
    """generationConfig additions for one call site; empty means the model defaults."""
    level = settings.gemini_site_thinking.get(site)
    return {"thinkingConfig": {"thinkingLevel": level}} if level else {}
