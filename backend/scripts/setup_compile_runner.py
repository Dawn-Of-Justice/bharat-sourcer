"""Provision the code-adapt compile runner (tier 3). Idempotent; needs owner gcloud access.

Creates, or brings up to date:

1. VPC `bharat-sourcer-compile` with one subnet (Private Google Access on, no Cloud NAT),
   so the jobs reach Google endpoints (this API) and nothing else on the internet;
2. service account `bharat-sourcer-compile@` with no roles and no secrets;
3. Artifact Registry repository `bharat-sourcer-compile` (keeps the 2 newest images);
4. one runner image per core family, built locally with Docker and pushed (`--skip-build`
   reuses the images already pushed for the current pins);
5. Cloud Run jobs `bharat-sourcer-compile-<family>` (2 vCPU / 4 GiB, 600 s, no retries,
   Direct VPC egress for all traffic);
6. IAM: the API may run those jobs with overrides and act as the runner identity; the
   GitHub deploy identity may update the jobs and push images;
7. API settings: BS_COMPILE_BACKEND=cloud_run_job, runner account and token audience.

Run from backend/: python scripts/setup_compile_runner.py [--skip-build] [--families avr]
"""

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from deploy_integration import ACCOUNT, PROJECT, REGION, SERVICE, command

ROOT = Path(__file__).resolve().parents[1]
COMPILE = ROOT / "compile"
NETWORK = "bharat-sourcer-compile"
SUBNET = f"{NETWORK}-{REGION}"
RANGE = "10.80.0.0/26"
RUNNER = f"bharat-sourcer-compile@{PROJECT}.iam.gserviceaccount.com"
DEPLOYER = f"bharat-sourcer-deploy@{PROJECT}.iam.gserviceaccount.com"
REPOSITORY = "bharat-sourcer-compile"
REGISTRY = f"{REGION}-docker.pkg.dev/{PROJECT}/{REPOSITORY}"
JOB_PREFIX = "bharat-sourcer-compile"
CLEANUP = [
    {"name": "keep-newest", "action": {"type": "Keep"}, "mostRecentVersions": {"keepCount": 2}},
    {"name": "delete-older", "action": {"type": "Delete"}, "condition": {"olderThan": "1d"}},
]


def missing(*args) -> bool:
    return command(*args, optional=True).returncode != 0


def pins_tag() -> str:
    """Image tag from the runner sources, so unchanged pins reuse the pushed image."""
    digest = hashlib.sha256()
    for name in ("Dockerfile", "pins.json", "arduino-cli.yaml", "install.py", "runner.py"):
        digest.update((COMPILE / name).read_bytes())
    return "pins-" + digest.hexdigest()[:12]


def network() -> None:
    if missing("compute", "networks", "describe", NETWORK):
        print("Creating VPC network...", flush=True)
        command("compute", "networks", "create", NETWORK, "--subnet-mode=custom")
    if missing("compute", "networks", "subnets", "describe", SUBNET, f"--region={REGION}"):
        command(
            "compute",
            "networks",
            "subnets",
            "create",
            SUBNET,
            f"--network={NETWORK}",
            f"--region={REGION}",
            f"--range={RANGE}",
            "--enable-private-ip-google-access",
        )
    else:
        command(
            "compute",
            "networks",
            "subnets",
            "update",
            SUBNET,
            f"--region={REGION}",
            "--enable-private-ip-google-access",
        )
    routers = command(
        "compute", "routers", "list", f"--filter=network~/{NETWORK}$", "--format=value(name)"
    )
    if routers.stdout.strip():
        raise RuntimeError(f"{NETWORK} has a Cloud Router; the runner network must have no NAT")


