"""Labelled evaluation against trimmed real Indian seller pages (fetched 2026-10-05).

Fixtures keep only JSON-LD, og/twitter meta tags and spec tables. Prices inside them are
historical snapshots used to exercise parsing; they are never current or verified prices.
See backend/infra/seller-page-evaluation.md for the findings.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from bharat_sourcer.sourcing.fetch import Page
from bharat_sourcer.sourcing.listings import page_images, title_matches, variant_url, verify_page
from bharat_sourcer.sourcing.specs import label_unit, parse_value

FIXTURES = Path(__file__).parent / "fixtures" / "seller_pages"
HTML = {"content-type": "text/html; charset=utf-8"}


@dataclass
class Case:
    fixture: str
    query: str
    verifies: bool
    reason: str
    image: str | None = None
    specs: dict = field(default_factory=dict)
    via_variant: bool = False
    stock: str | None = None
    # Parsing check only: the price the archived JSON-LD declared, not a current price.
    snapshot_price: str | None = None


OLED_OFF = "Title does not state the requested SSD1306 controller; title gate rejects"
CASES = [
    Case(
        "robocraze_oled_096.html",
        "0.96 inch OLED display",
        True,
        "Single Product/Offer in INR; JSON-LD images are placeholders, og:image used",
        image="https://robocraze.com/cdn/shop/files/0.96_Inch_OLED_Display_Module_SPI_I2C_4pin_Blue_Color.png",
        # "Driving Voltage: 3.3-5V" is deliberately not read as supply (ambiguous label).
        specs={"family": "oled", "interface": "i2c", "resolution": "128x64"},
        stock="out_of_stock",
        snapshot_price="172.00",
    ),
    Case("robocraze_oled_096.html", "SSD1306 OLED", False, OLED_OFF),
    Case(
        "robocraze_resistor_10k.html",
        "10k resistor",
        True,
        "Single Product/Offer in INR",
        image="https://robocraze.com/cdn/shop/products/10k_ressitor_10.jpg",
        stock="out_of_stock",
        snapshot_price="13.00",
    ),
    Case(
        "robocraze_pro_micro.html",
        "Pro Micro",
        True,
        "Single Product/Offer in INR",
        # Seller-declared og:image is a real photo but shows a Pro Mini board, not a Pro
        # Micro. It cannot be detected from metadata; images stay "visual only".
        image="https://robocraze.com/cdn/shop/products/Resistor220390Ohm_4.png",
        specs={"family": "pro_micro", "controller": "atmega32u4"},
        stock="in_stock",
        snapshot_price="419.00",
    ),
    Case(
        "robocraze_esp32_devkit.html",
        "ESP32 development board",
        True,
        "Single Product/Offer in INR",
        image="https://robocraze.com/cdn/shop/files/ESP32_Development_Board_CP2102",
        stock="out_of_stock",
    ),
    Case(
        "robocraze_led_5mm.html",
        "5mm LED",
        True,
        "Single Product/Offer in INR",
        image="https://robocraze.com/cdn/shop/products/1_3ea59085-69fc-430b-91e5-b3b6caaf1e9c.jpg",
        stock="in_stock",
    ),
    Case(
        "robocraze_push_button.html",
        "push button",
        True,
        "Single Product/Offer in INR",
        image="https://robocraze.com/cdn/shop/products/1_18189d6c-ade8-4648-a78c-06c41db7246f.png",
        stock="out_of_stock",
    ),
    Case(
        "quartz_oled_ssd1306.html",
        "0.96 inch OLED display",
        True,
        "Offer URL is the ?variant= URL; verified after the same-path variant fetch",
        image="https://quartzcomponents.com/cdn/shop/files/OLED-Display-0.96-Inch-I2C-Interface-4-Pin-Blue-SSD1306_grande.jpg",
        specs={"family": "oled", "controller": "ssd1306", "interface": "i2c"},
        via_variant=True,
        stock="in_stock",
        snapshot_price="144.00",
    ),
    Case(
        "quartz_oled_ssd1306.html",
        "SSD1306 OLED",
        True,
        "Title states SSD1306; verified via variant",
        image="https://quartzcomponents.com/cdn/shop/files/OLED-Display",
        specs={"family": "oled", "controller": "ssd1306", "interface": "i2c"},
        via_variant=True,
    ),
    Case(
        "quartz_ttp223.html",
        "TTP223 touch sensor",
        True,
        "Verified via variant",
        image="https://quartzcomponents.com/cdn/shop/products/TTP223-1-Channel-Capacitive-Touch-Sensor_grande.jpg",
        specs={"family": "ttp223", "controller": "ttp223"},
        via_variant=True,
        stock="in_stock",
    ),
    Case(
        "quartz_555_timer.html",
        "555 timer IC",
        True,
        "Verified via variant",
        image="https://quartzcomponents.com/cdn/shop/products/555-Timer-IC_",
        via_variant=True,
        snapshot_price="8.00",
    ),
    Case(
        "quartz_ldr.html",
        "LDR",
        True,
        "Verified via variant",
        image="https://quartzcomponents.com/cdn/shop/files/LDR-sensor-5mm_grande.jpg",
        via_variant=True,
    ),
    Case(
        "rytronics_oled_096.html",
        "0.96 inch OLED display",
        True,
        "Single Product/Offer in INR; ImageObject image",
        image="https://www.rytronics.in/wp-content/uploads/2021/10/OLED-.96-display-front-on.jpg",
        specs={"family": "oled", "interface": "i2c"},
        stock="in_stock",
        snapshot_price="199.00",
    ),
    Case(
        "compoindia_oled_7pin.html",
        "0.96 inch OLED display",
        True,
        'Title writes 0.96″ (fixed: inch notation normalised); "SPI/I2C" leaves interface unknown',
        image="https://compoindia.com/wp-content/uploads/2021/06/disp.jpg",
        specs={
            "family": "oled",
            "controller": "ssd1306",
            "resolution": "128x64",
            # "Operating Voltage (VDC): 3.3 ~ 5" (fixed: unit stated in the label).
            "supply_min_v": 3.3,
            "supply_max_v": 5.0,
        },
        stock="out_of_stock",
        snapshot_price="249.18",
    ),
    Case(
        "compoindia_ttp223.html",
        "TTP223 touch sensor",
        True,
        "Offer list with one Offer",
        image="https://compoindia.com/wp-content/uploads/2021/06/ttp223.jpg",
        specs={"family": "ttp223", "controller": "ttp223"},
        stock="in_stock",
    ),
    Case(
        "flyrobo_oled_096.html",
        "0.96 inch OLED display",
        True,
        "Single Product/Offer in INR",
        image="https://www.flyrobo.in/image/cache/wp/gj/OLED/oled-0.96-i2c-128-x-64-display-module-1000x1000.webp",
        specs={
            "family": "oled",
            "controller": "ssd1306",
            "interface": "i2c",
            "resolution": "128x64",
            "supply_min_v": 3.3,
            "supply_max_v": 5.0,
        },
        stock="in_stock",
        snapshot_price="215.00",
    ),
    Case("flyrobo_oled_096.html", "SSD1306 OLED", False, OLED_OFF + " (only the spec table does)"),
    Case(
        "evelta_qwiic_oled_091.html",
        "0.91 inch OLED",
        True,
        'Title writes "0.91 in." (fixed: inch notation normalised)',
        image="https://cdn11.bigcommerce.com/s-3fd3md1ghs/images/stencil/1280x1280/products/35485/20079/LCD-24606-1__93591.1712123271.jpg",
        specs={"family": "oled", "resolution": "128x32"},
        stock="in_stock",
        snapshot_price="1344.02",
    ),
    Case(
        "electronicscomp_oled_096.html",
        "0.96 inch OLED display",
        False,
        "No Product JSON-LD; the prose 'MRP Rs. ...' table row is never used as a price",
    ),
    Case(
        "electronicscomp_ttp223.html",
        "TTP223 touch sensor",
        False,
        "No Product JSON-LD; the prose 'MRP Rs. ...' table row is never used as a price",
    ),
]


def source_url(fixture: str) -> str:
    head = (FIXTURES / fixture).read_text(encoding="utf-8")[:400]
    return re.search(r"Source: (\S+)", head).group(1)


def load(fixture: str, url: str | None = None) -> Page:
    return Page(url or source_url(fixture), 200, HTML, (FIXTURES / fixture).read_bytes())


def verify_with_variant(page: Page, query: str):
    """Mirror the sourcing service: one same-path variant fetch, then reverify."""
    offer = verify_page(page, query)
    if offer is None and (target := variant_url(page, query)):
        return verify_page(Page(target, 200, HTML, page.body), query), True
    return offer, False


@pytest.mark.parametrize("fixture", sorted(p.name for p in FIXTURES.glob("*.html")))
def test_fixtures_are_trimmed_labelled_snapshots(fixture):
    text = (FIXTURES / fixture).read_text(encoding="utf-8")
    assert len(text.encode()) < 30_000
    assert text.startswith("<!-- Source: https://")
    assert "Trimmed real page for parsing tests only" in text[:600]
    assert "never current or verified prices" in text[:600]
    assert not re.search(r"<(img|iframe|form|link)\b", text, re.I)


def test_every_fixture_is_labelled():
    assert {c.fixture for c in CASES} == {p.name for p in FIXTURES.glob("*.html")}


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.fixture}:{c.query}")
def test_offer_verification_matches_label(case):
    offer, via_variant = verify_with_variant(load(case.fixture), case.query)
    assert (offer is not None) == case.verifies, case.reason
    if not case.verifies:
        return
    assert via_variant == case.via_variant
    assert offer.verification == "seller_structured_data"
    assert offer.seller_trust == "unverified"
    if case.stock:
        assert offer.stock == case.stock
    if case.snapshot_price:
        assert offer.price_inr == case.snapshot_price
    assert offer.specs.model_dump(exclude_none=True) == case.specs
    assert {e.field for e in offer.spec_evidence} == set(case.specs)
    assert offer.spec_conflicts == []
    if case.image:
        assert str(offer.image_url).startswith(case.image)


@pytest.mark.parametrize("case", CASES, ids=lambda c: f"{c.fixture}:{c.query}")
def test_image_extraction_matches_label(case):
    images = [str(image.url) for image in page_images(load(case.fixture), case.query)]
    if case.image is None:
        assert images == []
        return
    assert len(images) == 1 and images[0].startswith(case.image)
    assert not re.search(r"no-image|placeholder", images[0])


def test_placeholder_json_ld_images_fall_back_to_og_image():
    text = (FIXTURES / "robocraze_led_5mm.html").read_text(encoding="utf-8")
    assert "no-image-2048" in text
    offer = verify_page(load("robocraze_led_5mm.html"), "5mm LED")
    assert "no-image" not in str(offer.image_url)


def test_percent_escape_case_does_not_break_offer_url_match():
    # compoindia's offer URL uses lowercase escapes (%e2%80%b3); a fetched URL may not.
    url = source_url("compoindia_oled_7pin.html").replace("%e2%80%b3", "%E2%80%B3")
    offer = verify_page(load("compoindia_oled_7pin.html", url), "0.96 inch OLED")
    assert offer is not None and str(offer.url) == url


def test_variant_page_is_required_before_quartz_offer_verifies():
    page = load("quartz_ttp223.html")
    assert verify_page(page, "TTP223") is None
    target = variant_url(page, "TTP223")
    assert target.startswith(page.url + "?variant=")


def test_inch_notation_is_normalised_but_not_invented():
    assert title_matches('0.96" OLED', "OLED 0.96 inch module")
    assert title_matches("0.96 inch OLED", "0.96″ SPI/I2C 128×64 OLED")
    assert title_matches("0.91 inch OLED", "Qwiic OLED (0.91 in., 128x32)")
    assert not title_matches("5 inch display", "5 in 1 display kit")
    assert not title_matches("0.96 inch OLED", "0.96 OLED module")


def test_label_unit_only_permits_a_bare_numeric_range():
    assert label_unit("Operating Voltage (VDC)") == "v"
    assert label_unit("Operating Temperature (°C)") is None
    assert parse_value("supply", "3.3 ~ 5", "v") == {"supply_min_v": 3.3, "supply_max_v": 5.0}
    assert parse_value("supply", "3.3 ~ 5") == {}
    assert parse_value("supply", "12", "v") == {}
    assert parse_value("supply", "3.3 ~ 5 mA", "v") == {}
    assert parse_value("supply", "5 ~ 3.3", "v") == {}
