"""Buyable part specs: deterministic guardrails around the model-stated spec.

The buying spec itself (category, mount, ratings, synonyms, seller-style queries) is
written by the extraction call, which already reads the whole project. This module only:

- normalises units so model-stated values can be compared with listings (33kΩ = 33K =
  33000 Ω; 22µF = 22uF = 22 mfd);
- refuses values without a basis (a value the model calls "stated" must appear in the
  source; an inferred primary value must appear in the project context);
- builds a labelled seed spec from the part name when no AI spec exists;
- detects pack listings ("pack of 10").
"""

import hashlib
import re
from dataclasses import dataclass
from fractions import Fraction

from bharat_sourcer.schemas import BomItem, BuyableSpec, ProjectContext, SpecParam

PREFIX = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "m": 1e-3, "": 1.0, "k": 1e3, "K": 1e3, "M": 1e6}
# Unit word -> (kind, base unit symbol).
UNITS = {
    "ohm": ("resistance", "ohm"),
    "ohms": ("resistance", "ohm"),
    "f": ("capacitance", "F"),
    "farad": ("capacitance", "F"),
    "farads": ("capacitance", "F"),
    "v": ("voltage", "V"),
    "vdc": ("voltage", "V"),
    "volt": ("voltage", "V"),
    "volts": ("voltage", "V"),
    "w": ("power", "W"),
    "watt": ("power", "W"),
    "watts": ("power", "W"),
    "a": ("current", "A"),
    "amp": ("current", "A"),
    "amps": ("current", "A"),
    "h": ("inductance", "H"),
    "m": ("length", "m"),
    "mm": ("length", "m"),
    "cm": ("length", "m"),
    "%": ("tolerance", "%"),
}
PRIMARY = {
    "resistor": "resistance",
    "capacitor_electrolytic": "capacitance",
    "capacitor_ceramic": "capacitance",
}
VALUE_CATEGORIES = set(PRIMARY)
SMD_EXCLUDES = ["SMD", "SMT", "surface mount", "chip resistor", "0402", "0603", "0805", "1206"]


@dataclass(frozen=True)
class Measure:
    kind: str
    value: float
    unit: str
    text: str


def normalise_text(text: str) -> str:
    """Spell units one way: µ/μ/micro -> u, Ω/Ω -> ohm, mfd -> uF."""
    text = text.replace("µ", "u").replace("μ", "u").replace("Ω", "ohm").replace("Ω", "ohm")
    text = re.sub(r"(?i)\bmicro\s*-?\s*(?=f(?:arads?)?\b)", "u", text)
    text = re.sub(r"(?i)(\d)\s*micro\s*-?\s*(?=f)", r"\1u", text)
    text = re.sub(r"(?i)(?<=\d)\s*(?:mfd|mf)\b", "uF", text)
    text = re.sub(r"(?i)\bkilo\s*-?\s*ohms?\b", "kohm", text)
    text = re.sub(r"(?i)\bmega\s*-?\s*ohms?\b", "Mohm", text)
    return text


NUMBER = r"(?<![\w.,/])(\d+(?:\.\d+)?(?:/\d+)?)"
QUANTITY = re.compile(
    NUMBER
    + r"\s*(?P<prefix>[pnumkKM]?)\s*"
    + r"(?P<unit>(?i:ohms?|farads?|volts?|vdc|watts?|amps?|mm|cm)|[fFvVwWaAhHm%])(?![a-zA-Z])"
)
# 4R7, 4k7, 2M2: the letter is the decimal point and the multiplier.
RKM = re.compile(r"(?<![\w.])(\d+)([RkKM])(\d+)(?![\w.])")
BARE_K = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)\s*([kKM])(?![\w])")
GAUGE = re.compile(r"(?i)(?<![\w.])(?:(\d{1,2})\s*(awg|swg)|(awg|swg)\s*-?\s*(\d{1,2}))(?![\w.])")


def number(raw: str) -> float | None:
    try:
        return float(Fraction(raw)) if "/" in raw else float(raw)
    except (ValueError, ZeroDivisionError):
        return None


