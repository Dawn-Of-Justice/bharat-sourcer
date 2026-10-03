from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="BS_", env_file=".env", extra="ignore")

    demo_mode: bool = True
    integration_key: SecretStr | None = None
    dispatch_backend: Literal["local", "cloud_tasks"] = "local"
    tasks_location: str = "asia-south1"
    tasks_queue: str = "bharat-sourcer"
    tasks_url: str | None = None
    tasks_service_account: str | None = None
    storage_backend: Literal["memory", "firestore"] = "memory"
    gcp_project: str | None = None
    firestore_database: str = "(default)"
    firestore_collection: str = Field(default="backend_jobs", pattern=r"^[A-Za-z][A-Za-z0-9_-]*$")
    recovery_interval_s: float = Field(default=30, ge=1, le=300)
    extraction_lease_s: int = Field(default=600, ge=360, le=3600)
    gemini_api_key: SecretStr | None = None
    gemini_model: str = Field(default="gemini-3.8-flash", pattern=r"^[a-zA-Z0-9.-]+$")
    extraction_timeout_s: float = Field(default=120, ge=1, le=300)
    sourcing_enabled: bool = True
    sourcing_max_parts: int = Field(default=10, ge=1, le=30)
    sourcing_parallelism: int = Field(default=3, ge=1, le=4)
    sourcing_candidates_per_part: int = Field(default=5, ge=1, le=8)
    sourcing_lease_s: int = Field(default=1800, ge=600, le=7200)
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @model_validator(mode="after")
    def require_project(self):
        if self.dispatch_backend == "cloud_tasks" and (
            self.storage_backend != "firestore"
            or not self.tasks_url
            or not self.tasks_service_account
            or not self.gcp_project
        ):
            raise ValueError(
                "Cloud Tasks requires Firestore, project, target URL and service account"
            )
        if self.storage_backend == "firestore" and not self.gcp_project:
            raise ValueError("BS_GCP_PROJECT is required for Firestore storage")
        return self
