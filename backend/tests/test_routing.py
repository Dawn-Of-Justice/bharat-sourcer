"""Synthetic routing regressions; no prices here are verified offers."""

import json
import threading
from types import SimpleNamespace

import pytest

from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.politeness import Politeness
from bharat_sourcer.sourcing.routing import Rung, normalise, route_queries
from bharat_sourcer.sourcing.seller_search import ADAPTERS, Candidate, SellerSearch


@pytest.mark.parametrize(
    "name",
    [
        "Arduino Uno R3",
        "ESP32 DevKit V1",
        "10k ohm resistor",
        "BME280 module",
        "SG90 servo",
        "HC-SR04",
        "0.96 inch OLED I2C",
        "LM2596 buck",
        "TP4056 module",
        "Jumper wires male to female",
        "18650 holder 2-cell",
        "WS2812B strip",
        "NEMA 17 stepper",
        "A4988 driver",
        "100uF 25V capacitor",
        "IRFZ44N",
        "Raspberry Pi Pico",
        "Wire, 22 AWG, solid core",
        "Arduino Uno R3 (compatible)",
        "5mm LED (red) x5",
        "10kΩ Resistor (1/4 W, 5%)",
        "पुश बटन स्विच",
    ],
)
def test_ladders_are_nonempty_and_contain_no_junk(name):
    rungs = route_queries(None, name, name)
    assert rungs
    assert not {"red", "compatible", "22 core", "to female", "5mm x5", "1/4 w 5"} & set(rungs)
    assert all(len(q.split()) > 1 or q.kind == "model" for q in rungs)
    assert all(q.part_terms == rungs[0].part_terms for q in rungs)


def test_unicode_marks_model_spellings_synonyms_and_values():
    assert normalise("पुश बटन स्विच") == "पुश बटन स्विच"
    assert route_queries(None, "HC-SR04", "HC-SR04")[:3] == ["hc-sr04", "hcsr04", "hc sr04"]
    spec = SimpleNamespace(
        queries=["10k carbon film resistor"], synonyms=["10k resistance resistor"]
    )
    rungs = route_queries(spec, "10k resistor 1/4W", "10k resistor 1/4W")
    assert "10k resistor" in rungs
    assert rungs[-1].kind == "synonym"


SELLER = {"domain": "a.in", "enabled": True, "search": {"adapter": "woo_store_api"}}


def searcher(fetcher=None, **kwargs):
    return SellerSearch(Politeness(min_interval_s=0), fetcher, [SELLER], **kwargs)


def test_errors_continue_and_candidates_score_against_original_part(monkeypatch):
    calls = []

    def adapter(fetch, seller, query, limit):
        calls.append(query)
        if query == "broken resistor":
            raise ValueError("bad JSON")
        return [
            Candidate("https://a.in/p/1", "a.in", "female cable"),
            Candidate("https://a.in/p/2", "a.in", "jumper wires male to female"),
        ]

    monkeypatch.setitem(ADAPTERS, "woo_store_api", adapter)
    rungs = [
        Rung(q, "spec", "jumper wires male to female") for q in ["broken resistor", "female wire"]
    ]
    result = searcher().search(rungs)
    assert calls == ["broken resistor", "female wire"]
    assert result.candidates[0].url.endswith("/2")
    assert result.candidates[0].score > result.candidates[1].score
    assert "bad JSON" in result.diagnostics[0].detail


def test_woo_model_rung_first_and_accessory_demotion(monkeypatch):
    calls = []

    def adapter(fetch, seller, query, limit):
        calls.append(query)
        return [
            Candidate("https://a.in/p/1", "a.in", "Bracket for NEMA17 stepper"),
            Candidate("https://a.in/p/2", "a.in", "NEMA17 stepper"),
        ]

    monkeypatch.setitem(ADAPTERS, "woo_store_api", adapter)
    result = searcher().search(
        [Rung("stepper motor", "spec", "NEMA17 stepper"), Rung("nema17", "model", "NEMA17 stepper")]
    )
    assert calls == ["nema17"]
    assert result.candidates[0].url.endswith("/2")
    assert result.candidates[1].score == 0


def test_deadline_keeps_partial_results_and_stops_next_queries(monkeypatch):
    release, entered = threading.Event(), threading.Event()
    calls = []

    def adapter(fetch, seller, query, limit):
        calls.append(query)
        if len(calls) == 1:
            return [Candidate("https://a.in/p/1", "a.in", "unrelated")]
        entered.set()
        release.wait(2)
        return []

    monkeypatch.setitem(ADAPTERS, "woo_store_api", adapter)
    try:
        result = searcher(deadline_s=0.1).search(["first wire", "second wire", "third wire"])
        assert entered.is_set()
        assert result.diagnostics[0].status == "timeout_partial"
        assert len(result.candidates) == 1
        assert calls == ["first wire", "second wire"]
    finally:
        release.set()


class Fetcher:
    def __init__(self, bodies):
        self.bodies, self.calls = bodies, []

    def get(self, url, **kwargs):
        self.calls.append(url)
        body = self.bodies[min(len(self.calls) - 1, len(self.bodies) - 1)]
        return Page(url, 200, {"content-type": "application/json"}, body)


def test_invalid_response_not_cached_but_valid_empty_is_cached():
    fetcher = Fetcher([b"invalid", b"[]"])
    search = searcher(fetcher)
    search.search(["10kohm resistor"])
    search.search(["10kohm resistor"])
    search.search(["10kohm resistor"])
    assert len(fetcher.calls) == 2


def test_exact_request_urls_do_not_collide():
    fetcher = Fetcher([json.dumps([]).encode()])
    search = searcher(fetcher)
    search.search(["10kohm resistor", "10k resistor"])
    assert len(fetcher.calls) == 2
    assert fetcher.calls[0] != fetcher.calls[1]
