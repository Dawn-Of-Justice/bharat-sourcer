"""Inspect Firebase readiness without logging credentials or OAuth client secrets."""

import json

import httpx
from deploy_integration import PROJECT, command


def main():
    token = command("auth", "print-access-token").stdout.strip()
    urls = {
        "firebase_project": f"https://firebase.googleapis.com/v1beta1/projects/{PROJECT}",
        "auth_config": f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config",
        "google_provider": f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}"
        "/defaultSupportedIdpConfigs/google.com",
    }
    result = {}
    with httpx.Client(
        headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": PROJECT}, timeout=30
    ) as client:
        for name, url in urls.items():
            response = client.get(url)
            data = response.json()
            result[name] = {"status": response.status_code}
            if response.is_success:
                for field in ("projectId", "enabled", "authorizedDomains"):
                    if field in data:
                        result[name][field] = data[field]
            else:
                error = data.get("error", {})
                result[name]["error"] = error.get("message", "Request failed")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
