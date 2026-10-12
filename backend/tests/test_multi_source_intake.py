"""Multi-source intake tests: Adafruit/blog pages, code evidence, fusion, look-alikes, confidence.

The Adafruit Markdown and blog HTML fixtures are trimmed copies of real public pages fetched
once on 2026-10-06 (see each file's header comment). Every repository file, Gemini response
and BOM line below is SYNTHETIC test data: none of it is verified parts, quantities,
compatibility or evidence. No network or Gemini call runs: pages come from a fake fetcher
and Gemini responses from httpx.MockTransport.
"""

import json
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from bharat_sourcer.code_evidence import candidate_files, linked_files, read_code, scan
from bharat_sourcer.config import Settings
from bharat_sourcer.extraction import (
    ExtractionError,
    ExtractionResult,
    GeminiExtractor,
    generation_schema,
    supported_source,
)
from bharat_sourcer.fusion import compact, fuse, group_members, model_codes
from bharat_sourcer.intake import validate_sources
from bharat_sourcer.jobs import JobError, JobService
from bharat_sourcer.project_pages import document_text, project_page_source, quote_found
from bharat_sourcer.schemas import (
    BomItem,
    ConfirmJob,
    CreateJob,
    Evidence,
    Job,
    UpdateLine,
)
from bharat_sourcer.sourcing.fetch import FetchError, Page

FIXTURES = Path(__file__).parent / "fixtures" / "project_pages"
VIDEO = "https://www.youtube.com/watch?v=abcdefghijk"
REPO = "https://github.com/maker/synthetic-station"
RAW = "https://raw.githubusercontent.com/maker/synthetic-station/HEAD/"
ADAFRUIT = "https://learn.adafruit.com/magtag-weather"
BLOG = "https://randomnerdtutorials.com/esp32-web-server-with-bme280-mini-weather-station/"


def page(url, body, status=200, content_type="text/plain; charset=utf-8"):
    return Page(url, status, {"content-type": content_type}, body.encode())


