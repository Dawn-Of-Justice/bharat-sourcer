"""Authorize bharatsourcer.web.app for Google sign-in and allow it in the backend's CORS origins."""

import json
from pathlib import Path

import httpx
from deploy_integration import PROJECT, REGION, SERVICE, command

HOSTS = ["bharatsourcer.web.app", "bharatsourcer.firebaseapp.com"]


def main():
    token = command("auth", "print-access-token").stdout.strip()
    config_url = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config"
    with httpx.Client(
        headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": PROJECT}, timeout=30
    ) as client:
        response = client.get(config_url)
        response.raise_for_status()
        domains = response.json().get("authorizedDomains", [])
        missing = [host for host in HOSTS if host not in domains]
        if missing:
            client.patch(
                config_url,
                params={"updateMask": "authorizedDomains"},
                json={"authorizedDomains": [*domains, *missing]},
            ).raise_for_status()
    print("Firebase Auth domains authorized:", ", ".join(HOSTS), flush=True)

    service = json.loads(
        command(
            "run", "services", "describe", SERVICE, f"--region={REGION}", "--format=json"
        ).stdout
    )
    entries = service["spec"]["template"]["spec"]["containers"][0].get("env", [])
    values = {e["name"]: e.get("value") for e in entries}
    origins = json.loads(values.get("BS_CORS_ORIGINS") or "[]")
    added = [f"https://{host}" for host in HOSTS if f"https://{host}" not in origins]
    if added:
        flags = Path(__file__).resolve().parents[1] / ".data/domain-cors-flags.json"
        flags.parent.mkdir(exist_ok=True)
        flags.write_text(
            json.dumps({"--update-env-vars": {"BS_CORS_ORIGINS": json.dumps(origins + added)}})
        )
        command("run", "services", "update", SERVICE, f"--region={REGION}", f"--flags-file={flags}")
    print("Backend CORS origins:", json.dumps(origins + added), flush=True)


if __name__ == "__main__":
    main()
