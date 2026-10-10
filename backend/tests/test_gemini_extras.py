"""Gemini extras use synthetic jobs and a mocked transport; no model is ever called."""

import base64
import io
import json
import wave

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from bharat_sourcer.config import Settings
from bharat_sourcer.gemini_extras import explain_script, zoom_candidate
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import (
    BomItem,
    Clarification,
    Compatibility,
    CreateJob,
    Evidence,
    ProjectContext,
    Report,
    ReportLine,
    VerifiedOffer,
)

FLAGS = {"explain_enabled": True, "zoom_enabled": True, "scan_enabled": True}
PCM = b"\x01\x00" * 2400  # 0.1 s of synthetic 24 kHz audio


def items():
    return [
        BomItem(
            line_id="L01",
            raw_name="Mystery chip",
            evidence=[Evidence(timestamp="03:12", observation="Small black chip on the board")],
        ),
        BomItem(
            line_id="L02",
            raw_name="ESP32 board",
            evidence=[Evidence(timestamp="00:30", observation="ESP32 silkscreen visible")],
        ),
        BomItem(line_id="L03", raw_name="LiPo battery"),
    ]


def setup(demo=False, status="awaiting_confirmation", **overrides):
    defaults = {"demo_mode": True, "gemini_api_key": "test-secret"} | FLAGS
    settings = Settings(_env_file=None, **(defaults | overrides))
    app = create_app(settings)
    service = app.state.job_service
    job, token = service.create(CreateJob(url="https://youtu.be/abcdefghijk"))

    def seed(record):
        record.job.demo = demo
        record.job.status = status
        record.job.items = items()
        record.job.project = ProjectContext(
            title="Synthetic drum trigger", summary="A test board reads a piezo."
        )

    service.store.mutate(job.job_id, seed)
    calls = []
    replies = {}

    def handle(request):
        payload = json.loads(request.content)
        calls.append((request.url.path, payload))
        assert request.headers["x-goog-api-key"] == "test-secret"
        for key, reply in replies.items():
            if key in request.url.path:
                return reply(payload) if callable(reply) else reply
        raise AssertionError("Unexpected Gemini call " + request.url.path)

    app.state.extras.transport = httpx.MockTransport(handle)
    client = TestClient(app)
    client.headers["X-Job-Token"] = token
    return client, job.job_id, calls, replies


def structured(value):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {"finishReason": "STOP", "content": {"parts": [{"text": json.dumps(value)}]}}
            ],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5},
        },
    )


def speech(pcm=PCM, mime="audio/L16;codec=pcm;rate=24000"):
    return httpx.Response(
        200,
        json={
            "candidates": [
                {
                    "finishReason": "STOP",
                    "content": {
                        "parts": [
                            {
                                "inlineData": {
                                    "mimeType": mime,
                                    "data": base64.b64encode(pcm).decode(),
                                }
                            }
                        ]
                    },
                }
            ]
        },
    )


def photo(fmt="PNG", size=(64, 48)):
    buffer = io.BytesIO()
    Image.new("RGB", size, "white").save(buffer, format=fmt)
    return base64.b64encode(buffer.getvalue()).decode()


def test_features_are_off_by_default_and_never_call_gemini():
    client, job_id, calls, _ = setup(explain_enabled=False, zoom_enabled=False, scan_enabled=False)
    status = client.get(f"/v1/jobs/{job_id}/extras").json()
    assert not any(status[name]["enabled"] for name in ("explain", "zoom", "scan"))
    for path, body in [
        ("explain", {"language": "hi"}),
        ("items/L01/zoom", {}),
        ("scan", {"image_base64": photo()}),
    ]:
        response = client.post(f"/v1/jobs/{job_id}/{path}", json=body)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "FEATURE_DISABLED"
    assert calls == []
    assert Settings(_env_file=None).explain_enabled is False


def test_status_lists_zoom_candidates_and_quota():
    client, job_id, _, _ = setup()
    status = client.get(f"/v1/jobs/{job_id}/extras").json()
    assert status["zoom_line_ids"] == ["L01"]
    assert status["explain"] == {"enabled": True, "daily_limit": 10, "remaining": 10}
    assert "ml" in status["languages"]
    assert status["scan_mime_types"] == ["image/jpeg", "image/png", "image/webp"]