def identity_and_registry() -> None:
    if missing("iam", "service-accounts", "describe", RUNNER):
        command(
            "iam",
            "service-accounts",
            "create",
            RUNNER.split("@", maxsplit=1)[0],
            "--display-name=Bharat Sourcer compile runner (no roles)",
        )
    if missing("artifacts", "repositories", "describe", REPOSITORY, f"--location={REGION}"):
        command(
            "artifacts",
            "repositories",
            "create",
            REPOSITORY,
            "--repository-format=docker",
            f"--location={REGION}",
            "--description=Compile runner images (code-adapt tier 3)",
        )
    policy = ROOT / ".data" / "compile-cleanup-policy.json"
    policy.parent.mkdir(exist_ok=True)
    policy.write_text(json.dumps(CLEANUP), encoding="utf-8")
    command(
        "artifacts",
        "repositories",
        "set-cleanup-policies",
        REPOSITORY,
        f"--location={REGION}",
        f"--policy={policy}",
        "--no-dry-run",
    )


def build(families: list[str], tag: str) -> None:
    command("auth", "configure-docker", f"{REGION}-docker.pkg.dev")
    for family in families:
        image = f"{REGISTRY}/runner-{family}:{tag}"
        print(f"Building and pushing {image} ...", flush=True)
        subprocess.run(
            ["docker", "build", "--build-arg", f"FAMILY={family}", "-t", image, str(COMPILE)],
            check=True,
        )
        subprocess.run(["docker", "push", image], check=True)


def jobs(families: list[str], tag: str, api_url: str) -> None:
    for family in families:
        name = f"{JOB_PREFIX}-{family}"
        print(f"Deploying job {name} ...", flush=True)
        command(
            "run",
            "jobs",
            "deploy",
            name,
            f"--region={REGION}",
            f"--image={REGISTRY}/runner-{family}:{tag}",
            f"--service-account={RUNNER}",
            f"--network={NETWORK}",
            f"--subnet={SUBNET}",
            "--vpc-egress=all-traffic",
            "--cpu=2",
            "--memory=4Gi",
            "--task-timeout=600s",
            "--max-retries=0",
            "--tasks=1",
            "--parallelism=1",
            f"--set-env-vars=BS_COMPILE_API_URL={api_url}",
        )
        for member, role in (
            (f"serviceAccount:{ACCOUNT}", "roles/run.jobsExecutorWithOverrides"),
            (f"serviceAccount:{DEPLOYER}", "roles/run.developer"),
        ):
            command(
                "run",
                "jobs",
                "add-iam-policy-binding",
                name,
                f"--region={REGION}",
                f"--member={member}",
                f"--role={role}",
            )


def grants() -> None:
    # The runner identity has no roles, so acting as it grants nothing beyond running jobs.
    for member in (ACCOUNT, DEPLOYER):
        command(
            "iam",
            "service-accounts",
            "add-iam-policy-binding",
            RUNNER,
            f"--member=serviceAccount:{member}",
            "--role=roles/iam.serviceAccountUser",
        )
    command(
        "artifacts",
        "repositories",
        "add-iam-policy-binding",
        REPOSITORY,
        f"--location={REGION}",
        f"--member=serviceAccount:{DEPLOYER}",
        "--role=roles/artifactregistry.writer",
    )


def main() -> None:
    families = list(json.loads((COMPILE / "pins.json").read_text("utf-8"))["families"])
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--families", nargs="+", choices=families, default=families)
    args = parser.parse_args()
    api_url = command(
        "run", "services", "describe", SERVICE, f"--region={REGION}", "--format=value(status.url)"
    ).stdout.strip()
    if not api_url.startswith("https://"):
        raise RuntimeError("API service URL not found")
    tag = pins_tag()
    network()
    identity_and_registry()
    grants()
    if not args.skip_build:
        build(args.families, tag)
    jobs(args.families, tag, api_url)
    print("Enabling compile checks on the API...", flush=True)
    command(
        "run",
        "services",
        "update",
        SERVICE,
        f"--region={REGION}",
        "--update-env-vars=BS_COMPILE_BACKEND=cloud_run_job,"
        f"BS_COMPILE_SERVICE_ACCOUNT={RUNNER},BS_COMPILE_AUDIENCE={api_url}",
    )
    print(f"Compile runner ready: {', '.join(args.families)} (images tagged {tag})")


if __name__ == "__main__":
    main()
