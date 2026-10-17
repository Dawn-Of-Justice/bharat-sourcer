"""Title-only regressions from the live probe; no fixture prices are verified."""

import pytest

from bharat_sourcer.sourcing.textmatch import title_gate


@pytest.mark.parametrize(
    "query,title,expected",
    [
        ("NE555P Timer DIP-8", "NE555P TEXAS INSTRUMENTS Timer Single Precision PDIP-8", True),
        ("NE555P Timer DIP-8", "NE555 Timer IC SOIC-8 SMD Package", False),
        ("NE555P Timer DIP-8", "NE555P Timer PDIP-14", False),
        ("ESP32 development board", "ESP32 Camera Development Board OV2640", False),
        ("ESP32 development board", "ESP32 Development Board CP2102 38 Pin", True),
        ("ESP32 camera board", "ESP32 Camera Development Board OV2640", True),
        ("Arduino Uno", "USB A to USB B Cable for Arduino UNO", False),
        ("Arduino Uno", "TFT Display Shield for Arduino UNO", False),
        ("Arduino Uno", "Original Arduino UNO R4 WiFi", False),
        ("Arduino Uno", "Official Arduino UNO Q Single Board Computer", False),
        ("Arduino Uno R4", "Original Arduino UNO R4 WiFi", True),
        ("Arduino Uno", "Original Arduino Uno Rev3 with Cable", True),
        ("HC-SR04 ultrasonic sensor", "HC-SR04 Ultrasonic Sensor Acrylic Holder", False),
        ("HC-SR04 holder", "HC-SR04 Ultrasonic Sensor Acrylic Holder", True),
        ("NE555 timer", "NE555 Timer Surface Mount SOIC-8", True),
        ("ESP32 DOIT DevKit V1", "ESP32 Development Board DOIT DevKit V1", True),
        ("ESP32 DOIT DevKit V1", "ESP32 DEVKIT V1 WiFi Bluetooth Board", False),
    ],
)
def test_matching(query, title, expected):
    assert title_gate(query, title) is expected


def test_tracking_dedup_preserves_variants():
    from bharat_sourcer.sourcing.sellers import same_listing

    base = "https://example.in/products/sensor"
    assert same_listing(base + "?variant=1&_gsid=abc&utm_source=shopify", base + "?variant=1")
    assert not same_listing(base + "?variant=1", base + "?variant=2")
    assert not same_listing(base, base + "?variant=1")


def test_different_generation_retained_for_adaptation_after_judge(monkeypatch):
    from bharat_sourcer.compat import resolve_part
    from bharat_sourcer.schemas import BomItem, VerifiedOffer
    from bharat_sourcer.sourcing.part_spec import buyable_spec
    from bharat_sourcer.sourcing.service import SourcingService, VerifyState

    item = BomItem(line_id="L01", raw_name="Arduino Uno")
    offer = VerifiedOffer(
        url="https://example.in/uno-r4",
        seller="example.in",
        title="Arduino Uno R4 WiFi",
        price_inr="1000.00",
        stock="in_stock",
    )
    monkeypatch.setattr("bharat_sourcer.sourcing.service.review_candidates", lambda *args: [offer])
    service = SourcingService(None, judge=object())
    state = VerifyState()
    assert not service._review(
        buyable_spec(item, None), None, resolve_part(item), [object()], state, []
    )
    assert len(state.offers) == 1
    assert state.offers[0].match.status == "partial"
    assert "board_generation" in state.offers[0].match.conflicts
    assert "adaptation" in state.offers[0].match.reasons[0]
