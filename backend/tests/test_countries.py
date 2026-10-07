"""Country registry, account settings and the removed PIN field. Identities are synthetic."""

from dataclasses import replace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.countries import COUNTRIES, DEFAULT_COUNTRY, INDIA, country
from bharat_sourcer.identity import Principal
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import CreateJob, Job
from bharat_sourcer.sourcing.service import source_rank
from bharat_sourcer.storage import MemoryJobStore, StoredJob

# A second country, only for these tests, to prove the plumbing is not India-only.
NEPAL = replace(INDIA, code="NP", name="Nepal", currency="NPR", locale="ne-NP", cities=())


class Verifier:
    def verify(self, token):
        if token not in {"alice", "bob"}:
            raise ValueError("Invalid mock signature")
        return Principal("user:" + token)


def setup():
    settings = Settings(
        _env_file=None,
        auth_enabled=True,
        gcp_project="fixture-project",
        guest_session_secret="test-secret-only-not-production-123456",
    )
    client = TestClient(
        create_app(settings, identity_verifier=Verifier()), base_url="https://testserver"
    )
    client.headers["X-Requested-With"] = "BharatSourcer"
    return client


def auth(user):
    return {"Authorization": "Bearer " + user}


def test_registry_defaults_to_india():
    assert DEFAULT_COUNTRY == "IN" and country(None) is INDIA and country("ZZ") is INDIA
    assert INDIA.currency == "INR" and INDIA.mains_vac == 230
    assert INDIA.city("bengaluru").name == "Bengaluru" and INDIA.city("Atlantis") is None
    assert INDIA.contains(12.97, 77.59) and not INDIA.contains(51.5, -0.12)
    assert source_rank({"title": "robu.in"}) == 0 and source_rank({"title": "shop.in"}) == 0
    assert source_rank({"title": "example.com"}) == 1


def test_legacy_pin_is_ignored_on_requests_and_saved_snapshots():
    request = CreateJob.model_validate({"url": "https://example.com", "pin": "560001"})
    assert request.country == "IN" and "pin" not in request.model_dump()
    old = {"job_id": "j1", "input": {"url": "https://example.com/", "pin": "560001"}}
    assert Job.model_validate(old).input.country == "IN"
    store = MemoryJobStore()
    store.create(StoredJob(job=Job.model_validate(old), token_hash="x"))
    assert store.get("j1").job.input.country == "IN"


@pytest.mark.parametrize("code", ["US", "in", "IND", ""])
def test_unsupported_country_is_rejected(code):
    with pytest.raises(ValueError):
        CreateJob(url="https://example.com", country=code)


def test_countries_route_lists_supported_countries_and_market_cities():
    body = setup().get("/v1/countries").json()
    assert body["default"] == "IN"
    [india] = body["countries"]
    assert (india["code"], india["name"], india["currency"]) == ("IN", "India", "INR")
    assert "Bengaluru" in india["market_cities"]


def test_account_settings_save_and_default_new_projects():
    client = setup()
    assert client.get("/v1/account/settings", headers=auth("alice")).json() == {
        "country": "IN",
        "updated_at": None,
        "saved": False,
    }
    with patch.dict(COUNTRIES, {"NP": NEPAL}):
        saved = client.post("/v1/account/settings", json={"country": "NP"}, headers=auth("alice"))
        assert saved.status_code == 200 and saved.json()["saved"] is True
        assert client.get("/v1/account/settings", headers=auth("alice")).json()["country"] == "NP"
        # Other accounts are unaffected.
        assert client.get("/v1/account/settings", headers=auth("bob")).json()["country"] == "IN"

        def created_country(user, body):
            job = client.post("/v1/jobs", json=body, headers=auth(user)).json()
            return client.get(f"/v1/jobs/{job['job_id']}", headers=auth(user)).json()["input"]

        url = {"url": "https://example.com"}
        assert created_country("alice", url)["country"] == "NP"
        # An explicit country on the request wins over the saved one.
        assert created_country("alice", url | {"country": "IN"})["country"] == "IN"
        assert created_country("bob", url)["country"] == "IN"
    # A saved country that is no longer supported falls back to the default.
    assert client.get("/v1/account/settings", headers=auth("alice")).json()["saved"] is False


def test_account_settings_validation_and_guests():
    client = setup()
    bad = client.post("/v1/account/settings", json={"country": "US"}, headers=auth("alice"))
    assert bad.status_code == 422
    assert client.get("/v1/account/settings").status_code == 401
    assert client.post("/v1/session/guest").status_code == 200
    assert client.get("/v1/account/settings").json()["saved"] is False
    response = client.post("/v1/account/settings", json={"country": "IN"})
    assert response.status_code == 401 and response.json()["error"]["code"] == "ACCOUNT_REQUIRED"
    no_header = client.post(
        "/v1/account/settings",
        json={"country": "IN"},
        headers=auth("alice") | {"X-Requested-With": ""},
    )
    assert no_header.status_code == 403