def find_measures(text: str, resistor_context: bool = False) -> list[Measure]:
    """Every value-with-unit in `text`, normalised to SI. Bare "33K" counts as ohms only
    in a resistor context, where sellers routinely omit the unit."""
    text = normalise_text(text or "")[:20000]
    found: list[Measure] = []
    taken: list[tuple[int, int]] = []

    def add(match, kind, value, unit):
        if value is None:
            return
        span = match.span()
        if any(s < span[1] and span[0] < e for s, e in taken):
            return
        taken.append(span)
        found.append(Measure(kind, value, unit, match.group(0).strip()))

    for match in GAUGE.finditer(text):
        size = match.group(1) or match.group(4)
        system = (match.group(2) or match.group(3)).upper()
        add(match, "gauge", float(size), system)
    for match in QUANTITY.finditer(text):
        raw, prefix, unit = match.group(1), match.group("prefix"), match.group("unit")
        key = unit.lower()
        if key == "m" and prefix == "":
            kind, base = "length", "m"
        elif key in {"mm", "cm"}:
            kind, base = "length", "m"
            prefix = "m" if key == "mm" else ""
            scale = 0.01 if key == "cm" else 1.0
            value = number(raw)
            add(match, kind, value * PREFIX[prefix] * scale if value is not None else None, base)
            continue
        elif key == "h" and prefix not in {"u", "m", "n"}:
            # "5H" pencils and "2H" hardness are not inductors.
            continue
        elif key == "a" and prefix == "" and unit == "a":
            continue
        else:
            kind, base = UNITS[key]
        if kind == "resistance" and prefix == "m":
            # Sellers write "1-20 mohm" meaning megohms; milliohm parts are not hobby stock.
            prefix = "M"
        if kind == "capacitance" and prefix not in {"p", "n", "u", "m"}:
            # A bare "F" after a number (or "kF") is not a hobby capacitor value.
            continue
        value = number(raw)
        if value is None:
            continue
        add(match, kind, value * PREFIX[prefix], base)
    for match in RKM.finditer(text):
        whole, letter, frac = match.groups()
        scale = {"R": 1.0, "k": 1e3, "K": 1e3, "M": 1e6}[letter]
        add(match, "resistance", float(f"{whole}.{frac}") * scale, "ohm")
    if resistor_context:
        for match in BARE_K.finditer(text):
            add(match, "resistance", float(match.group(1)) * PREFIX[match.group(2)], "ohm")
        for match in re.finditer(r"(?<![\w.])(\d+(?:\.\d+)?)\s*R(?![\w])", text):
            add(match, "resistance", float(match.group(1)), "ohm")
    return found


def parse_measure(text: str, resistor_context: bool = False) -> Measure | None:
    found = find_measures(text, resistor_context)
    return found[0] if found else None


def same_value(left: float, right: float) -> bool:
    return abs(left - right) <= 1e-9 * max(abs(left), abs(right), 1e-30)


def param_matches(param: SpecParam, measure: Measure) -> bool | None:
    """True/False when comparable; None when the measure is a different quantity."""
    if param.si_value is None or param.unit != measure.unit:
        return None
    low = param.si_value
    if param.operator == "equals":
        return same_value(low, measure.value)
    if param.operator == "at_least":
        return measure.value >= low or same_value(low, measure.value)
    if param.operator == "at_most":
        return measure.value <= low or same_value(low, measure.value)
    high = param.si_value_max if param.si_value_max is not None else low
    return low <= measure.value <= high or any(
        same_value(measure.value, edge) for edge in (low, high)
    )


def with_si(param: SpecParam, resistor_context: bool) -> SpecParam:
    measure = parse_measure(param.value, resistor_context)
    if measure is None:
        return param.model_copy(update={"si_value": None, "si_value_max": None})
    update = {"si_value": measure.value, "unit": measure.unit}
    if param.value_max:
        # "1k-10k": a bare upper bound takes the lower bound's quantity.
        top = parse_measure(param.value_max, resistor_context or measure.kind == "resistance")
        if top is not None and top.unit == measure.unit:
            update["si_value_max"] = top.value
    return param.model_copy(update=update)


def stated_in(param: SpecParam, text: str, resistor_context: bool) -> bool:
    if param.si_value is None:
        return normalise_text(param.value).casefold() in normalise_text(text).casefold()
    measures = find_measures(text, resistor_context)
    values = [param.si_value] + ([param.si_value_max] if param.si_value_max is not None else [])
    return all(
        any(m.unit == param.unit and same_value(m.value, v) for m in measures) for v in values
    )


def item_text(item: BomItem) -> str:
    parts = [item.raw_name]
    parts += [f"{r.name} {r.value} {r.unit or ''}" for r in item.requirements if r.origin == "user"]
    parts += [e.quote or "" for e in item.evidence] + [e.observation for e in item.evidence]
    return " \n".join(parts)


def project_text(project: ProjectContext | None, item: BomItem | None = None) -> str:
    parts = []
    if project:
        parts += [project.summary or "", project.power or "", project.description or ""]
        parts += project.assumptions
    if item:
        parts += [f"{r.name} {r.value} {r.unit or ''}" for r in item.requirements]
    return " \n".join(parts)


def unique(values, limit):
    seen, kept = set(), []
    for value in values:
        value = " ".join(str(value).split())[:120]
        if value and value.casefold() not in seen:
            seen.add(value.casefold())
            kept.append(value)
    return kept[:limit]


