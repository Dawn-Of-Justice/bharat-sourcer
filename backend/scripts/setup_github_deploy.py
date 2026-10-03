"""Provision keyless GitHub authentication for the existing integration service."""

from deploy_integration import ACCOUNT, PROJECT, REGION, SERVICE, command


def main():
    pool = "bharat-github"
    repo = "Dawn-Of-Justice/bharat-sourcer"
    deployer = f"bharat-sourcer-deploy@{PROJECT}.iam.gserviceaccount.com"
    command("services", "enable", "iamcredentials.googleapis.com", "sts.googleapis.com")
    if command("iam", "service-accounts", "describe", deployer, optional=True).returncode:
        command("iam", "service-accounts", "create", "bharat-sourcer-deploy")
    if command(
        "iam", "workload-identity-pools", "describe", pool, "--location=global", optional=True
    ).returncode:
        command("iam", "workload-identity-pools", "create", pool, "--location=global")
    condition = (
        f"assertion.repository == '{repo}' && "
        "assertion.repository_owner == 'Dawn-Of-Justice' && "
        "assertion.ref == 'refs/heads/main' && "
        f"assertion.workflow_ref == '{repo}/.github/workflows/backend.yml@refs/heads/main' && "
        "assertion.event_name in ['push', 'workflow_dispatch']"
    )
    found = command(
        "iam",
        "workload-identity-pools",
        "providers",
        "describe",
        "backend",
        f"--workload-identity-pool={pool}",
        "--location=global",
        optional=True,
    )
    verb = "update-oidc" if found.returncode == 0 else "create-oidc"
    command(
        "iam",
        "workload-identity-pools",
        "providers",
        verb,
        "backend",
        f"--workload-identity-pool={pool}",
        "--location=global",
        "--issuer-uri=https://token.actions.githubusercontent.com",
        "--attribute-mapping=google.subject=assertion.sub,attribute.repository=assertion.repository",
        f"--attribute-condition={condition}",
    )
    command(
        "iam",
        "service-accounts",
        "add-iam-policy-binding",
        deployer,
        "--role=roles/iam.workloadIdentityUser",
        "--member=principalSet://iam.googleapis.com/projects/689415686498/locations/global/"
        f"workloadIdentityPools/{pool}/attribute.repository/{repo}",
    )
    command(
        "run",
        "services",
        "add-iam-policy-binding",
        SERVICE,
        f"--region={REGION}",
        f"--member=serviceAccount:{deployer}",
        "--role=roles/run.developer",
    )
    command(
        "artifacts",
        "repositories",
        "add-iam-policy-binding",
        "cloud-run-source-deploy",
        f"--location={REGION}",
        f"--member=serviceAccount:{deployer}",
        "--role=roles/artifactregistry.writer",
    )
    command(
        "iam",
        "service-accounts",
        "add-iam-policy-binding",
        ACCOUNT,
        f"--member=serviceAccount:{deployer}",
        "--role=roles/iam.serviceAccountUser",
    )
    print("GitHub OIDC configured for backend.yml on main; no service-account key created.")


if __name__ == "__main__":
    main()