def test_explain_english_speaks_script_once_then_serves_cache(capsys):
    client, job_id, calls, replies = setup()
    replies["tts:generateContent"] = speech()
    first = client.post(f"/v1/jobs/{job_id}/explain", json={"language": "en"})
    assert first.status_code == 200
    body = first.json()
    assert body["cached"] is False and body["translated"] is False
    assert body["transcript"] == body["source_script"]
    assert "Mystery chip" in body["transcript"] and "Lithium" in body["transcript"]
    assert "not verified" in body["label"]
    with wave.open(io.BytesIO(base64.b64decode(body["audio_base64"]))) as audio:
        assert audio.getframerate() == 24000 and audio.getnframes() == 2400
    assert body["duration_s"] == 0.1
    [(path, payload)] = calls
    assert path.endswith("/gemini-3.8-flash-tts:generateContent")
    assert payload["generationConfig"]["responseModalities"] == ["AUDIO"]
    voice = payload["generationConfig"]["speechConfig"]["voiceConfig"]
    assert voice["prebuiltVoiceConfig"]["voiceName"] == "Kore"
    assert '"site": "explain_tts"' in capsys.readouterr().out
    again = client.post(f"/v1/jobs/{job_id}/explain", json={"language": "en"}).json()
    assert again["cached"] is True and again["audio_base64"] == body["audio_base64"]
    assert len(calls) == 1
    status = client.get(f"/v1/jobs/{job_id}/extras").json()
    assert status["explain"]["remaining"] == 9


def test_explain_translates_then_speaks_keeping_part_numbers():
    client, job_id, calls, replies = setup()
    replies["gemini-3.8-flash:generateContent"] = structured({"text": "ESP32 बोर्ड (अनुवाद)"})
    replies["tts:generateContent"] = speech()
    body = client.post(f"/v1/jobs/{job_id}/explain", json={"language": "hi"}).json()
    assert body["translated"] is True and body["transcript"] == "ESP32 बोर्ड (अनुवाद)"
    assert "machine-translated" in body["label"]
    translate, tts = calls
    assert "Hindi" in translate[1]["systemInstruction"]["parts"][0]["text"]
    assert "part numbers" in translate[1]["systemInstruction"]["parts"][0]["text"]
    assert json.loads(translate[1]["contents"][0]["parts"][0]["text"]) == {
        "text": body["source_script"]
    }
    assert "ESP32 बोर्ड" in tts[1]["contents"][0]["parts"][0]["text"]


def test_explain_quota_and_bad_audio():
    client, job_id, _, replies = setup(explain_daily_limit=1)
    replies["tts:generateContent"] = speech(mime="audio/mpeg")
    failed = client.post(f"/v1/jobs/{job_id}/explain", json={"language": "en"})
    assert failed.status_code == 502 and failed.json()["error"]["code"] == "INVALID_OUTPUT"
    limited = client.post(f"/v1/jobs/{job_id}/explain", json={"language": "en"})
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "FEATURE_QUOTA"
    assert int(limited.headers["Retry-After"]) > 0
    assert client.post(f"/v1/jobs/{job_id}/explain", json={"language": "xx"}).status_code == 422


def test_explain_demo_returns_labelled_silence_without_calls():
    client, job_id, calls, _ = setup(demo=True)
    body = client.post(f"/v1/jobs/{job_id}/explain", json={"language": "ta"}).json()
    assert body["demo"] is True and body["translated"] is False
    assert "Demo sample" in body["label"]
    assert body["duration_s"] == 1.0
    assert calls == []


