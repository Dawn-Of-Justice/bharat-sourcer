"""Register the existing GCP project and a Firebase web app; do not enable backend auth."""

import json
import time
from pathlib import Path

import httpx
from deploy_integration import PROJECT, command


def main():
    token = command("auth", "print-access-token").stdout.strip()
    base = "https://firebase.googleapis.com/v1beta1/"
    with httpx.Client(
        headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": PROJECT},
        timeout=60,
    ) as client:

        def request(method, path, **kwargs):
            response = client.request(method, base + path, **kwargs)
            if not response.is_success:
                raise RuntimeError(
                    f"Firebase request failed: {response.status_code} {response.text}"
                )
            return response.json()

        def wait(operation):
            for _ in range(60):
                if operation.get("done"):
                    if "error" in operation:
                        raise RuntimeError(str(operation["error"]))
                    return operation.get("response", {})
                time.sleep(2)
                operation = request("GET", operation["name"])
            raise RuntimeError("Firebase operation still pending; check console before retrying")

        path = f"projects/{PROJECT}"
        response = client.get(base + path)
        if response.status_code == 404:
            wait(request("POST", path + ":addFirebase", json={}))
            print("Registered existing GCP project with Firebase.", flush=True)
        else:
            response.raise_for_status()
        apps = request("GET", path + "/webApps").get("apps", [])
        matches = [app for app in apps if app.get("displayName") == "Bharat Sourcer Web"]
        app = (
            matches[0]
            if matches
            else wait(
                request("POST", path + "/webApps", json={"displayName": "Bharat Sourcer Web"})
            )
        )
        config = request("GET", app["name"] + "/config")
        target = Path(__file__).resolve().parents[1] / ".data/firebase-web-config.json"
        target.parent.mkdir(exist_ok=True)
        target.write_text(json.dumps(config, indent=2), encoding="utf-8")
        print(f"Firebase web app ready. SDK configuration saved locally: {target}")
        print("Google provider still requires verification. Backend auth setting unchanged.")


if __name__ == "__main__":
    main()
