"""Offline parsing tests over project-page fixtures and robots.txt policies.

The Instructables JSON fixtures are trimmed copies of real responses fetched on 2026-10-05
(step prose paraphrased; see each file's `_fixture` note); the page-shell HTML is the real
server-rendered page with scripts removed; the robots.txt texts are the sites' real rules.
The Hackster page and every other inline page or policy are SYNTHETIC. Nothing here is
verified parts data, and no network or Gemini call runs.
"""

import json
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest

from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import ExtractionError, GeminiExtractor
from bharat_sourcer.project_pages import (
    document_text,
    instructables_text,
    project_page_source,
    quote_found,
    readable_text,
)
from bharat_sourcer.sourcing.fetch import USER_AGENT, Page, SafeFetcher, robots_parser

FIXTURES = Path(__file__).parent / "fixtures" / "project_pages"
JSON_TYPE = "application/json;charset=UTF-8"
HTML_TYPE = "text/html; charset=utf-8"
HACKSTER = "https://www.hackster.io/maker/synthetic-plant-monitor"

# Real robots.txt rules of both sites as served on 2026-10-05 (Hackster's bot block list,
# which names only other crawlers, is shortened to its first entry).
INSTRUCTABLES_ROBOTS = """User-agent: Mediapartners-Google*
Disallow:

User-agent: Slurp
Crawl-delay: 1

User-agent: AdsBot-Google*
Disallow:

User-agent: *
Disallow: /*.pdf$
Disallow: /*.txt$
Disallow: /*.html$
Disallow: /file/*
Disallow: /howto/*
Disallow: /image/*
"""
HACKSTER_ROBOTS = """User-Agent: *

# GraphQL API
# Block GraphQL endpoints to prevent infinite query combinations
Disallow: /api/graphql/*

# Authentication & OAuth
Disallow: /users/auth/*
Disallow: /auth/*
Disallow: /site/login*

# User Accounts & Privacy
Disallow: /users/*

# Projects - Functional Pages Only
Allow: /projects/tags
Allow: /projects/tags/*
Disallow: /projects/*

# Search
Disallow: /search*

# Embed Routes
Disallow: /*/*/embed

User-agent: OmniExplorer_Bot
Disallow: /
"""

INSTRUCTABLES_PROJECTS = {
    "arduino-weather-station": (
        "https://www.instructables.com/Arduino-Weather-Station/",
        ["WS2812B LED's (50)", "ESP2866 Arduino met WiFi verbinding", "Micro-USB kabel"],
    ),
    "arduino-obstacle-avoiding-robot": (
        "https://www.instructables.com/Arduino-Obstacle-Avoiding-Robot/",
        [
            "Dual Shaft DC Geared Motor 300 RPM (BO Motor) X 2",
            "HC-SR04 Ultrasonic Sensor Module",
            "L298N 2A Based Motor Driver Module",
            "7.4 v battery (2 x 18650 battery in series )",
        ],
    ),
    "arduino-traffic-light-controller": (
        "https://www.instructables.com/Arduino-Traffic-Light-Controller/",
        ["Inland Arduino UNO R3- $6", "Sainsmart 4 Channel Relay - $8", "9V Arduino Powersupply"],
    ),
}


def fixture_page(name, url, content_type):
    return Page(url, 200, {"content-type": content_type}, (FIXTURES / name).read_bytes())


def instructables_page(slug):
    url = project_page_source(INSTRUCTABLES_PROJECTS[slug][0]).fetch_urls[0]
    return fixture_page(f"instructables-{slug}.json", url, JSON_TYPE)


def test_fixtures_are_small_and_script_free():
    for path in FIXTURES.iterdir():
        data = path.read_bytes()
        assert len(data) < 60_000, path.name
        if path.suffix == ".json":
            assert "_fixture" in json.loads(data)
        else:
            assert data.startswith(b"<!--")