def guard_spec(spec: BuyableSpec, source_text: str, context_text: str) -> BuyableSpec:
    """Normalise units and drop values with no basis. User specs are normalised only."""
    user = spec.origin == "user"
    resistorish = spec.category in {"resistor", "ldr"}
    primary = PRIMARY.get(spec.category)
    params, reasons = [], list(spec.reasons)
    needs_value, needs_reason = spec.needs_value, spec.needs_value_reason
    for param in spec.params:
        param = with_si(param, resistorish)
        if user:
            params.append(param.model_copy(update={"origin": "user"}))
            continue
        if param.origin == "stated" and not stated_in(param, source_text, resistorish):
            if not param.reason:
                reasons.append(f"Dropped {param.name}: not found in the source.")
                continue
            param = param.model_copy(update={"origin": "inferred"})
        if param.origin == "inferred" and not param.reason:
            reasons.append(f"Dropped {param.name}: inferred without a reason.")
            continue
        is_primary = (
            primary is not None
            and param.si_value is not None
            and (
                (param.unit == "ohm" and primary == "resistance")
                or (param.unit == "F" and primary == "capacitance")
            )
        )
        if (
            is_primary
            and param.origin == "inferred"
            and not stated_in(param, context_text, resistorish)
        ):
            # Never invent a part value: an inferred value needs a basis in the project.
            reasons.append(f"Dropped {param.name}: no basis in the source or project.")
            needs_value = True
            needs_reason = needs_reason or "The source does not state this part's value."
            continue
        params.append(param)
    if spec.category in VALUE_CATEGORIES and not user:
        has_value = any(
            p.unit == ("ohm" if primary == "resistance" else "F")
            and p.operator == "equals"
            and p.si_value is not None
            for p in params
        )
        if not has_value:
            needs_value = True
            needs_reason = needs_reason or "The source does not state this part's value."
        elif needs_value and not any(p.origin == "inferred" for p in params):
            needs_value, needs_reason = False, None
    mount, mount_origin, mount_reason = spec.mount, spec.mount_origin, spec.mount_reason
    if not user and mount != "any" and mount_origin in {"inferred", "default"} and not mount_reason:
        mount, mount_origin = "any", "default"
    if user and mount != "any":
        mount_origin = "user"
    exclude = list(spec.exclude)
    if mount == "tht" and spec.category in {"resistor", "capacitor_ceramic", "led", "diode"}:
        exclude += SMD_EXCLUDES
    return spec.model_copy(
        update={
            "params": params[:12],
            "must": unique([p.name for p in params if p.required], 12),
            "mount": mount,
            "mount_origin": mount_origin,
            "mount_reason": mount_reason,
            "prefer": unique(spec.prefer, 10),
            "exclude": unique(exclude, 12),
            "synonyms": unique(spec.synonyms, 10),
            "queries": unique(spec.queries, 4),
            "needs_value": needs_value,
            "needs_value_reason": needs_reason if needs_value else None,
            "reasons": unique(reasons, 6),
        }
    )


QUANTITY_NAMES = {
    "resistance": "resistance",
    "capacitance": "capacitance",
    "voltage": "voltage_rating",
    "power": "power_rating",
    "current": "current",
    "length": "size",
    "tolerance": "tolerance",
    "gauge": "gauge",
    "inductance": "inductance",
}


def seed_spec(item: BomItem) -> BuyableSpec:
    """Labelled fallback when no AI spec exists: values from the name, nothing inferred."""
    resistorish = bool(re.search(r"(?i)resist|\bldr\b|ohm", item.raw_name))
    params, seen = [], set()
    for measure in find_measures(item.raw_name, resistorish):
        name = QUANTITY_NAMES[measure.kind]
        if name in seen:
            continue
        seen.add(name)
        params.append(
            SpecParam(
                name=name,
                value=normalise_text(measure.text),
                unit=measure.unit,
                si_value=measure.value,
                origin="stated",
                required=name in {"resistance", "capacitance"},
            )
        )
    query = " ".join(normalise_text(item.raw_name).split())[:120]
    return BuyableSpec(
        origin="seed",
        params=params,
        must=[p.name for p in params if p.required],
        queries=[query] if query else [],
        reasons=["Seed spec from the part name; no AI buying spec was available."],
    )


def buyable_spec(item: BomItem, project: ProjectContext | None = None) -> BuyableSpec:
    """The spec sourcing uses for a line: the item's AI/user spec, guarded, or a seed."""
    if item.buyable_spec is None:
        return seed_spec(item)
    spec = guard_spec(item.buyable_spec, item_text(item), project_text(project, item))
    if not spec.queries:
        spec = spec.model_copy(update={"queries": seed_spec(item).queries})
    return spec


PACK = [
    re.compile(r"(?i)\b(?:pack|set|lot|bag|box|kit|bundle)\s+of\s+(\d{1,5})\b"),
    re.compile(r"(?i)(?<![\w.])(\d{1,5})\s*(?:pcs|pc|pieces|nos|units)\b\.?"),
    re.compile(r"(?i)\b(\d{1,5})\s*-?\s*pack\b"),
]


def pack_quantity(text: str) -> int | None:
    """Pieces per listing when the text states a pack; None when absent or contradictory."""
    counts = {int(m.group(1)) for pattern in PACK for m in pattern.finditer(text or "")}
    counts.discard(0)
    if len(counts) != 1:
        return None
    count = counts.pop()
    return count if 1 < count <= 100000 else None


def spec_hash(spec: BuyableSpec) -> str:
    return hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:32]
