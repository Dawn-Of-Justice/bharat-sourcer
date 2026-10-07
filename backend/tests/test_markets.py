"""Nearby markets use synthetic jobs and a mocked transport; no model is ever called."""

import json
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.countries import INDIA
from bharat_sourcer.jobs import JobError
from bharat_sourcer.main import create_app
from bharat_sourcer.markets import (
    SUMMARY_LABEL,
    parse_grounding,
    part_categories,
    resolve_location,
)
from bharat_sourcer.schemas import BomItem, BuyableSpec, CostEstimate, CreateJob

# Shape recorded from a live call on 2026-10-07; content synthetic (shop names, addresses
# and IDs are invented). Do not present these as real shops.
CHUNKS = [
    {
        "maps": {
            "uri": "https://maps.google.com/maps?cid=1111111111111111111",
            "title": "Synthetic Electro Tech - Google Maps",
            "text": "**Title:** Synthetic Electro Tech\n\n**About:**\n\n"
            "* **Address:** 2nd Floor, No 1, Synthetic Road, Bengaluru 560002\n"
            "* **Rating:** 4.5",
        }
    },
    {
        "maps": {
            "uri": "https://www.google.com/maps/reviews/data=!4m5!synthetic1",
            "title": "Review of Synthetic Electro Tech",
            "text": "Good stock of resistors (synthetic review).",
        }
    },
    {
        "maps": {
            "uri": "https://maps.google.com/maps?cid=2222222222222222222",
            "title": "Fixture Components - Google Maps",
            "text": "**Title:** Fixture Components",
            "placeId": "places/ChIJsynthetic2",
        }
    },
    # Duplicate place URI and an unsafe URI are dropped.
    {"maps": {"uri": "https://maps.google.com/maps?cid=2222222222222222222", "title": "Dup"}},
    {"maps": {"uri": "javascript:alert(1)", "title": "Bad - Google Maps"}},
]
TEXT = "1. Synthetic Electro Tech (Synthetic Road)\n2. Fixture Components (Synthetic Road)"


def maps_reply(chunks=CHUNKS, text=TEXT, finish="STOP"):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": finish,
                    "content": {"role": "model", "parts": [{"text": text}]},
                    "groundingMetadata": {"groundingChunks": chunks},
                }
            ],
            "usageMetadata": {
                "promptTokenCount": 60,
                "candidatesTokenCount": 180,
                "toolUsePromptTokenCount": 500,
                "totalTokenCount": 783,
            },
        },
    )


def items():
    return [
        BomItem(line_id="L01", raw_name="330 ohm resistor", qty=4),
        BomItem(
            line_id="L02",
            raw_name="Red indicator",
            buyable_spec=BuyableSpec(category="led"),
        ),
        BomItem(line_id="L03", raw_name="BME280 sensor module"),
        BomItem(line_id="L04", raw_name="Secret project gizmo", user_has_it=True),
    ]


def setup(demo=False, with_items=True, **overrides):
    defaults = {"demo_mode": True, "gemini_api_key": "test-secret"}
    settings = Settings(_env_file=None, **(defaults | overrides))
    app = create_app(settings)
    service = app.state.job_service
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))

    def seed(record):
        record.job.demo = demo
        record.job.status = "awaiting_confirmation"
        record.job.items = items() if with_items else []

    service.store.mutate(job.job_id, seed)
    calls = []
    replies = []

    def handle(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload))
        assert request.headers["x-goog-api-key"] == "test-secret"
        if not replies:
            raise AssertionError("Unexpected Gemini call " + request.url.path)
        return replies.pop(0)

    app.state.markets.transport = httpx.MockTransport(handle)
    client = TestClient(app)
    client.headers["X-Job-Token"] = token
    return client, job.job_id, calls, replies, app


