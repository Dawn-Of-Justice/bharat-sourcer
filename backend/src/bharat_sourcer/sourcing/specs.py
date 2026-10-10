"""Seller-published specification labels. Unknown or contradictory values stay unknown."""

import re
from html.parser import HTMLParser

from bharat_sourcer.schemas import PartSpecs

# Deliberately narrow: generic labels such as "voltage", "frequency" or "address" are
# ambiguous on real listings and are ignored rather than guessed.
LABELS = {
    "controller": {"controller", "driver ic", "controller ic", "microcontroller", "mcu"},
    "interface": {"interface", "communication interface", "interface type", "communication"},
    "logic_v": {"logic level", "logic voltage", "io voltage", "i/o voltage", "logic level voltage"},
    "supply": {
        "operating voltage",
        "supply voltage",
        "input voltage",
        "working voltage",
        "operating voltage range",
        "supply voltage range",
    },
    "clock_mhz": {"clock speed", "clock frequency", "crystal frequency", "cpu speed"},
    "resolution": {"resolution", "display resolution", "pixel resolution"},
    "i2c_address": {"i2c address", "iic address"},
}
ALIASES = {label: field for field, labels in LABELS.items() for label in labels}
VOLT = r"(\d+(?:\.\d+)?)\s*v"


def label_field(label: str) -> str | None:
    text = re.sub(r"\([^)]*\)", "", label.lower()).strip(" :\t-")
    return ALIASES.get(re.sub(r"\s+", " ", text))


# A unit stated only in the label, e.g. "Operating Voltage (VDC)": "3.3 ~ 5" (compoindia.com).
VOLT_UNITS = {"v", "vdc", "v dc", "volt", "volts"}


def label_unit(label: str) -> str | None:
    units = {u.strip().lower() for u in re.findall(r"\(([^)]*)\)", label)}
    return "v" if units and units <= VOLT_UNITS else None


def one(values: list) -> object | None:
    return values[0] if len(set(values)) == 1 else None


def parse_value(field: str, raw: object, unit: str | None = None) -> dict:
    """Return PartSpecs values for one labelled seller value, or {} when ambiguous.

    ``unit`` is a unit declared by the label itself; it only permits bare numbers when the
    whole value is a single numeric range.
    """
    text = str(raw).lower()
    if len(text) > 200:
        return {}
    found = {}
    if field == "controller":
        options = ["atmega32u4", "ssd1306", "sh1106", "ttp223"]
        found["controller"] = one([o for o in options if re.search(r"\b" + o + r"\b", text)])
    elif field == "interface":
        names = {"i2c": "i2c", "iic": "i2c", "twi": "i2c", "spi": "spi", "usb": "usb"}
        found["interface"] = one([names[n] for n in re.findall(r"\b(i2c|iic|twi|spi|usb)\b", text)])
    elif field == "logic_v":
        volts = [float(v) for v in re.findall(VOLT, text)]
        found["logic_v"] = one([v for v in volts if v in (3.3, 5.0)]) if len(volts) == 1 else None
    elif field == "supply":
        span = re.findall(VOLT.replace("\\s*v", "\\s*v?") + r"\s*(?:-|–|~|to)\s*" + VOLT, text)
        bare = r"(\d+(?:\.\d+)?)\s*v?\s*(?:-|–|~|to)\s*(\d+(?:\.\d+)?)\s*v?(?:\s*dc)?"
        if not span and unit == "v" and (match := re.fullmatch(bare, text.strip())):
            span = [match.groups()]
        if len(span) == 1:
            low, high = (float(v) for v in span[0])
            if low < high:
                found = {"supply_min_v": low, "supply_max_v": high}
    elif field == "clock_mhz":
        found["clock_mhz"] = one([int(v) for v in re.findall(r"(?<![\d.])(8|16)\s*mhz\b", text)])
    elif field == "resolution":
        found["resolution"] = one(
            ["128x" + v for v in re.findall(r"\b128\s*[x×*]\s*(32|64)\b", text)]
        )
    elif field == "i2c_address":
        found["i2c_address"] = one(re.findall(r"\b(0x3[cd])\b", text))
    found = {key: value for key, value in found.items() if value is not None}
    try:
        PartSpecs(**found)
    except ValueError:
        return {}
    return found


class SpecTables(HTMLParser):
    """Two-cell table rows and dt/dd pairs, bounded; scripts and styles are ignored."""

    def __init__(self, max_rows: int = 300):
        super().__init__(convert_charrefs=True)
        self.rows: list[tuple[str, str]] = []
        self.max_rows = max_rows
        self.cells: list[str] | None = None
        self.text: list[str] | None = None
        self.term: str | None = None
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.skip += 1
        elif tag == "tr":
            self.cells = []
        elif tag in {"td", "th", "dt", "dd"}:
            self.text = []

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.skip = max(0, self.skip - 1)
        elif tag in {"td", "th"} and self.text is not None and self.cells is not None:
            self.cells.append(self.clean())
        elif tag == "tr" and self.cells is not None:
            if len(self.cells) == 2:
                self.add(*self.cells)
            self.cells = None
        elif tag == "dt" and self.text is not None:
            self.term = self.clean()
        elif tag == "dd" and self.text is not None and self.term is not None:
            self.add(self.term, self.clean())
            self.term = None

    def handle_data(self, data):
        if self.text is not None and not self.skip:
            self.text.append(data)

    def clean(self) -> str:
        value = re.sub(r"\s+", " ", "".join(self.text or [])).strip()
        self.text = None
        return value[:300]

    def add(self, label: str, value: str):
        if label and value and len(self.rows) < self.max_rows:
            self.rows.append((label, value))


def table_specs(html: str) -> list[tuple[str, object, str]]:
    """(field, value, label) from labelled spec rows on the page."""
    parser = SpecTables()
    parser.feed(html)
    found: list[tuple[str, object, str]] = []
    for label, value in parser.rows:
        field = label_field(label)
        if field:
            found.extend(
                (name, parsed, label)
                for name, parsed in parse_value(field, value, label_unit(label)).items()
            )
    return found
