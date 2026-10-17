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
    ],
)
def test_matching(query, title, expected):
    assert title_gate(query, title) is expected
