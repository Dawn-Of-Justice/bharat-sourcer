"""Read-only live release check. No jobs, model calls, seller search or mutations."""

import json
import tomllib
from pathlib import Path

import httpx


def main():
    root = Path(__file__).resolve().parents[1]
    access = json.loads((root / ".data/integration-access.json").read_text(encoding="utf-8"))
    expected = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"][
        "version"
    ]
    with httpx.Client(base_url=access["base_url"], timeout=60) as client:
        health = client.get("/health")
        health.raise_for_status()
        response = client.get("/openapi.json")
        response.raise_for_status()
        schema = response.json()
        assert schema["info"]["version"] == expected
        models = schema["components"]["schemas"]
        assert "research" in models["ReportLine"]["properties"]
        assert "requirements" in models["BomItem"]["properties"]
        assert "research_assessment" in models["VerifiedOffer"]["properties"]
        assert "accept_research_assessment" in models["SelectOffer"]["properties"]
        assert client.post("/v1/jobs", json={"url": "https://example.com"}).status_code == 401
    print(json.dumps({"health": health.json(), "version": expected, "research_contract": "pass"}))


if __name__ == "__main__":
    main()
