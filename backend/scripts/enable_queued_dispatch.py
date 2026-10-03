"""Migrate the existing integration service to scale-to-zero durable dispatch."""

import json
import os
from pathlib import Path

from deploy_integration import ACCOUNT, PROJECT, REGION, SERVICE, command


def main():
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    worker = f"bharat-sourcer-tasks@{PROJECT}.iam.gserviceaccount.com"
    queue = "bharat-sourcer"
    url = json.loads((root / ".data/integration-access.json").read_text())["base_url"]
    print("Enabling task queue and scheduler...", flush=True)
    command("services", "enable", "cloudtasks.googleapis.com", "cloudscheduler.googleapis.com")
    if command("iam", "service-accounts", "describe", worker, optional=True).returncode:
        command("iam", "service-accounts", "create", "bharat-sourcer-tasks")
    command(
        "iam",
        "service-accounts",
        "add-iam-policy-binding",
        worker,
        f"--member=serviceAccount:{ACCOUNT}",
        "--role=roles/iam.serviceAccountUser",
    )
    if command(
        "tasks", "queues", "describe", queue, f"--location={REGION}", optional=True
    ).returncode:
        command("tasks", "queues", "create", queue, f"--location={REGION}")
    command(
        "tasks",
        "queues",
        "update",
        queue,
        f"--location={REGION}",
        "--max-concurrent-dispatches=2",
        "--max-dispatches-per-second=2",
        "--max-attempts=200",
        "--max-retry-duration=86400s",
        "--min-backoff=10s",
        "--max-backoff=60s",
    )
    command(
        "tasks",
        "queues",
        "add-iam-policy-binding",
        queue,
        f"--location={REGION}",
        f"--member=serviceAccount:{ACCOUNT}",
        "--role=roles/cloudtasks.enqueuer",
    )
    path = root / ".data/cloud-run-env.json"
    env = json.loads(path.read_text())
    env.update(
        BS_DISPATCH_BACKEND="cloud_tasks",
        BS_TASKS_LOCATION=REGION,
        BS_TASKS_QUEUE=queue,
        BS_TASKS_URL=url,
        BS_TASKS_SERVICE_ACCOUNT=worker,
    )
    path.write_text(json.dumps(env), encoding="utf-8")
    print("Deploying request-billed API with minimum zero instances...", flush=True)
    result = command(
        "run",
        "deploy",
        SERVICE,
        f"--region={REGION}",
        "--source=.",
        "--min-instances=0",
        "--min=0",
        "--max-instances=1",
        "--max=1",
        "--cpu-throttling",
        "--timeout=1800",
        f"--env-vars-file={path}",
        "--format=value(status.latestReadyRevisionName)",
    )
    print("Revision:", result.stdout.strip(), flush=True)
    name = "bharat-sourcer-reconcile"
    verb = (
        "update"
        if command(
            "scheduler", "jobs", "describe", name, f"--location={REGION}", optional=True
        ).returncode
        == 0
        else "create"
    )
    command(
        "scheduler",
        "jobs",
        verb,
        "http",
        name,
        f"--location={REGION}",
        "--schedule=*/5 * * * *",
        "--time-zone=Etc/UTC",
        "--http-method=POST",
        f"--uri={url}/internal/sweep",
        f"--oidc-service-account-email={worker}",
        f"--oidc-token-audience={url}",
        "--attempt-deadline=180s",
    )
    command("scheduler", "jobs", "run", name, f"--location={REGION}")
    print("Queue enabled; scheduled reconciliation every five minutes.", flush=True)


if __name__ == "__main__":
    main()