def test_instructables_html_is_an_empty_shell():
    """The real server-rendered page has no supplies or steps, only its title."""
    shell = fixture_page(
        "instructables-page-shell.html",
        "https://www.instructables.com/Arduino-Weather-Station/",
        HTML_TYPE,
    )
    assert readable_text(shell, 60_000) == "Arduino Weather Station : 4 Steps - Instructables"


@pytest.mark.parametrize("slug", sorted(INSTRUCTABLES_PROJECTS))
def test_instructables_supplies_survive_and_quotes_verify(slug):
    url, quotes = INSTRUCTABLES_PROJECTS[slug]
    source = project_page_source(url)
    assert source.url == url and source.cite_url == url
    assert source.fetch_urls == (
        "https://www.instructables.com/json-api/showInstructableModel?urlString="
        + url.split("/")[3],
    )
    text = document_text(source, instructables_page(slug), 60_000)
    assert (
        text.splitlines()[0]
        == json.loads((FIXTURES / f"instructables-{slug}.json").read_text())["title"].strip()
    )
    for quote in quotes:
        assert quote_found(quote, text), quote
    # Markup, link targets in attributes and fixture metadata never reach the text.
    assert "<" not in text and "rel=" not in text and "_fixture" not in text
    assert "Trimmed real response" not in text


def test_instructables_supplies_precede_steps_and_steps_are_numbered():
    text = instructables_text(instructables_page("arduino-weather-station"), 60_000)
    lines = text.splitlines()
    assert lines[:3] == ["Arduino Weather Station", "Supplies", "Onderdelen:"]
    assert lines.index("Supplies") < lines.index("Step 1: Design")
    assert "Step 4: Conclusie" in lines
    # Parts lists inside a step (older projects have no Supplies field) are kept too.
    traffic = instructables_text(instructables_page("arduino-traffic-light-controller"), 60_000)
    assert "Supplies" not in traffic.splitlines()
    assert "Parts List" in traffic.splitlines()


def test_instructables_budget_keeps_supplies_first():
    page = instructables_page("arduino-obstacle-avoiding-robot")
    text = instructables_text(page, 1_000)
    assert len(text) == 1_000
    assert quote_found("HC-SR04 Ultrasonic Sensor Module", text)
    assert "Step 5" not in text


@pytest.mark.parametrize(
    "body,content_type",
    [
        (b'{"error": "Sorry, we couldn\'t find that one!"}', JSON_TYPE),
        (b'{"title": "Draft", "status": "DRAFT", "steps": []}', JSON_TYPE),
        (b"not json", JSON_TYPE),
        (b"[]", JSON_TYPE),
        (b"<html><title>Loading</title></html>", HTML_TYPE),
    ],
)
def test_instructables_unusable_model_has_no_text(body, content_type):
    page = Page(
        "https://www.instructables.com/json-api/x", 200, {"content-type": content_type}, body
    )
    assert instructables_text(page, 60_000) == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instructables.com/id/Arduino-Weather-Station/",
        "http://instructables.com/Arduino-Weather-Station?x=1",
    ],
)
def test_instructables_legacy_and_bare_urls_map_to_project(url):
    source = project_page_source(url)
    assert source.url == "https://www.instructables.com/Arduino-Weather-Station/"


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instructables.com/circuits/arduino/projects/",
        "https://www.instructables.com/circuits/",
        "https://www.instructables.com/member/someone/",
        "https://www.instructables.com/json-api/",
        "https://www.instructables.com/Some/Deep/Path/",
    ],
)
def test_instructables_section_pages_are_not_projects(url):
    assert project_page_source(url) is None


def gemini(items):
    body = {
        "candidates": [
            {
                "finishReason": "STOP",
                "content": {"parts": [{"text": json.dumps({"items": items})}]},
            }
        ]
    }
    return httpx.Response(200, json=body)


class FakeFetcher:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        self.calls.append(url)
        return self.pages[url]


