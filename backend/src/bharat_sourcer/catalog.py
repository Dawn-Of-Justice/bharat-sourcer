"""Curated maker-part catalogue (a static knowledge graph) and a deterministic name resolver.

Entries are curated reference facts about common modules and chips, never seller facts.
`verified` stays false until a maintainer checks every value against the cited `source`.
"""

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from importlib.resources import files
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from bharat_sourcer.schemas import PartSpecs

Category = Literal[
    "dev_board",
    "sensor",
    "input",
    "display",
    "motor_driver",
    "actuator",
    "led",
    "relay",
    "power",
    "comms",
    "passive",
    "cable",
    "misc",
]
Grade = Literal["A", "B", "C", "D", "X"]
Area = Literal["wiring", "code", "power", "safety", "verify"]
Interface = Literal[
    "i2c", "spi", "uart", "digital", "analog", "pwm", "one_wire", "usb", "parallel", "step_dir"
]
Connector = Literal[
    "header",
    "stemma_qt",
    "qwiic",
    "grove",
    "jst_ph",
    "pi_hat",
    "feather",
    "pololu_stepstick",
    "screw_terminal",
    "usb",
    "barrel",
    "ac_plug",
]
Range = tuple[float, float]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Change(Strict):
    area: Area
    text: str = Field(min_length=1, max_length=400)


class Substitute(Strict):
    """A curated edge: replacing this entry with `id` needs at least `grade`."""

    id: str
    grade: Grade
    changes: list[Change] = Field(min_length=1)


class CatalogEntry(Strict):
    id: str = Field(pattern=r"^[a-z0-9_]+$")
    name: str = Field(min_length=1, max_length=120)
    category: Category
    chip: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$")
    # Maps the entry onto the original typed `PartSpecs` families.
    family: Literal["pro_micro", "oled", "ttp223", "usb_cable"] | None = None
    aliases: list[str] = Field(min_length=1)
    # Shared terms that only ever produce an ambiguous candidate list.
    generic: list[str] = Field(default_factory=list)
    supply_v: Range | None = None
    # Float literals are valid for pydantic (enum in OpenAPI) but not in the typing spec.
    logic_v: Literal[3.3, 5.0] | None = None  # type: ignore[valid-type]
    logic_follows_supply: bool = False
    io_5v_tolerant: bool | None = None
    input_3v3_ok: bool | None = None
    output_signals: list[str] = Field(default_factory=list)
    interfaces: list[Interface] = Field(default_factory=list)
    i2c_addresses: list[str] = Field(default_factory=list)
    pins: list[str] = Field(default_factory=list)
    connector: Connector | None = None
    wiring_note: str | None = None
    measures: list[str] = Field(default_factory=list)
    ranges: dict[str, Range] = Field(default_factory=dict)
    steps: dict[str, float] = Field(default_factory=dict)
    display_controller: str | None = None
    display_resolution: str | None = Field(default=None, pattern=r"^\d+x\d+$")
    current_a: float | None = Field(default=None, gt=0)
    motor_supply_v: Range | None = None
    control_interface: Literal["step_dir", "pwm_dir", "digital", "pwm"] | None = None
    footprint: str | None = None
    output_v: float | None = Field(default=None, gt=0)
    input_vac: Range | None = None
    plug: Literal["type_d", "type_m", "us_type_a", "us_type_b"] | None = None
    barrel: Literal["5.5x2.1", "5.5x2.5"] | None = None
    polarity: Literal["center_positive", "center_negative"] | None = None
    mains: bool = False
    mains_rating_vac: float | None = Field(default=None, gt=0)
    enclosed: bool | None = None
    active_level: Literal["high", "low"] | None = None
    control_v: Range | None = None
    protocol: str | None = None
    ma_per_led: float | None = Field(default=None, gt=0)
    features: list[str] = Field(default_factory=list)
    board_target: str | None = None
    usb_serial: str | None = None
    bootloader: Literal["new", "old"] | None = None
    pin_labels: Literal["gpio", "d_labels"] | None = None
    strapping_pins: list[int] = Field(default_factory=list)
    input_only_pins: list[int] = Field(default_factory=list)
    rails_v: list[float] = Field(default_factory=list)
    clock_mhz: int | None = None
    libraries: list[str] = Field(default_factory=list)
    lookalikes: list[str] = Field(default_factory=list)
    verify: str | None = None
    substitutes: list[Substitute] = Field(default_factory=list)
    part_specs: dict[str, str | float | bool] = Field(default_factory=dict)
    notes: str | None = None
    source: str | None = Field(default=None, pattern=r"^https://")
    verified: bool = False

    @model_validator(mode="after")
    def consistent(self):
        ranges = [self.supply_v, self.motor_supply_v, self.input_vac, self.control_v]
        ranges += list(self.ranges.values())
        if any(r is not None and r[0] > r[1] for r in ranges):
            raise ValueError(f"{self.id}: range minimum exceeds maximum")
        if any(not re.fullmatch(r"0x[0-9a-f]{2}", a) for a in self.i2c_addresses):
            raise ValueError(f"{self.id}: I2C addresses must look like 0x3c")
        if self.i2c_addresses and "i2c" not in self.interfaces:
            raise ValueError(f"{self.id}: I2C addresses without an I2C interface")
        if self.verified and not self.source:
            raise ValueError(f"{self.id}: verified entries must cite a source")
        if self.category == "sensor" and not self.measures:
            raise ValueError(f"{self.id}: sensors must list measured quantities")
        if self.mains and self.category not in {"relay", "power"}:
            raise ValueError(f"{self.id}: only relay or power entries switch mains")
        legacy_specs(self)  # Raises when the entry contradicts the typed families.
        return self