class FakeFetcher:
    """Synthetic stand-in for SafeFetcher: serves canned documents and records calls."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def get(self, url, *, robots=True, max_bytes=2_000_000):
        self.calls.append(url)
        value = self.responses.get(url, page(url, "", 404))
        if isinstance(value, Exception):
            raise value
        return value


def gemini(body):
    text = json.dumps(body)
    return httpx.Response(
        200,
        json={"candidates": [{"finishReason": "STOP", "content": {"parts": [{"text": text}]}}]},
    )


def extractor(fetcher, handler):
    return GeminiExtractor(
        Settings(_env_file=None, demo_mode=False, gemini_api_key="test-secret"),
        transport=httpx.MockTransport(handler),
        fetcher=fetcher,
    )


def video_ev(timestamp="00:10"):
    return Evidence(timestamp=timestamp, observation="Synthetic video evidence")


def page_ev(quote, url="https://www.instructables.com/Synthetic/"):
    return Evidence(source="project_page", observation="Synthetic quote", quote=quote, url=url)


def code_ev(line=3, quote="#include <Adafruit_BME280.h>"):
    return Evidence(
        source="code",
        observation="Synthetic include",
        quote=quote,
        url=f"{REPO}/blob/HEAD/src/main.cpp#L{line}",
        file="src/main.cpp",
        line=line,
    )


def item(name, evidence, qty=1, qty_source="stated", **extra):
    return BomItem(
        line_id="L01", raw_name=name, qty=qty, qty_source=qty_source, evidence=evidence, **extra
    )


# --- New page sources ------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        ADAFRUIT,
        "https://learn.adafruit.com/magtag-weather/overview",
        "https://learn.adafruit.com/magtag-weather.md?view=all",
    ],
)
def test_adafruit_guide_urls_use_markdown_view(url):
    source = project_page_source(url)
    assert source.kind == "adafruit" and source.url == ADAFRUIT
    assert source.fetch_urls == (ADAFRUIT + ".md?view=all",)
    assert source.cite_url == ADAFRUIT + "?view=all"
    assert supported_source(url) == ("project_page", ADAFRUIT)


@pytest.mark.parametrize(
    "url",
    [
        "https://learn.adafruit.com/",
        "https://learn.adafruit.com/products/4800/guides",
        "https://learn.adafruit.com/guides/latest",
        "https://randomnerdtutorials.com/",
        "https://randomnerdtutorials.com.evil.test/post/",
    ],
)
def test_unlisted_or_non_article_pages_stay_unsupported(url):
    assert project_page_source(url) is None
    with pytest.raises(ExtractionError) as captured:
        supported_source(url)
    assert captured.value.code == "UNSUPPORTED_URL"
    assert "Adafruit Learn" in captured.value.message


def test_tutorial_blog_url_is_canonicalised():
    source = project_page_source("http://www.randomnerdtutorials.com/esp32-x/?utm_source=a#c")
    assert source.kind == "blog"
    assert source.url == "https://randomnerdtutorials.com/esp32-x/"
    assert "www.randomnerdtutorials.com" in source.hosts


def test_adafruit_fixture_text_drops_images_links_and_shop_chrome():
    source = project_page_source(ADAFRUIT)
    body = (FIXTURES / "adafruit-magtag-weather.md").read_text(encoding="utf-8")
    text = document_text(
        source, page(source.fetch_urls[0], body, content_type="text/markdown"), 60000
    )
    assert '### Adafruit MagTag - 2.9" Grayscale E-Ink WiFi Display' in text
    assert "Lithium Ion Polymer Battery with Short Cable - 3.7V 420mAh" in text
    for chrome in ["Buy Now", "Out of Stock", "cdn-shop.adafruit.com", "Trimmed copy", "](http"]:
        assert chrome not in text


def test_blog_fixture_reads_only_the_article_body():
    source = project_page_source(BLOG)
    body = (FIXTURES / "blog-rnt-esp32-bme280-web-server.html").read_text(encoding="utf-8")
    text = document_text(source, page(BLOG, body, content_type="text/html; charset=UTF-8"), 60000)
    assert "ESP32 DOIT DEVKIT V1 Board" in text and "BME280 sensor module" in text
    assert "#include <Adafruit_BME280.h>" in text
    for chrome in ["RASPBERRY PI", "What to Read Next", "Thermostat", "overkill", "Copyright"]:
        assert chrome not in text


def test_blog_without_article_markup_falls_back_to_page_text():
    source = project_page_source(BLOG)
    markup = "<html><body><nav>MENU</nav><p>Synthetic: 1x HC-SR04 sensor</p></body></html>"
    text = document_text(source, page(BLOG, markup, content_type="text/html"), 1000)
    assert text == "Synthetic: 1x HC-SR04 sensor"


def test_adafruit_extraction_checks_quotes_and_cites_all_pages_view():
    body = (FIXTURES / "adafruit-magtag-weather.md").read_text(encoding="utf-8")
    fetch_url = ADAFRUIT + ".md?view=all"
    fetcher = FakeFetcher({fetch_url: page(fetch_url, body, content_type="text/markdown")})
    magtag = {
        "raw_name": "Adafruit MagTag",
        "qty": 1,
        "lookalikes": ["Adafruit MagTag", "MagTag 2025 Edition"],
        "evidence": [
            {"quote": 'Adafruit MagTag - 2.9" Grayscale E-Ink WiFi Display', "observation": "x"}
        ],
    }
    result = extractor(fetcher, lambda request: gemini({"items": [magtag]})).extract(ADAFRUIT)
    assert fetcher.calls == [fetch_url]
    evidence = result.items[0].evidence[0]
    assert str(evidence.url) == ADAFRUIT + "?view=all"
    # The model's own name is not a look-alike; other names are kept as "ai" warnings.
    assert [(x.name, x.origin) for x in result.items[0].lookalikes] == [
        ("MagTag 2025 Edition", "ai")
    ]
    assert result.code_items == []


def test_generation_schema_and_prompts_ask_for_lookalikes():
    from bharat_sourcer.extraction import PAGE_PROMPT, PROMPT, ExtractedPageBom

    for model in (None, ExtractedPageBom):
        schema = generation_schema(model) if model else generation_schema()
        assert "lookalikes" in schema["properties"]["items"]["items"]["properties"]
    assert "lookalikes" in PROMPT and "lookalikes" in PAGE_PROMPT


# --- Code evidence ---------------------------------------------------------------------

SKETCH = """// Synthetic sketch
#include <Wire.h>
#include <Adafruit_BME280.h>
/* #include <Adafruit_SSD1306.h>
#include <NewPing.h> */
// #include <Servo.h>
#include "SH1106Wire.h"
"""
PLATFORMIO = """; Synthetic platformio.ini
[env:esp32dev]
platform = espressif32
board = esp32dev
lib_deps =
    adafruit/Adafruit BME280 Library@^2.2.2
    https://github.com/someone/Unknown-Library.git
    bblanchon/ArduinoJson