def test_instructables_extraction_cites_project_page_not_api():
    page = instructables_page("arduino-obstacle-avoiding-robot")
    fetcher = FakeFetcher({page.url: page})
    seen = {}

    def handle(request):
        document = json.loads(json.loads(request.content)["contents"][0]["parts"][0]["text"])
        seen.update(document)
        return gemini(
            [
                {
                    "raw_name": "HC-SR04 ultrasonic sensor",
                    "qty": None,
                    "evidence": [
                        {"quote": "HC-SR04 Ultrasonic Sensor Module", "observation": "Supplies"}
                    ],
                },
                {
                    "raw_name": "BO motor",
                    "qty": 2,
                    "evidence": [
                        {
                            "quote": "Dual Shaft DC Geared Motor 300 RPM (BO Motor) X 2",
                            "observation": "Supplies",
                        }
                    ],
                },
            ]
        )

    extractor = GeminiExtractor(
        Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret"),
        transport=httpx.MockTransport(handle),
        fetcher=fetcher,
    )
    items = extractor.extract("https://www.instructables.com/Arduino-Obstacle-Avoiding-Robot")
    url = "https://www.instructables.com/Arduino-Obstacle-Avoiding-Robot/"
    assert fetcher.calls == [page.url]
    assert seen["document_url"] == url and seen["source_kind"] == "instructables"
    assert seen["page_text"].startswith("Arduino Obstacle Avoiding Robot\nSupplies\n")
    assert [item.raw_name for item in items] == ["HC-SR04 ultrasonic sensor", "BO motor"]
    assert all(str(e.url) == url for item in items for e in item.evidence)


def hackster_text(limit=60_000):
    page = fixture_page("hackster-synthetic-plant-monitor.html", HACKSTER, HTML_TYPE)
    return document_text(project_page_source(HACKSTER), page, limit)


def test_hackster_keeps_components_and_story_and_drops_chrome():
    text = hackster_text()
    for kept in [
        "Synthetic Plant Monitor",
        "Things used in this project",
        "Components and supplies",
        "Capacitive soil moisture sensor v1.2",
        "Single-channel 5V relay module",
        "Hand tools and fabrication machines",
        "Story",
        "Connect the sensor output to analog pin A0",
        "plant_monitor.ino",
        "Schematics",
    ]:
        assert kept in text, kept
    for dropped in [
        "NAV-ONLY",
        "SYNTHETIC-BANNER",
        "SCRIPT-ONLY",
        "Respect project",
        "CREDITS-ONLY",
        "COMMENT-ONLY",
        "Arduino Mega",
        "RELATED-ONLY",
        "ASIDE-ONLY",
        "FOOTER-ONLY",
    ]:
        assert dropped not in text, dropped
    # Table cells become separate lines; whitespace-normalised quotes still match a row.
    assert quote_found("Capacitive soil moisture sensor v1.2 ×1", text)
    assert quote_found("Jumper wires (generic)", text)
    assert text.index("Components and supplies") < text.index("Story")


def test_hackster_components_survive_a_tight_budget():
    text = hackster_text(limit=400)
    assert quote_found("5V mini submersible water pump", text)