def test_parse_grounding_separates_places_from_review_links():
    places, sources = parse_grounding({"groundingMetadata": {"groundingChunks": CHUNKS}})
    assert [p.title for p in places] == ["Synthetic Electro Tech", "Fixture Components"]
    assert places[0].address == "2nd Floor, No 1, Synthetic Road, Bengaluru 560002"
    assert places[0].uri.endswith("cid=1111111111111111111")
    assert places[1].address is None and places[1].place_id == "places/ChIJsynthetic2"
    # Attribution keeps the exact titles and URIs in response order, reviews included.
    assert [(s.title, s.kind) for s in sources] == [
        ("Synthetic Electro Tech - Google Maps", "place"),
        ("Review of Synthetic Electro Tech", "review"),
        ("Fixture Components - Google Maps", "place"),
    ]
    assert sources[1].uri == CHUNKS[1]["maps"]["uri"]


def test_city_mapping_and_validation():
    location = resolve_location(INDIA, "Bengaluru", None, None)
    assert (location.city, location.latitude, location.longitude) == ("Bengaluru", 12.9716, 77.5946)
    assert location.source == "city" and location.approximate and "Approximate" in location.label
    assert resolve_location(INDIA, " kochi ", None, None).city == "Kochi"
    with pytest.raises(JobError) as error:
        resolve_location(INDIA, "Atlantis", None, None)
    assert (error.value.status, error.value.code) == (422, "CITY_NOT_SUPPORTED")
    coords = resolve_location(INDIA, None, 12.97163, 77.59461)
    assert (coords.latitude, coords.longitude, coords.source) == (12.97, 77.59, "coordinates")
    for args, code in [
        (("Delhi", 12.9, 77.5), "INVALID_LOCATION"),
        ((None, 12.9, None), "INVALID_LOCATION"),
        ((None, 51.5, -0.12), "LOCATION_OUTSIDE_COUNTRY"),
    ]:
        with pytest.raises(JobError) as error:
            resolve_location(INDIA, *args)
        assert error.value.code == code


def test_categories_come_from_the_bom_only():
    job = SimpleNamespace(items=items())
    assert part_categories(job) == ["resistors", "LEDs", "sensors"]
    job.items = [BomItem(line_id="L01", raw_name="Gizmo")]
    assert part_categories(job) == ["electronic components"]


def test_live_lookup_returns_places_attribution_and_records_usage(capsys):
    client, job_id, calls, replies, app = setup()
    replies.append(maps_reply())
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["demo"] is False and body["cached"] is False
    assert body["summary"] == TEXT and body["summary_label"] == SUMMARY_LABEL
    assert [p["title"] for p in body["places"]] == ["Synthetic Electro Tech", "Fixture Components"]
    assert body["attribution"]["provider"] == "Google Maps"
    assert [s["uri"] for s in body["attribution"]["sources"]] == [
        CHUNKS[0]["maps"]["uri"],
        CHUNKS[1]["maps"]["uri"],
        CHUNKS[2]["maps"]["uri"],
    ]
    assert body["location"]["city"] == "Bengaluru" and body["location"]["approximate"]
    # One call: Maps tool, the location, low thinking, and only part categories in the prompt.
    ((path, payload),) = calls
    assert path.endswith("/gemini-3.8-flash:generateContent")
    assert payload["tools"] == [{"googleMaps": {}}]
    assert payload["toolConfig"]["retrievalConfig"]["latLng"] == {
        "latitude": 12.9716,
        "longitude": 77.5946,
    }
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}
    prompt = payload["contents"][0]["parts"][0]["text"]
    assert "resistors, LEDs, sensors" in prompt
    assert "Secret" not in prompt and "BME280" not in prompt and "330" not in prompt
    usage = [
        json.loads(line.removeprefix("GEMINI_USAGE "))
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("GEMINI_USAGE ")
    ]
    assert len(usage) == 1
    assert usage[0]["site"] == "markets" and usage[0]["search_queries"] == 1
    assert usage[0]["grounded"] is True and usage[0]["job_id"] == job_id
    cost = app.state.job_service.store.get(job_id).job.cost_estimate
    assert cost.calls_by_site == {"markets": 1} and cost.search_queries == 1


