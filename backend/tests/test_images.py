"""Image fallbacks use synthetic parts; generated images are stubs, never real model output."""

import json
from urllib.parse import unquote

from fastapi.testclient import TestClient

from bharat_sourcer.config import Settings
from bharat_sourcer.images import PartImageService, illustration
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    CreateJob,
    PartImage,
    Report,
    ReportLine,
    VerifiedOffer,
)
from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import page_images

SELLER = "https://seller.example/part"
STUB = "data:image/jpeg;base64,c3R1Yg=="


def setup(name="Mystery widget", offers=(), candidates=(), demo=False, **overrides):
    defaults = {"demo_mode": True, "image_generation_enabled": True, "gemini_api_key": "x"}
    settings = Settings(_env_file=None, **(defaults | overrides))
    app = create_app(settings)
    service = app.state.job_service
    job, token = service.create(CreateJob(url="https://example.com"))

    def seed(record):
        item = BomItem(line_id="L01", raw_name=name, qty=1)
        record.job.demo = demo
        record.job.status = "done"
        record.job.items = [item]
        record.job.report = Report(
            demo=demo,
            summary="Synthetic test report",
            lines=[
                ReportLine(
                    item=item,
                    sourcing_status="offers_found" if offers else "no_verified_offers",
                    offers=list(offers),
                    image_candidates=list(candidates),
                )
            ],
        )

    service.store.mutate(job.job_id, seed)
    calls = []

    def generator(raw_name):
        calls.append(raw_name)
        return STUB

    app.state.image_service.generator = generator
    client = TestClient(app)
    client.headers["X-Job-Token"] = token
    return client, job.job_id, calls


def path(job_id, line_id="L01"):
    return f"/v1/jobs/{job_id}/parts/{line_id}/image"


def test_seller_and_source_candidates_are_deduplicated_and_failed_urls_skipped():
    offer = VerifiedOffer(
        url=SELLER,
        seller="seller.example",
        title="Synthetic part",
        price_inr="1.00",
        stock="in_stock",
        image_url="https://seller.example/a.png",
    )
    source = PartImage(url="https://other.example/b.png", kind="source", label="Reference")
    duplicate = PartImage(url="https://seller.example/a.png", kind="source", label="Duplicate")
    client, job_id, calls = setup(offers=[offer], candidates=[source, duplicate])
    body = client.get(path(job_id)).json()
    assert [(c["url"], c["kind"]) for c in body["candidates"]] == [
        ("https://seller.example/a.png", "seller"),
        ("https://other.example/b.png", "source"),
    ]
    assert body["generation_status"] == "not_needed"
    retry = client.post(path(job_id), json={"failed_urls": ["https://seller.example/a.png"]})
    assert [c["url"] for c in retry.json()["candidates"]] == ["https://other.example/b.png"]
    assert calls == []


def test_category_illustration_is_labelled_and_never_generates():
    client, job_id, calls = setup(name="220 ohm resistor")
    body = client.post(path(job_id), json={}).json()
    assert body["candidates"] == []
    assert body["fallback"]["kind"] == "category"
    assert "not a product photo" in unquote(body["fallback"]["url"])
    assert body["generation_status"] == "not_needed"
    assert calls == []


def test_illustration_escapes_part_names():
    image = illustration('<script>alert("x")</script> widget')
    assert image.kind == "placeholder"
    assert "<script>" not in unquote(image.url)


def test_get_never_generates_and_post_generates_once_then_caches():
    client, job_id, calls = setup()
    assert client.get(path(job_id)).json()["generation_status"] == "not_requested"
    first = client.post(path(job_id), json={}).json()
    assert first["generation_status"] == "ready"
    assert first["candidates"][0]["kind"] == "generated"
    assert "AI-generated" in first["candidates"][0]["label"]
    assert client.get(path(job_id)).json()["candidates"][0]["url"] == STUB
    assert client.post(path(job_id), json={}).json()["generation_status"] == "ready"
    assert calls == ["Mystery widget"]


def test_generation_requires_flag_key_and_live_job():
    for overrides in [
        {"image_generation_enabled": False},
        {"gemini_api_key": None},
        {"demo": True},
    ]:
        client, job_id, calls = setup(**overrides)
        assert client.post(path(job_id), json={}).json()["generation_status"] == "not_requested"
        assert calls == []


def test_generation_failure_is_cached_without_retrying_immediately():
    client, job_id, _ = setup()
    service: PartImageService = client.app.state.image_service
    attempts = []

    def failing(name):
        attempts.append(name)
        raise ValueError("Synthetic failure")

    service.generator = failing
    assert client.post(path(job_id), json={}).json()["generation_status"] == "unavailable"
    assert client.post(path(job_id), json={}).json()["generation_status"] == "unavailable"
    assert len(attempts) == 1


def test_global_daily_image_quota_is_enforced():
    client, job_id, calls = setup(image_daily_limit=1)
    service = client.app.state.image_service
    assert client.post(path(job_id), json={}).json()["generation_status"] == "ready"

    def seed(record):
        record.job.items[0] = BomItem(line_id="L01", raw_name="Another widget", qty=1)

    service.jobs.store.mutate(job_id, seed)
    assert client.post(path(job_id), json={}).json()["generation_status"] == "unavailable"
    assert calls == ["Mystery widget"]


def test_unknown_line_and_wrong_token_are_rejected():
    client, job_id, _ = setup()
    assert client.get(path(job_id, "L99")).status_code == 404
    assert client.get(path(job_id), headers={"X-Job-Token": "wrong" * 8}).status_code in {
        401,
        403,
        404,
    }


def test_page_images_only_reads_matching_product_json_ld():
    products = [
        {"@type": "Product", "name": "TTP223 touch module", "image": "/img/ttp223.png"},
        {"@type": "Product", "name": "Unrelated speaker", "image": "/img/speaker.png"},
    ]
    body = "".join(
        f'<script type="application/ld+json">{json.dumps(product)}</script>' for product in products
    )
    page = Page(
        url="https://seller.example/ttp223",
        status=200,
        headers={"content-type": "text/html"},
        body=body.encode(),
    )
    images = page_images(page, "TTP223 touch module")
    assert [image.url for image in images] == ["https://seller.example/img/ttp223.png"]
    assert images[0].kind == "source"
    assert page_images(Page(page.url, 404, page.headers, page.body), "TTP223") == []