def test_boilerplate_heading_drops_only_its_section():
    html = (
        "<h2>Supplies</h2><p>2x SG90 servo</p><h3>Comments (4)</h3><p>COMMENT</p>"
        "<h4>Reply</h4><p>NESTED REPLY</p><h2>Step 2: Wire it</h2><p>Use 22 AWG wire</p>"
        "<h2>You might also like</h2><p>RELATED</p><div hidden>HIDDEN</div>"
        '<div role="navigation"><div>NAVROLE</div></div><p>tail</p>'
        '<div id="comments"><div>IDCOMMENT</div></div>'
    )
    text = readable_text(Page(HACKSTER, 200, {"content-type": HTML_TYPE}, html.encode()), 9_999)
    assert text.splitlines() == ["Supplies", "2x SG90 servo", "Step 2: Wire it", "Use 22 AWG wire"]
    shown = "<h2>Comments on sourcing</h2><p>kept</p><div><div>nested</div> after</div>"
    text = readable_text(Page(HACKSTER, 200, {"content-type": HTML_TYPE}, shown.encode()), 999)
    assert text.splitlines() == ["Comments on sourcing", "kept", "nested", "after"]


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instructables.com/Arduino-Weather-Station/",
        "https://www.instructables.com/Arduino-Obstacle-Avoiding-Robot/",
        "https://www.instructables.com/Arduino-Traffic-Light-Controller/",
        "https://www.instructables.com/json-api/showInstructableModel?urlString=Arduino-Weather-Station",
    ],
)
def test_real_instructables_robots_allow_project_data(url):
    parser = robots_parser(INSTRUCTABLES_ROBOTS)
    assert parser.can_fetch(USER_AGENT, url)
    assert parser.crawl_delay(USER_AGENT) is None and parser.request_rate(USER_AGENT) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instructables.com/file/FOO/BAR/plan.pdf",
        "https://www.instructables.com/Arduino-Weather-Station/notes.txt",
        "https://www.instructables.com/howto/servo",
        "https://www.instructables.com/json-api/showInstructableModel?urlString=notes.txt",
    ],
)
def test_real_instructables_robots_wildcards_are_enforced(url):
    assert not robots_parser(INSTRUCTABLES_ROBOTS).can_fetch(USER_AGENT, url)


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://www.hackster.io/techtalkies1/real-life-color-picker-8e72e4", True),
        ("https://www.hackster.io/adam-taylor/routescope-daad56", True),
        (
            "https://www.hackster.io/cameroncoward/"
            "termi3-the-question-answering-typewriter-is-back-79b49c",
            True,
        ),
        ("https://www.hackster.io/projects/tags/arduino", True),
        ("https://www.hackster.io/projects/new", False),
        ("https://www.hackster.io/users/sign_in", False),
        ("https://www.hackster.io/search?q=esp32", False),
        ("https://www.hackster.io/maker/project/embed", False),
    ],
)
def test_real_hackster_robots_group_survives_comments(url, allowed):
    """The stdlib parser alone drops Hackster's `*` group at its blank/comment lines."""
    parser = robots_parser(HACKSTER_ROBOTS)
    assert parser.can_fetch(USER_AGENT, url) is allowed
    assert parser.crawl_delay(USER_AGENT) is None and parser.request_rate(USER_AGENT) is None


def test_robots_longest_match_wins_and_allow_breaks_ties():
    policy = "User-agent: *\nDisallow: /a\nAllow: /a/b\nDisallow: /c\nAllow: /c\n"
    parser = robots_parser(policy)
    assert not parser.can_fetch(USER_AGENT, "https://x.example/a/c")
    assert parser.can_fetch(USER_AGENT, "https://x.example/a/b/c")
    assert parser.can_fetch(USER_AGENT, "https://x.example/c")


@pytest.mark.parametrize(
    "policy,url",
    [
        (
            INSTRUCTABLES_ROBOTS,
            "https://www.instructables.com/json-api/showInstructableModel?urlString=X",
        ),
        (HACKSTER_ROBOTS, HACKSTER),
    ],
)
def test_safe_fetcher_allows_real_policies(policy, url):
    fetcher = SafeFetcher()
    robots = Page(url, 200, {}, policy.encode())
    with patch.object(fetcher, "_request", return_value=robots) as request:
        assert fetcher._allowed(url)
        assert request.call_count == 1


def test_hackster_cloudflare_refusal_is_reported_clearly():
    """Hackster answered project pages with HTTP 403 from the dev sandbox; say so plainly."""
    blocked = Page(
        HACKSTER, 403, {"content-type": HTML_TYPE}, b"<title>Attention Required!</title>"
    )
    extractor = GeminiExtractor(
        Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret"),
        transport=httpx.MockTransport(lambda request: pytest.fail("Gemini must not be called")),
        fetcher=FakeFetcher({HACKSTER: blocked}),
    )
    with pytest.raises(ExtractionError) as captured:
        extractor.extract(HACKSTER)
    assert captured.value.code == "SOURCE_UNAVAILABLE"
    assert "refused automated access" in captured.value.message
    assert "HTTP 403" in captured.value.message
