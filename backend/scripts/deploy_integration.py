"""Deploy the team integration API to Cloud Run. Requires authorized gcloud access."""

import json
import os
import secrets
import subprocess
from pathlib import Path

from bharat_sourcer.config import Settings

PROJECT = "hackathon-510415"
REGION = "asia-south1"
SERVICE = "bharat-sourcer-integration"
ACCOUNT = f"bharat-sourcer-api@{PROJECT}.iam.gserviceaccount.com"
GCLOUD = str(Path(os.environ["LOCALAPPDATA"]) / "Google/Cloud SDK/google-cloud-sdk/bin/gcloud.cmd")


def command(*args, data=None, optional=False):
    result = subprocess.run(
        [GCLOUD, *args, f"--project={PROJECT}", "--quiet"],
        input=data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode and not optional:
        # Commands never contain secret values; secret payloads go only through stdin.
        raise RuntimeError(result.stderr)
    return result


def secret(name, value):
    found = command("secrets", "describe", name, optional=True)
    if found.returncode:
        command("secrets", "create", name, "--replication-policy=automatic")
    result = command(
        "secrets", "versions", "add", name, "--data-file=-", "--format=value(name)", data=value
    )
    version = result.stdout.strip().split("/")[-1]
    command(
        "secrets",
        "add-iam-policy-binding",
        name,
        f"--member=serviceAccount:{ACCOUNT}",
        "--role=roles/secretmanager.secretAccessor",
    )
    return version


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    settings = Settings()
    if not settings.gemini_api_key:
        raise RuntimeError("Configure local Gemini key first")
    data_dir = root / ".data"
    data_dir.mkdir(exist_ok=True)
    credentials = data_dir / "integration-access.json"
    if credentials.exists():
        integration_key = json.loads(credentials.read_text())["integration_key"]
    else:
        integration_key = secrets.token_urlsafe(32)
        credentials.write_text(json.dumps({"integration_key": integration_key}), encoding="utf-8")
    print("Preparing runtime service account and secrets...", flush=True)
    if command("iam", "service-accounts", "describe", ACCOUNT, optional=True).returncode:
        command(
            "iam",
            "service-accounts",
            "create",
            "bharat-sourcer-api",
            "--display-name=Bharat Sourcer integration backend",
        )
    command(
        "projects",
        "add-iam-policy-binding",
        PROJECT,
        f"--member=serviceAccount:{ACCOUNT}",
        "--role=roles/datastore.user",
    )
    gemini_version = secret("bharat-sourcer-gemini", settings.gemini_api_key.get_secret_value())
    access_version = secret("bharat-sourcer-integration-key", integration_key)
    env = {
        "BS_DEMO_MODE": "false",
        "BS_STORAGE_BACKEND": "firestore",
        "BS_GCP_PROJECT": PROJECT,
        "BS_FIRESTORE_DATABASE": "(default)",
        "BS_FIRESTORE_COLLECTION": "backend_integration_jobs",
        "BS_GEMINI_MODEL": settings.gemini_model,
        "BS_SOURCING_ENABLED": "true",
        "BS_CORS_ORIGINS": json.dumps(
            [
                "http://localhost:5173",
                "http://127.0.0.1:5173",
                "http://localhost:3000",
                "http://127.0.0.1:3000",
            ]
        ),
    }
    env_path = data_dir / "cloud-run-env.json"
    env_path.write_text(json.dumps(env), encoding="utf-8")
    print("Building and deploying Cloud Run (one always-running instance)...", flush=True)
    result = command(
        "run",
        "deploy",
        SERVICE,
        f"--region={REGION}",
        "--source=.",
        f"--service-account={ACCOUNT}",
        "--allow-unauthenticated",
        "--port=8080",
        "--cpu=1",
        "--memory=512Mi",
        "--min-instances=1",
        "--max-instances=1",
        "--no-cpu-throttling",
        "--concurrency=20",
        "--timeout=300",
        f"--env-vars-file={env_path}",
        f"--set-secrets=BS_GEMINI_API_KEY=bharat-sourcer-gemini:{gemini_version},"
        f"BS_INTEGRATION_KEY=bharat-sourcer-integration-key:{access_version}",
        "--format=value(status.url)",
    )
    url = result.stdout.strip()
    if not url.startswith("https://"):
        url = command(
            "run",
            "services",
            "describe",
            SERVICE,
            f"--region={REGION}",
            "--format=value(status.url)",
        ).stdout.strip()
    credentials.write_text(
        json.dumps({"base_url": url, "integration_key": integration_key}, indent=2),
        encoding="utf-8",
    )
    print(f"Deployed: {url}\nLocal private access file: {credentials}", flush=True)


if __name__ == "__main__":
    main()
