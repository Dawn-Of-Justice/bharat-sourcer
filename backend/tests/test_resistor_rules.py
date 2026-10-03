from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from bharat_sourcer import resistor_rules as rules
from bharat_sourcer.config import Settings
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import BomItem, ChatReply, ResistorInputs


def inputs(**changes):
    return ResistorInputs(
        **(
            dict(
                line_id="L01",
                purpose="led_series",
                supply_max_v=3.3,
                led_forward_min_v=2,
                target_max_ma=5,
                driver_limit_ma=8,
                confirmed=True,
            )
            | changes
        )
    )


@pytest.fixture(autouse=True)
def reset_rule(monkeypatch):
    monkeypatch.setattr(rules, "_quarantined", False)


def test_led_calculation_accounts_for_tolerance_and_power():
    result = rules.calculate(inputs())
    assert Decimal(result.resistance_ohm) == 300
    assert Decimal(result.worst_case_current_ma) <= 5
    assert Decimal(result.worst_case_power_w) >= Decimal("1.3") ** 2 / 285
    assert Decimal(result.minimum_rated_power_w) >= Decimal("1.3") ** 2 / 285 * 2
    assert result.recovery == "none"


@pytest.mark.parametrize("voltage", [3.3, 5, 12, 24])
@pytest.mark.parametrize("ma", [1, 5, 10, 20])
def test_current_bound_and_fallback_agreement(voltage, ma):
    value = inputs(supply_max_v=voltage, target_max_ma=ma, driver_limit_ma=7)
    result = rules.calculate(value)
    resistance = Decimal(result.resistance_ohm)
    current = (Decimal(str(voltage)) - 2) / (resistance * Decimal(".95")) * 1000
    assert current <= min(ma, 7)
    minimum = (Decimal(str(voltage)) - 2) / Decimal(min(ma, 7)) * 1000 / Decimal(".95")
    assert rules.primary_select(minimum) == rules.fallback_select(minimum)


def test_fault_quarantines_primary_and_uses_validated_fallback_for_future_calls():
    with patch.object(rules, "primary_select", return_value=Decimal("0")) as broken:
        result = rules.calculate(inputs())
        assert result.recovery == "validated_fallback"
        assert Decimal(result.resistance_ohm) == 300
        calls = broken.call_count
        again = rules.calculate(inputs())
        assert again.recovery == "validated_fallback"
        assert broken.call_count == calls


def test_both_rules_broken_produce_no_recommendation():
    with (
        patch.object(rules, "primary_select", side_effect=RuntimeError),
        patch.object(rules, "fallback_select", return_value=Decimal("1")),
    ):
        result = rules.calculate(inputs())
    assert result.status == "unavailable"
    assert result.resistance_ohm is None
    assert result.recovery == "blocked"


@pytest.mark.parametrize(
    "changes",
    [
        {"confirmed": False},
        {"target_max_ma": 0},
        {"supply_max_v": float("nan")},
        {"supply_max_v": 240},
        {"purpose": "piezo_input"},
    ],
)
def test_rejects_unconfirmed_or_unsupported_inputs(changes):
    with pytest.raises(ValidationError):
        inputs(**changes)


def test_invalid_voltage_headroom():
    with pytest.raises(ValueError):
        rules.calculate(inputs(supply_max_v=2))


def test_api_persists_conditional_suggestion_without_changing_bom():
    app = create_app(Settings(_env_file=None))
    client = TestClient(app)
    created = client.post("/v1/jobs", json={"url": "https://example.com"}).json()
    root = f"/v1/jobs/{created['job_id']}"
    headers = {"X-Job-Token": created["job_token"]}
    before = client.get(root, headers=headers).json()
    assert client.post(root + "/resistor-advice", json=inputs().model_dump()).status_code == 404
    result = client.post(root + "/resistor-advice", headers=headers, json=inputs().model_dump())
    assert result.status_code == 200
    assert result.json()["items"] == before["items"]
    advice = result.json()["resistor_advice"][-1]
    assert advice["status"] == "suggestion"
    assert advice["inputs"]["confirmed"] is True
    assert client.get(root, headers=headers).json()["resistor_advice"] == [advice]
    bad = client.post(
        root + "/resistor-advice", headers=headers, json=inputs(line_id="missing").model_dump()
    )
    assert bad.status_code == 422


def test_chat_asks_contextual_question_without_inventing_value():
    class Extractor:
        def extract(self, url):
            return [BomItem(line_id="L01", raw_name="resistors", qty=2)]

    class Assistant:
        def reply(self, job):
            return ChatReply(
                text="Which resistor is in series with the LED?",
                cited_line_ids=["L01"],
                resistor_question={
                    "line_id": "L01",
                    "purpose": "unknown",
                    "question": "Is this for the LED or the piezo input?",
                },
            )

    app = create_app(
        Settings(_env_file=None, demo_mode=False, sourcing_enabled=False, gemini_api_key="test"),
        extractor=Extractor(),
        assistant=Assistant(),
    )
    client = TestClient(app)
    created = client.post("/v1/jobs", json={"url": "https://youtu.be/abcdefghijk"}).json()
    root = f"/v1/jobs/{created['job_id']}"
    headers = {"X-Job-Token": created["job_token"]}
    assert (
        client.post(
            root + "/messages",
            headers=headers,
            json={"message_id": str(uuid4()), "text": "What resistance should I use?"},
        ).status_code
        == 202
    )
    job = client.get(root, headers=headers).json()
    assert job["messages"][-1]["resistor_question"]["purpose"] == "unknown"
    assert job["items"][0]["qty"] == 2
    assert job["resistor_advice"] == []