def test_explain_script_is_deterministic_bounded_and_reports_changes():
    client, job_id, _, _ = setup()
    service = client.app.state.job_service
    job = service.get(job_id, client.headers["X-Job-Token"])
    offer = VerifiedOffer(
        url="https://seller.example/a",
        seller="Example",
        title="Synthetic",
        price_inr="10.00",
        compatibility=Compatibility(
            status="changes_required", changes=["Add a level shifter on SDA"]
        ),
    )
    job.items[0].clarifications = [Clarification(field="logic_v", question="Is it 3.3 V?")]
    job.report = Report(
        summary="Synthetic",
        lines=[ReportLine(item=job.items[0], sourcing_status="offers_found", offers=[offer])],
    )
    script = explain_script(job, 900)
    assert script == explain_script(job, 900)
    assert "Wiring change for Mystery chip: Add a level shifter on SDA." in script
    assert "Check for Mystery chip: Is it 3.3 V?" in script
    short = explain_script(job, 500)
    assert len(short) <= 500 and short.endswith("seller prices are not verified.")
    assert "Disconnect power" in short and "Lithium" in short
    assert "Wiring change" not in short


def test_zoom_reads_clip_and_creates_reviewable_proposal():
    client, job_id, calls, replies = setup()
    replies["gemini-3.8-flash:generateContent"] = structured(
        {
            "readable": True,
            "marking": "ATMEGA328P",
            "suggested_name": "ATmega328P microcontroller",
            "seen_at": "03:15",
            "observation": "The chip top reads ATMEGA328P.",
        }
    )
    response = client.post(f"/v1/jobs/{job_id}/items/L01/zoom", json={})
    assert response.status_code == 200
    body = response.json()
    assert body["clip"] == {"start": "03:07", "end": "03:22"}
    assert body["evidence"]["timestamp"] == "03:15"
    assert body["marking"] == "ATMEGA328P" and body["demo"] is False
    [(_path, payload)] = calls
    video = payload["contents"][0]["parts"][0]
    assert video["fileData"]["fileUri"] == "https://www.youtube.com/watch?v=abcdefghijk"
    assert video["videoMetadata"]["startOffset"] == "187s"
    assert video["videoMetadata"]["endOffset"] == "202s"
    assert payload["generationConfig"]["mediaResolution"] == "MEDIA_RESOLUTION_HIGH"
    job = client.get(f"/v1/jobs/{job_id}").json()
    assert job["items"][0]["raw_name"] == "Mystery chip"  # not overwritten
    message = job["messages"][-1]
    assert message["message_id"] == body["message_id"]
    assert message["proposal"]["status"] == "pending"
    assert "03:07–03:22" in message["text"] and "not verified" in message["text"]
    decided = client.post(
        f"/v1/jobs/{job_id}/messages/{body['message_id']}/decision", json={"action": "accept"}
    ).json()
    assert decided["items"][0]["raw_name"] == "ATmega328P microcontroller"


def test_zoom_unreadable_clip_suggests_nothing_and_clamps_timestamp():
    client, job_id, _, replies = setup()
    replies["gemini-3.8-flash:generateContent"] = structured(
        {
            "readable": False,
            "marking": "guess",
            "suggested_name": "Guess chip",
            "seen_at": "09:00",
            "observation": "The chip is blurred.",
        }
    )
    body = client.post(f"/v1/jobs/{job_id}/items/L01/zoom", json={"timestamp": "03:12"}).json()
    assert body["marking"] is None and body["suggested_name"] is None
    assert body["evidence"]["timestamp"] == "03:07"
    message = client.get(f"/v1/jobs/{job_id}").json()["messages"][-1]
    assert message["proposal"] is None and "No marking could be read" in message["text"]


def test_zoom_rejects_wrong_state_line_and_timestamp_without_calls():
    client, job_id, calls, _ = setup()
    assert client.post(f"/v1/jobs/{job_id}/items/L99/zoom", json={}).status_code == 404
    assert client.post(f"/v1/jobs/{job_id}/items/L03/zoom", json={}).status_code == 409
    wrong = client.post(f"/v1/jobs/{job_id}/items/L01/zoom", json={"timestamp": "00:01"})
    assert wrong.status_code == 422
    done, done_id, done_calls, _ = setup(status="done")
    assert done.post(f"/v1/jobs/{done_id}/items/L01/zoom", json={}).status_code == 409
    assert calls == [] and done_calls == []


