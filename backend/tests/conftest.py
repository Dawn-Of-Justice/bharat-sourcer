"""Keep tests hermetic: developer or CI shells may export real BS_* settings."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch):
    for name in [name for name in os.environ if name.startswith("BS_")]:
        monkeypatch.delenv(name)
    # The project overview starts automatically after extraction and reads GitHub and
    # Gemini; tests that exercise it pass overview_enabled=True with fakes (test_overview.py).
    monkeypatch.setenv("BS_OVERVIEW_ENABLED", "false")