def legacy_specs(entry: CatalogEntry) -> dict:
    """Catalogue values expressed in the original typed `PartSpecs` vocabulary."""
    if entry.family is None:
        return {}
    values = {"family": entry.family}
    if entry.chip in {"atmega32u4", "ssd1306", "sh1106", "ttp223"}:
        values["controller"] = entry.chip
    if entry.logic_v is not None:
        values["logic_v"] = entry.logic_v
    if entry.clock_mhz in {8, 16}:
        values["clock_mhz"] = entry.clock_mhz
    if len(entry.interfaces) == 1 and entry.interfaces[0] in {"i2c", "spi", "digital", "usb"}:
        values["interface"] = entry.interfaces[0]
    if entry.display_resolution in {"128x32", "128x64"}:
        values["resolution"] = entry.display_resolution
    if entry.supply_v:
        values["supply_min_v"], values["supply_max_v"] = entry.supply_v
    if entry.i2c_addresses and entry.i2c_addresses[0] in {"0x3c", "0x3d"}:
        values["i2c_address"] = entry.i2c_addresses[0]
    if entry.pins:
        values["pinout"] = ",".join(entry.pins)
    values |= entry.part_specs
    return PartSpecs(**values).model_dump(exclude_none=True)


# Words that describe a category rather than identify a part; ignored for coverage.
STOP = {
    "a", "an", "and", "the", "for", "with", "of", "to", "in", "on", "x", "pcs", "pc", "piece",
    "module", "modules", "board", "boards", "breakout", "sensor", "sensors", "kit", "arduino",
    "compatible", "development", "dev", "display", "screen", "driver", "controller", "motor",
    "stepper", "temperature", "humidity", "pressure", "digital", "analog", "ultrasonic",
    "distance", "capacitive", "touch", "original", "genuine", "new", "high", "quality", "mini",
    "backpack", "adapter", "interface", "microcontroller", "wifi", "bluetooth", "strip", "led",
    "leds", "rgb", "pixel", "pixels", "black", "blue", "white", "green", "red", "purple",
    "yellow", "type", "v", "inch",
}  # fmt: skip


def normalize(text: str) -> list[str]:
    text = text.lower().replace("×", "x").replace("µ", "u").replace("Ω", "ohm")
    # 0.96", 0.96″, 0.96 inch → 0.96in
    text = re.sub(r"(\d)\s*(?:\"|''|″|inch(?:es)?\b)", r"\1in ", text)
    return re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text)


@dataclass(frozen=True)
class Hit:
    entry: CatalogEntry
    covered: frozenset[int]
    contiguous: bool
    generic: bool


@dataclass
class Resolution:
    status: Literal["matched", "ambiguous", "unmatched"]
    entry: CatalogEntry | None = None
    confidence: float = 0.0
    candidates: list[tuple[CatalogEntry, float]] = field(default_factory=list)


