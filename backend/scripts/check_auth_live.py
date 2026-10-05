"""Direct backend auth smoke check; one guest session, no projects or model calls."""

import json
from pathlib import Path

import httpx


def main():
    access = json.loads(
        (Path(__file__).resolve().parents[1] / ".data/integration-access.json").read_text()
    )
    origin = "https://bharat-sourcer-web-diahnrbuna-el.a.run.app"
    headers = {
        "X-Integration-Key": access["integration_key"],
        "X-Requested-With": "BharatSourcer",
        "Origin": origin,
    }
    with httpx.Client(base_url=access["base_url"], headers=headers, timeout=60) as client:
        assert client.get("/v1/session").status_code == 401
        preflight = client.options(
            "/v1/session",
            headers={
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization,X-Integration-Key",
            },
        )
        assert preflight.headers.get("access-control-allow-origin") == origin
        assert client.post("/v1/jobs", json={"url": "https://example.com"}).status_code == 401
        guest = client.post("/v1/session/guest")
        guest.raise_for_status()
        assert guest.json()["kind"] == "guest"
        cookie = guest.headers["set-cookie"].lower()
        assert all(value in cookie for value in ("secure", "httponly", "samesite=lax"))
        assert client.get("/v1/session").json()["kind"] == "guest"
        assert client.get("/v1/projects").json()["projects"] == []
        usage = client.get("/v1/session/usage")
        usage.raise_for_status()
        assert usage.json()["daily_actions"]["used"] == 0
        assert (
            client.get("/v1/session", headers={"Authorization": "Bearer invalid"}).status_code
            == 401
        )
        assert client.post("/v1/session/logout").status_code == 204
        assert client.get("/v1/session").status_code == 401
    print(
        "PASS: auth required, production CORS, secure guest cookie, saved-project list, "
        "usage, invalid bearer rejection and logout. No paid work started."
    )


if __name__ == "__main__":
    main()
