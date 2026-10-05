"""Prepare production origin; opt-in auth activation with proxy smoke checks and rollback."""

import argparse
import json
import re
from pathlib import Path

import httpx
from deploy_integration import PROJECT, REGION, SERVICE, command

ORIGIN = "https://bharat-sourcer-web-diahnrbuna-el.a.run.app"


def smoke():
    headers = {"Origin": ORIGIN, "X-Requested-With": "BharatSourcer"}
    with httpx.Client(base_url=ORIGIN, headers=headers, timeout=60) as client:
        response = client.post("/api/v1/session/guest")
        response.raise_for_status()
        assert response.json()["kind"] == "guest"
        assert "bs_guest" in client.cookies, "Proxy did not forward guest cookie"
        assert client.get("/api/v1/session").json()["kind"] == "guest"
        usage = client.get("/api/v1/session/usage")
        usage.raise_for_status()
        assert "daily_actions" in usage.json()
        projects = client.get("/api/v1/projects")
        projects.raise_for_status()
        assert projects.json()["projects"] == []
        invalid = client.get("/api/v1/session", headers={"Authorization": "Bearer invalid-smoke"})
        assert invalid.status_code == 401, "Proxy did not forward Authorization"
        assert client.post("/api/v1/session/logout").status_code == 204
        assert client.get("/api/v1/session").status_code == 401
    print("Proxy guest cookie, session, usage, projects, bearer rejection and logout passed.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--activate", action="store_true")
    args = parser.parse_args()
    token = command("auth", "print-access-token").stdout.strip()
    config_url = f"https://identitytoolkit.googleapis.com/admin/v2/projects/{PROJECT}/config"
    with httpx.Client(
        headers={"Authorization": f"Bearer {token}", "X-Goog-User-Project": PROJECT}, timeout=30
    ) as client:
        response = client.get(config_url)
        response.raise_for_status()
        domains = response.json().get("authorizedDomains", [])
        domain = httpx.URL(ORIGIN).host
        if domain not in domains:
            response = client.patch(
                config_url,
                params={"updateMask": "authorizedDomains"},
                json={"authorizedDomains": [*domains, domain]},
            )
            response.raise_for_status()
        assert domain in client.get(config_url).json()["authorizedDomains"]
    print("Production Firebase domain authorized.", flush=True)
    service = json.loads(
        command(
            "run", "services", "describe", SERVICE, f"--region={REGION}", "--format=json"
        ).stdout
    )
    entries = service["spec"]["template"]["spec"]["containers"][0].get("env", [])
    values = {e["name"]: e.get("value") for e in entries}
    origins = json.loads(values.get("BS_CORS_ORIGINS") or "[]")
    if ORIGIN not in origins:
        origins.append(ORIGIN)
    flags = Path(__file__).resolve().parents[1] / ".data/auth-cors-flags.json"
    flags.write_text(json.dumps({"--update-env-vars": {"BS_CORS_ORIGINS": json.dumps(origins)}}))
    command("run", "services", "update", SERVICE, f"--region={REGION}", f"--flags-file={flags}")
    print("Backend production CORS configured.", flush=True)
    with httpx.Client(timeout=60) as client:
        page = client.get(ORIGIN)
        page.raise_for_status()
        scripts = re.findall(r'<script[^>]+src="([^"]+)"', page.text)
        bundles = "\n".join(client.get(str(httpx.URL(ORIGIN).join(src))).text for src in scripts)
        indicators = {
            key: key in bundles
            for key in ("firebaseapp.com", "/session/guest", "/projects", "BharatSourcer")
        }
        print("Deployed frontend indicators:", json.dumps(indicators), flush=True)
    if not args.activate:
        print("Preparation complete. Authentication setting unchanged.")
        return
    if not all(indicators.values()):
        raise RuntimeError("Frontend auth bundle not ready; auth setting unchanged")
    assert any(e["name"] == "BS_GUEST_SESSION_SECRET" for e in entries)
    previous = values.get("BS_AUTH_ENABLED") or "false"
    snapshot = Path(__file__).resolve().parents[1] / ".data/auth-rollout.json"
    snapshot.write_text(
        json.dumps(
            {
                "previous_auth": previous,
                "previous_revision": service["status"]["latestReadyRevisionName"],
            }
        )
    )
    command(
        "run",
        "services",
        "update",
        SERVICE,
        f"--region={REGION}",
        "--update-env-vars=BS_AUTH_ENABLED=true",
    )
    try:
        smoke()
    except Exception:
        command(
            "run",
            "services",
            "update",
            SERVICE,
            f"--region={REGION}",
            f"--update-env-vars=BS_AUTH_ENABLED={previous}",
        )
        raise RuntimeError("Proxy smoke failed; restored previous authentication setting") from None
    print("Authentication enabled. No extraction or model calls were started.")


if __name__ == "__main__":
    main()