class Catalog:
    def __init__(self, entries: list[CatalogEntry]):
        self.entries: dict[str, CatalogEntry] = {}
        for entry in entries:
            if entry.id in self.entries:
                raise ValueError(f"Duplicate catalogue id {entry.id}")
            self.entries[entry.id] = entry
        self.aliases: dict[str, tuple[CatalogEntry, list[str], bool]] = {}
        for entry in entries:
            for alias, generic in [(a, False) for a in entry.aliases] + [
                (g, True) for g in entry.generic
            ]:
                tokens = normalize(alias)
                if not tokens:
                    raise ValueError(f"{entry.id}: empty alias")
                key = ("g:" if generic else "a:") + entry.id + ":" + "".join(tokens)
                self.aliases[key] = (entry, tokens, generic)
            for ref in entry.lookalikes + [s.id for s in entry.substitutes]:
                if ref not in self.entries or ref == entry.id:
                    raise ValueError(f"{entry.id}: unknown reference {ref}")
        seen: dict[str, str] = {}
        for entry, tokens, generic in self.aliases.values():
            if generic:
                continue
            key = "".join(tokens)
            if seen.get(key, entry.id) != entry.id:
                raise ValueError(f"Alias '{key}' is used by {seen[key]} and {entry.id}")
            seen[key] = entry.id
        for entry, tokens, generic in self.aliases.values():
            if generic and "".join(tokens) in seen:
                raise ValueError(f"{entry.id}: generic term '{''.join(tokens)}' is an alias")

    def get(self, entry_id: str | None) -> CatalogEntry | None:
        return self.entries.get(entry_id) if entry_id else None

    def _match(self, tokens: list[str], alias: list[str]) -> tuple[frozenset[int], bool] | None:
        joined = "".join(alias)
        # Contiguous: the alias spelling equals one to five adjacent name tokens joined.
        for start in range(len(tokens)):
            text = ""
            for end in range(start, min(start + 5, len(tokens))):
                text += tokens[end]
                if text == joined:
                    return frozenset(range(start, end + 1)), True
                if len(text) >= len(joined):
                    break
        # Ordered with at most two unrelated tokens in between ("pro micro compatible 5v").
        if len(alias) < 2:
            return None
        for start, token in enumerate(tokens):
            if token != alias[0]:
                continue
            covered, position, gaps = [start], start, 0
            for wanted in alias[1:]:
                position += 1
                while position < len(tokens) and tokens[position] != wanted and gaps <= 2:
                    position, gaps = position + 1, gaps + 1
                if position >= len(tokens) or gaps > 2 or tokens[position] != wanted:
                    break
                covered.append(position)
            else:
                return frozenset(covered), False
        return None

    def resolve(self, name: str) -> Resolution:
        """Map a raw BOM or listing name to one entry, or return candidates; never guess."""
        tokens = normalize(name)
        significant = {i for i, t in enumerate(tokens) if t not in STOP and not t.isdigit()}
        best: dict[str, Hit] = {}
        for entry, alias, generic in self.aliases.values():
            found = self._match(tokens, alias)
            if not found:
                continue
            hit = Hit(entry, found[0], found[1], generic)
            current = best.get(entry.id)
            if current is None:
                best[entry.id] = hit
                continue
            # One entry's aliases and shared terms together explain the name.
            lead = hit if rank(hit, significant) > rank(current, significant) else current
            best[entry.id] = Hit(
                entry,
                current.covered | hit.covered,
                lead.contiguous,
                current.generic and hit.generic,
            )
        if not best:
            return Resolution("unmatched")
        hits = sorted(best.values(), key=lambda h: rank(h, significant), reverse=True)
        top = hits[0]

        def confidence(hit: Hit) -> float:
            covered = len(hit.covered & significant)
            coverage = covered / len(significant) if significant else 1.0
            base = 0.6 if hit.contiguous else 0.5
            return round(min(1.0, base + 0.4 * coverage) - (0.2 if hit.generic else 0), 2)

        top_sig = top.covered & significant
        if top.generic:
            # Only shared terms matched ("BME280", "OLED"): list the variants, pick none.
            pool = [h for h in hits if (h.covered & significant) == top_sig]
        else:
            # A rival names something the top match does not explain, or ties with it.
            pool = [top] + [
                h
                for h in hits[1:]
                if (h.covered & significant) - top_sig
                or (
                    not h.generic
                    and (h.covered & significant) == top_sig
                    and h.contiguous == top.contiguous
                )
            ]
        if len(pool) == 1:
            return Resolution("matched", top.entry, confidence(top))
        return Resolution(
            "ambiguous",
            candidates=[(h.entry, confidence(h)) for h in pool[:6]],
            confidence=confidence(top),
        )


def rank(hit: Hit, significant: set[int]) -> tuple:
    return (
        not hit.generic,
        len(hit.covered & significant),
        hit.contiguous,
        len(hit.covered),
    )


def parse_catalog(raw: object) -> Catalog:
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise ValueError("Catalogue must be an object with an 'entries' list")
    return Catalog([CatalogEntry.model_validate(entry) for entry in raw["entries"]])


@lru_cache(maxsize=1)
def load_catalog() -> Catalog:
    path = files("bharat_sourcer").joinpath("data", "parts_catalog.json")
    return parse_catalog(json.loads(path.read_text(encoding="utf-8")))


def resolve_name(name: str) -> Resolution:
    return load_catalog().resolve(name)
