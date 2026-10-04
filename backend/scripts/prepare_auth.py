"""Prepare backend auth infrastructure without enabling authentication or rotating cookies."""

import json
import secrets

from deploy_integration import ACCOUNT, REGION, SERVICE, command


def main():
    service = json.loads(
        command(
            "run", "services", "describe", SERVICE, f"--region={REGION}", "--format=json"
        ).stdout
    )
    env = service["spec"]["template"]["spec"]["containers"][0].get("env", [])
    values = {entry["name"]: entry.get("value") for entry in env}
    collection = values.get("BS_FIRESTORE_COLLECTION") or "backend_jobs"
    database = values.get("BS_FIRESTORE_DATABASE") or "(default)"
    name = "bharat-sourcer-guest-session"
    # An existing secret must never be rotated implicitly: guests rely on its stability.
    found = command("secrets", "describe", name, optional=True)
    if found.returncode:
        if "NOT_FOUND" not in found.stderr:
            raise RuntimeError(found.stderr)
        command("secrets", "create", name, "--replication-policy=automatic")
        command("secrets", "versions", "add", name, "--data-file=-", data=secrets.token_urlsafe(48))
    versions = json.loads(
        command(
            "secrets", "versions", "list", name, "--filter=state:ENABLED", "--format=json"
        ).stdout
    )
    if not versions:
        raise RuntimeError("Guest secret has no enabled version; restore it before continuing")
    version = max(int(item["name"].split("/")[-1]) for item in versions)
    runtime_account = service["spec"]["template"]["spec"].get("serviceAccountName", ACCOUNT)
    command(
        "secrets",
        "add-iam-policy-binding",
        name,
        f"--member=serviceAccount:{runtime_account}",
        "--role=roles/secretmanager.secretAccessor",
    )
    command(
        "firestore",
        "fields",
        "ttls",
        "update",
        "expires_at",
        f"--collection-group={collection}_usage",
        f"--database={database}",
        "--enable-ttl",
        "--async",
    )
    # Preserve an existing binding, including an intentionally pinned older version.
    if not any(entry["name"] == "BS_GUEST_SESSION_SECRET" for entry in env):
        command(
            "run",
            "services",
            "update",
            SERVICE,
            f"--region={REGION}",
            f"--update-secrets=BS_GUEST_SESSION_SECRET={name}:{version}",
        )
    print("Guest secret prepared and quota TTL requested. Authentication setting unchanged.")


if __name__ == "__main__":
    main()