def test_scan_suggests_owned_parts_through_a_proposal_and_never_stores_photo():
    client, job_id, calls, replies = setup()
    replies["gemini-3.8-flash:generateContent"] = structured(
        {
            "matches": [
                {
                    "line_id": "L02",
                    "likely_present": True,
                    "box_2d": [100, 120, 400, 520.4],
                    "observation": "Blue ESP32 board",
                },
                {"line_id": "L02", "likely_present": False, "observation": "duplicate"},
                {"line_id": "L99", "likely_present": True, "observation": "invented"},
                {
                    "line_id": "L01",
                    "likely_present": False,
                    "box_2d": [500, 500, 100, 100],
                    "observation": "Not seen",
                },
            ]
        }
    )
    image = photo("WEBP")
    response = client.post(f"/v1/jobs/{job_id}/scan", json={"image_base64": image})
    assert response.status_code == 200
    body = response.json()
    assert [(s["line_id"], s["likely_present"], s["box_2d"]) for s in body["suggestions"]] == [
        ("L02", True, [100, 120, 400, 520]),
        ("L01", False, None),
    ]
    [(_path, payload)] = calls
    sent = payload["contents"][0]["parts"][0]["inlineData"]
    assert sent["mimeType"] == "image/jpeg"
    assert base64.b64decode(sent["data"]).startswith(b"\xff\xd8\xff")
    job = client.get(f"/v1/jobs/{job_id}")
    assert image not in job.text and sent["data"] not in job.text
    assert job.json()["items"][1]["user_has_it"] is False
    accepted = client.post(
        f"/v1/jobs/{job_id}/messages/{body['message_id']}/decision", json={"action": "accept"}
    ).json()
    assert accepted["items"][1]["user_has_it"] is True


def test_scan_validates_photo_before_any_call():
    client, job_id, calls, _ = setup(scan_max_bytes=100_000)
    gif = base64.b64encode(b"GIF89a" + b"\x00" * 50).decode()
    for body, status in [
        ({"image_base64": "not base64!!"}, 422),
        ({"image_base64": gif}, 415),
        ({"image_base64": base64.b64encode(b"\xff\xd8\xff" + b"\x00" * 50).decode()}, 422),
        ({"image_base64": base64.b64encode(b"\x00" * 100_001).decode()}, 413),
    ]:
        assert client.post(f"/v1/jobs/{job_id}/scan", json=body).status_code == status
    assert calls == []


def test_scan_demo_returns_labelled_sample_proposal():
    client, job_id, calls, _ = setup(demo=True)
    body = client.post(
        f"/v1/jobs/{job_id}/scan", json={"image_base64": "data:image/png;base64," + photo()}
    ).json()
    assert body["demo"] is True and "Demo sample" in body["label"]
    assert body["suggestions"][0]["observation"].startswith("Demo sample")
    message = client.get(f"/v1/jobs/{job_id}").json()["messages"][-1]
    assert message["text"].startswith("Demo sample.")
    assert calls == []


def test_zoom_candidate_rule():
    chip, board, battery = items()
    assert zoom_candidate(chip) and not zoom_candidate(board) and not zoom_candidate(battery)
    board.clarifications = [Clarification(field="logic_v", question="Which voltage?")]
    assert zoom_candidate(board)


def test_extras_do_not_spend_the_project_action_budget():
    settings = Settings(
        _env_file=None,
        auth_enabled=True,
        gcp_project="fixture-project",
        guest_session_secret="test-secret-only-not-production-123456",
        guest_daily_actions=1,
        **FLAGS,
    )
    client = TestClient(create_app(settings), base_url="https://testserver")
    client.headers["X-Requested-With"] = "BharatSourcer"
    client.post("/v1/session/guest")
    job_id = client.post("/v1/jobs", json={"url": "https://example.com"}).json()["job_id"]
    for _ in range(3):
        response = client.post(f"/v1/jobs/{job_id}/explain", json={"language": "en"})
        assert response.status_code == 200 and response.json()["demo"] is True
    assert client.post(f"/v1/jobs/{job_id}/resume").status_code == 429