monitor_speed = 115200
"""


def test_scan_maps_includes_and_skips_comments():
    hints = scan("src/main.cpp", SKETCH)
    assert [(part, line) for part, line, _, _ in hints] == [
        ("BME280 sensor module", 3),
        ("SH1106 OLED display", 7),
    ]


def test_scan_platformio_board_and_lib_deps():
    hints = scan("platformio.ini", PLATFORMIO)
    assert [(part, line) for part, line, _, _ in hints] == [
        ("ESP32 development board", 4),
        ("BME280 sensor module", 6),
    ]


def test_scan_python_and_requirements_and_library_json():
    code = "import board\nimport adafruit_bmp280, neopixel\nfrom adafruit_dht import DHT22\n"
    assert [(p, n) for p, n, _, _ in scan("code.py", code)] == [
        ("BMP280 sensor module", 2),
        ("Addressable RGB LEDs (WS2812B / NeoPixel)", 2),
        ("DHT temperature and humidity sensor (DHT11 or DHT22)", 3),
    ]
    requirements = "# deps\nadafruit-circuitpython-ssd1306==2.12\nrequests\n"
    assert [p for p, _, _, _ in scan("requirements.txt", requirements)] == ["SSD1306 OLED display"]
    library = json.dumps({"dependencies": [{"name": "Adafruit SGP30 Sensor"}]}, indent=1)
    assert [p for p, _, _, _ in scan("library.json", library)] == ["SGP30 air quality sensor"]
    assert scan("library.json", "{not json") == []


def test_readme_links_are_bounded_and_path_safe():
    readme = (
        "See [the sketch](firmware/station.ino), [docs](docs/guide.md), "
        "[escape](../../etc/passwd.py), [anchor](#wiring) and "
        "https://github.com/maker/synthetic-station/blob/main/src/sensors.h for pins."
    )
    assert linked_files("maker", "synthetic-station", readme) == [
        ("main", "src/sensors.h"),
        ("HEAD", "firmware/station.ino"),
    ]
    files = candidate_files("maker", "synthetic-station", readme * 3)
    assert files[0] == ("HEAD", "platformio.ini") and len(files) <= 8


def test_read_code_cites_file_line_and_skips_failures():
    fetcher = FakeFetcher(
        {
            RAW + "platformio.ini": page(RAW + "platformio.ini", PLATFORMIO),
            RAW + "src/main.cpp": page(RAW + "src/main.cpp", SKETCH),
            RAW + "code.py": FetchError("Robots policy prevents verification"),
        }
    )
    items = read_code(fetcher, REPO, "# Synthetic README")
    assert [x.raw_name for x in items] == [
        "ESP32 development board",
        "BME280 sensor module",
        "SH1106 OLED display",
    ]
    bme = items[1]
    assert [(e.file, e.line) for e in bme.evidence] == [("platformio.ini", 6), ("src/main.cpp", 3)]
    assert str(bme.evidence[1].url) == f"{REPO}/blob/HEAD/src/main.cpp#L3"
    assert bme.evidence[1].quote == "#include <Adafruit_BME280.h>"
    assert (bme.qty, bme.qty_source) == (1, "inferred")
    assert all(url.startswith(RAW) for url in fetcher.calls) and len(fetcher.calls) <= 8


def test_code_evidence_validation():
    assert code_ev().source == "code"
    for bad in [
        {"source": "code", "observation": "x", "quote": "abc", "url": REPO, "file": "a.ino"},
        {"timestamp": "00:01", "observation": "x", "file": "a.ino", "line": 1},
        {"source": "project_page", "observation": "x", "quote": "abc", "url": REPO, "line": 2},
    ]:
        with pytest.raises(ValidationError):
            Evidence.model_validate(bad)


def test_github_extraction_returns_readme_parts_and_code_hints():
    readme = "# Synthetic station\n\n## Parts\n- BMP280 sensor\n- 0.96 inch OLED\n"
    fetcher = FakeFetcher(
        {
            RAW + "README.md": page(RAW + "README.md", readme),
            RAW + "src/main.cpp": page(RAW + "src/main.cpp", SKETCH),
        }
    )
    sensor = {
        "raw_name": "BMP280 sensor",
        "qty": 1,
        "evidence": [{"quote": "BMP280 sensor", "observation": "Parts list"}],
    }
    result = extractor(fetcher, lambda request: gemini({"items": [sensor]})).extract(REPO)
    assert [x.raw_name for x in result.items] == ["BMP280 sensor"]
    assert [x.raw_name for x in result.code_items] == [
        "BME280 sensor module",
        "SH1106 OLED display",
    ]
    fused = fuse([result.items, result.code_items])
    # README says BMP280 while the code includes Adafruit_BME280.h: one line, one conflict.
    assert [x.raw_name for x in fused] == ["BMP280 sensor", "SH1106 OLED display"]
    conflict = fused[0].conflicts[0]
    assert conflict.kind == "identity_mismatch"
    assert [(v.value, v.source, v.locator) for v in conflict.values] == [
        ("BMP280 sensor", "project_page", "BMP280 sensor"),
        ("BME280 sensor module", "code", "src/main.cpp:3"),
    ]
    assert fused[0].confidence == "check"
    # Code alone pins the SH1106 member of the OLED group, so the warning stays but it is verified.
    assert fused[1].confidence == "verified"
    assert [x.name for x in fused[1].lookalikes] == ["SSD1306"]


def test_github_readme_without_quoted_parts_still_returns_code_hints():
    fetcher = FakeFetcher(
        {
            RAW + "README.md": page(RAW + "README.md", "# Synthetic"),
            RAW + "platformio.ini": page(RAW + "platformio.ini", PLATFORMIO),
        }
    )
    result = extractor(fetcher, lambda request: gemini({"items": []})).extract(REPO)
    assert result.items == [] and len(result.code_items) == 2


TREE = "https://api.github.com/repos/maker/synthetic-station/git/trees/HEAD?recursive=1"
DESK_SKETCH = """// Synthetic sketch
#include <Wire.h>
#include <Adafruit_SH110X.h>
#define TOUCH_PIN 7
"""


def tree(*entries):
    """A synthetic GitHub git/trees response: (path, size) blobs."""
    body = {"tree": [{"path": p, "type": "blob", "size": size} for p, size in entries]}
    return page(TREE, json.dumps(body), content_type="application/json")


def test_github_without_readme_reads_code_from_the_repository_tree():
    fetcher = FakeFetcher(
        {
            TREE: tree(
                ("photo.jpeg", 1000),
                ("deskbuddy.ino", 3000),
                ("libraries/Other/Other.cpp", 100),  # vendored: skipped
                ("huge.cpp", 900_000),  # over the size limit: skipped
            ),
            RAW + "deskbuddy.ino": page(RAW + "deskbuddy.ino", DESK_SKETCH),
        }
    )

    def no_model(request):
        raise AssertionError("No README means no page model call")

    result = extractor(fetcher, no_model).extract(REPO)
    assert result.items == []
    assert [x.raw_name for x in result.code_items] == ["SH1106 OLED display"]
    evidence = result.code_items[0].evidence[0]
    assert (evidence.file, evidence.line) == ("deskbuddy.ino", 3)
    raw_calls = [url for url in fetcher.calls if url.startswith(RAW)]
    readmes = [RAW + name for name in ("README.md", "readme.md", "README.rst", "README")]
    assert raw_calls == [*readmes, RAW + "deskbuddy.ino"]
    assert TREE in fetcher.calls


def test_github_without_readme_or_code_reports_a_clear_message():
    fetcher = FakeFetcher({TREE: tree(("photo.jpeg", 1000), ("case.stl", 2000))})
    with pytest.raises(ExtractionError) as captured:
        extractor(fetcher, lambda request: gemini({"items": []})).extract(REPO)
    assert captured.value.code == "SOURCE_UNAVAILABLE"
    assert "no README and no code files" in captured.value.message


def test_github_tree_is_a_fallback_when_conventional_guesses_miss():
    fetcher = FakeFetcher(
        {
            RAW + "README.md": page(RAW + "README.md", "# Synthetic"),
            TREE: tree(("firmware/station_v2.ino", 500)),
            RAW + "firmware/station_v2.ino": page(RAW + "firmware/station_v2.ino", SKETCH),
        }
    )
    result = extractor(fetcher, lambda request: gemini({"items": []})).extract(REPO)
    assert [x.raw_name for x in result.code_items] == [
        "BME280 sensor module",
        "SH1106 OLED display",
    ]
    # The tree is not read when a conventional file already gave code.
    fetcher = FakeFetcher({RAW + "src/main.cpp": page(RAW + "src/main.cpp", SKETCH)})
    read_code(fetcher, REPO, "# Synthetic README")
    assert TREE not in fetcher.calls


def test_github_tree_failures_fall_back_to_conventional_guesses():
    for response in (FetchError("Robots policy prevents verification"), page(TREE, "{bad")):
        fetcher = FakeFetcher(
            {TREE: response, RAW + "src/main.cpp": page(RAW + "src/main.cpp", SKETCH)}
        )
        items = read_code(fetcher, REPO, "")
        assert [x.raw_name for x in items] == ["BME280 sensor module", "SH1106 OLED display"]


def test_intake_reports_readme_less_github_source_as_read():
    from bharat_sourcer.intake import extract_sources

    class Extractor:
        def extract(self, url):
            if url == REPO:
                return ExtractionResult(
                    items=[], code_items=read_code(FakeFetcher(CODE_ONLY), REPO, "")
                )
            return ExtractionResult(
                items=[item("1.3 inch I2C OLED display module (SH1106)", [video_ev()])]
            )

    CODE_ONLY = {
        TREE: tree(("deskbuddy.ino", 3000)),
        RAW + "deskbuddy.ino": page(RAW + "deskbuddy.ino", DESK_SKETCH),
    }
    result = extract_sources(Extractor(), [VIDEO, REPO])
    github = result.sources[1]
    assert (github.status, github.item_count, github.code_item_count) == ("read", 0, 1)
    assert [x.raw_name for x in result.items] == ["1.3 inch I2C OLED display module (SH1106)"]
    assert {e.source for e in result.items[0].evidence} == {"video", "code"}


# --- Fusion, look-alikes and confidence -----------------------------------------------


def test_name_helpers():
    assert compact("AMS1117-3.3 LDO") == "ams11173 3 ldo"
    assert model_codes("ESP32-S3 DevKitC-1, 3.7V 420mAh") == {"esp32s3", "devkitc1"}
    assert group_members("ESP32 DOIT DEVKIT V1") == {"esp32_family": {"ESP32"}}
    assert group_members("ESP32-S3 board") == {"esp32_family": {"ESP32-S3"}}
    assert group_members("AMS1117 regulator") == {"ams1117": set()}
    assert group_members("HC-SR04P") == {"hcsr04": {"HC-SR04P"}}


def test_agreeing_sources_merge_into_one_verified_line():
    video = [item("L298N motor driver", [video_ev()], qty=None, qty_source="inferred")]
    page_items = [item("L298N dual H-bridge driver board", [page_ev("L298N driver board")], qty=1)]
    fused = fuse([video, page_items])
    assert len(fused) == 1
    line = fused[0]
    assert line.raw_name == "L298N motor driver"  # the primary source's name is kept
    assert [e.source for e in line.evidence] == ["video", "project_page"]
    assert (line.qty, line.qty_source) == (1, "stated")  # a stated count beats an inferred one
    assert line.conflicts == []
    assert (line.confidence, line.confidence_reason) == (
        "verified",
        "2 sources agree on this part.",
    )


def test_quantity_disagreement_is_a_conflict_not_a_choice():
    fused = fuse(
        [
            [item("N20 gear motor", [video_ev()], qty=2)],
            [item("N20 gear motors", [page_ev("4 x N20 gear motors")], qty=4)],
        ]
    )
    line = fused[0]
    assert line.qty == 2 and line.conflicts[0].kind == "qty_mismatch"
    assert [v.value for v in line.conflicts[0].values] == ["2", "4"]
    assert line.confidence == "check"


def test_generic_name_takes_part_number_and_distinct_parts_stay_apart():
    fused = fuse(
        [
            [item("Ultrasonic sensor", [video_ev()]), item("A4988 driver", [video_ev("00:20")])],
            [
                item("HC-SR04P ultrasonic sensor", [page_ev("HC-SR04P ultrasonic sensor")]),
                item("L298N driver", [page_ev("L298N driver")]),
            ],
        ]
    )
    assert [x.raw_name for x in fused] == [
        "HC-SR04P ultrasonic sensor",
        "A4988 driver",
        "L298N driver",
    ]
    assert [x.line_id for x in fused] == ["L01", "L02", "L03"]
    # HC-SR04P is a look-alike group member: two agreeing sources still cap it at likely.
    assert fused[0].confidence == "likely"
    assert fused[0].confidence_reason == (
        "Easily confused with HC-SR04; confirm the exact variant."
    )
    assert [x.name for x in fused[0].lookalikes] == ["HC-SR04"]


def test_lines_within_one_source_are_never_merged():
    fused = fuse(
        [[item("220 ohm resistor", [video_ev()]), item("220 ohm resistor", [video_ev("01:00")])]]
    )
    assert len(fused) == 2


def test_single_source_confidence_levels():
    fused = fuse(
        [
            [
                item("Breadboard", [page_ev("Breadboard")]),
                item("Jumper wires", [video_ev()]),
                item("BME280 sensor module", [page_ev("BME280 sensor module")]),
                BomItem(line_id="L09", raw_name="Synthetic added line"),
            ]
        ]
    )
    # A look-alike alone is likely (confirm the variant); no evidence stays check.
    assert [x.confidence for x in fused] == ["likely", "likely", "likely", "check"]
    assert "quote checked" in fused[0].confidence_reason
    assert "BMP280" in fused[2].confidence_reason
    assert "confirm the exact variant" in fused[2].confidence_reason
    assert fused[2].lookalikes[0].origin == "table" and fused[2].lookalikes[0].note


def test_generic_suggested_battery_folds_into_the_specific_battery():
    lipo = item("3.7V 400mAh LiPo battery (602530)", [video_ev("00:30")])
    generic = item("Rechargeable battery", [video_ev("02:10")], qty=1, qty_source="inferred")
    switch = item("Slide switch", [video_ev("00:40")], qty_source="inferred")
    fused = fuse([[lipo, generic, switch]])
    assert [x.raw_name for x in fused] == ["3.7V 400mAh LiPo battery (602530)", "Slide switch"]
    assert [x.line_id for x in fused] == ["L01", "L02"]
    assert [e.timestamp for e in fused[0].evidence] == ["00:30", "02:10"]
    assert (fused[0].qty, fused[0].qty_source) == (1, "stated")


def test_battery_lines_that_are_not_duplicates_stay_apart():
    coin = item("CR2032 coin cell", [video_ev()])
    lipo = item("3.7V LiPo battery", [video_ev("00:20")])
    generic = item("Battery", [video_ev("00:30")], qty_source="inferred")
    # Two specific batteries: the generic suggestion is ambiguous and is kept.
    assert len(fuse([[coin, lipo, generic]])) == 3
    # A stated generic line is the source's own line, not a suggestion.
    stated = item("Rechargeable battery", [video_ev("00:30")])
    assert len(fuse([[lipo, stated]])) == 2


def test_code_include_alone_is_verified():
    fused = fuse([[item("BME280 sensor module", [code_ev()], qty_source="inferred")]])
    assert fused[0].confidence == "verified"
    assert [x.name for x in fused[0].lookalikes] == ["BMP280"]


# --- Jobs ------------------------------------------------------------------------------


class SourceExtractor:
    """Synthetic extractor: canned results per URL, recording the order of calls."""

    def __init__(self, results):
        self.results = results
        self.calls = []

    def extract(self, url):
        self.calls.append(url)
        value = self.results[url]
        if isinstance(value, Exception):
            raise value
        return value


def test_create_job_sources_are_bounded_and_optional():
    assert CreateJob(url=VIDEO).sources == []
    with pytest.raises(ValidationError):
        CreateJob(url=VIDEO, sources=[REPO, ADAFRUIT, BLOG, "https://github.com/a/b"])
    old = Job.model_validate(
        {"job_id": "00000000-0000-4000-8000-000000000000", "input": {"url": VIDEO}}
    )
    assert old.source_reports == [] and old.input.sources == []


def test_validate_sources_dedupes_and_allows_one_video():
    assert validate_sources([VIDEO, "https://youtu.be/abcdefghijk", REPO + ".git"]) == [
        ("video", VIDEO, VIDEO),
        ("project_page", REPO, REPO + ".git"),
    ]
    with pytest.raises(ExtractionError) as captured:
        validate_sources([VIDEO, "https://youtu.be/bbbbbbbbbbb"])
    assert captured.value.code == "UNSUPPORTED_SOURCES"


def test_job_with_sources_fuses_and_reports_each_source():
    service = JobService(
        SourceExtractor(
            {
                VIDEO: ExtractionResult(items=[item("BMP280 sensor", [video_ev()])]),
                REPO: ExtractionResult(
                    items=[],
                    code_items=[item("BME280 sensor module", [code_ev()], qty_source="inferred")],
                ),
                BLOG: ExtractionError("SOURCE_UNAVAILABLE", "Synthetic fetch failure"),
            }
        )
    )
    job, token = service.create(CreateJob(url=VIDEO, sources=[REPO, BLOG]))
    assert job.events[0].message == "Video queued with 2 more sources."
    service.extract(job.job_id)
    snapshot = service.get(job.job_id, token)
    assert snapshot.status == "awaiting_confirmation"
    assert len(snapshot.items) == 1 and snapshot.items[0].conflicts[0].kind == "identity_mismatch"
    assert [
        (r.kind, r.role, r.status, r.item_count, r.code_item_count) for r in snapshot.source_reports
    ] == [
        ("video", "primary", "read", 1, 0),
        ("github", "additional", "read", 0, 1),
        ("blog", "additional", "failed", 0, 0),
    ]
    assert snapshot.source_reports[2].error.code == "SOURCE_UNAVAILABLE"


def test_job_fails_only_when_every_source_fails():
    service = JobService(
        SourceExtractor(
            {
                VIDEO: ExtractionError("NO_BOM", "Synthetic: nothing found"),
                REPO: ExtractionError("SOURCE_UNAVAILABLE", "Synthetic: no README"),
            }
        )
    )
    job, token = service.create(CreateJob(url=VIDEO, sources=[REPO]))
    service.extract(job.job_id)
    snapshot = service.get(job.job_id, token)
    assert snapshot.status == "failed" and snapshot.error.code == "NO_BOM"


def test_create_rejects_two_videos_and_unsupported_extra_sources():
    service = JobService(SourceExtractor({}))
    for sources, code in [
        (["https://youtu.be/bbbbbbbbbbb"], "UNSUPPORTED_SOURCES"),
        (["https://127.0.0.1/post/"], "UNSUPPORTED_URL"),
    ]:
        with pytest.raises(JobError) as captured:
            service.create(CreateJob(url=VIDEO, sources=sources))
        assert (captured.value.status, captured.value.code) == (400, code)


def test_renaming_a_line_clears_its_confidence():
    service = JobService(
        SourceExtractor({VIDEO: ExtractionResult(items=[item("Jumper wires", [video_ev()])])})
    )
    job, token = service.create(CreateJob(url=VIDEO))
    service.extract(job.job_id)
    assert service.get(job.job_id, token).items[0].confidence == "likely"
    record = service.store.get(job.job_id)
    service.edit_draft(
        record.job,
        ConfirmJob(edits=[UpdateLine(op="update", line_id="L01", raw_name="Dupont wires")]),
    )
    assert record.job.items[0].confidence is None


def test_quote_found_still_applies_to_markdown_text():
    assert quote_found("3.7V 420mAh", "Battery with Short Cable - 3.7V   420mAh")