def test_cache_hit_makes_no_call_and_stores_no_project_data():
    client, job_id, calls, replies, app = setup()
    replies.append(maps_reply())
    first = client.get(f"/v1/jobs/{job_id}/markets", params={"lat": 12.9716, "lng": 77.5946})
    assert first.status_code == 200
    # Same rounded location and categories: served from the shared cache, no second call.
    second = client.get(f"/v1/jobs/{job_id}/markets", params={"lat": 12.9744, "lng": 77.5899})
    assert second.status_code == 200
    assert second.json()["cached"] is True
    assert second.json()["attribution"] == first.json()["attribution"]
    assert len(calls) == 1
    stored = json.dumps(app.state.shared_cache.records, default=str)
    assert "Secret" not in stored and "330 ohm" not in stored and job_id not in stored


def test_daily_quota_per_owner():
    client, job_id, calls, replies, _ = setup(markets_daily_limit=1)
    replies.extend([maps_reply(), maps_reply()])
    assert client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"}).status_code == 200
    # A different location misses the cache and is over the quota.
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Chennai"})
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "FEATURE_QUOTA"
    assert int(response.headers["Retry-After"]) >= 1
    assert len(calls) == 1
    # Cache hits stay free after the quota is used.
    assert client.get(f"/v1/jobs/{job_id}/markets", params={"city": "bengaluru"}).status_code == 200


def test_global_daily_cap():
    client, job_id, calls, replies, _ = setup(markets_global_daily_limit=1, markets_daily_limit=5)
    replies.extend([maps_reply()])
    assert client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"}).status_code == 200
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Mumbai"})
    assert response.status_code == 429 and len(calls) == 1


def test_demo_job_returns_labelled_sample_without_a_call():
    client, job_id, calls, _, _ = setup(demo=True)
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"})
    assert response.status_code == 200
    body = response.json()
    assert body["demo"] is True and "Demo sample" in body["label"]
    assert all("(demo)" in p["title"] and p["uri"] is None for p in body["places"])
    assert body["attribution"]["sources"] == []
    assert calls == []


def test_flag_off_and_missing_key_never_call_gemini():
    client, job_id, calls, _, _ = setup(markets_enabled=False)
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"})
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "FEATURE_DISABLED"
    client, job_id, calls2, _, _ = setup(gemini_api_key=None)
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"})
    assert response.json()["error"]["code"] == "FEATURE_UNAVAILABLE"
    assert calls == calls2 == []
    assert Settings(_env_file=None).markets_enabled is True


def test_validation_errors_and_empty_bom():
    client, job_id, calls, _, _ = setup()
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Atlantis"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "CITY_NOT_SUPPORTED"
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"pin": "560002"})
    assert response.status_code == 422  # PIN lookups were removed in v0.23
    assert client.get(f"/v1/jobs/{job_id}/markets").status_code == 422
    client, job_id, calls2, _, _ = setup(with_items=False)
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"})
    assert response.status_code == 409
    assert calls == calls2 == []


def test_ungrounded_text_is_not_shown_and_bad_output_fails():
    client, job_id, calls, replies, _ = setup()
    replies.append(maps_reply(chunks=[]))
    body = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"}).json()
    assert body["summary"] is None and body["places"] == []
    assert body["attribution"]["sources"] == []
    replies.append(maps_reply(finish="MAX_TOKENS"))
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Chennai"})
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "INVALID_OUTPUT"


def test_job_budget_blocks_paid_lookup():
    client, job_id, calls, _, app = setup()

    def spent(record):
        record.job.cost_estimate = CostEstimate(
            total_usd=0.3, run_usd=0.3, budget_usd=0.25, budget_reached=True
        )

    app.state.job_service.store.mutate(job_id, spent)
    response = client.get(f"/v1/jobs/{job_id}/markets", params={"city": "Bengaluru"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_BUDGET_REACHED"
    assert calls == []
