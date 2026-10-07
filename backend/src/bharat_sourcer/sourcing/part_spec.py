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


# Seed classification from the part name, first match wins (LDR before resistor, LED before
# diode, modules and boards before the parts they carry).
SEED_CATEGORIES: list[tuple[re.Pattern, str]] = [
    (
        re.compile(
            r"(?i)\bldrs?\b|photo-?resistor|light[\s-]*dependent[\s-]*resistor|photocell"
            r"|\bgl55\d\d\b"
        ),
        "ldr",
    ),
    (
        re.compile(r"(?i)arduino|esp32|esp8266|raspberry|nodemcu|dev(?:elopment)?\s*board"),
        "board",
    ),
    (re.compile(r"(?i)\bmodules?\b|breakout"), "module"),
    (re.compile(r"(?i)\bsensors?\b|thermistor"), "sensor"),
    (re.compile(r"(?i)\bleds?\b|light[\s-]*emitting[\s-]*diode"), "led"),
    (re.compile(r"(?i)resistor|\bresistance\b"), "resistor"),
    (re.compile(r"(?i)electrolytic|\belko\b"), "capacitor_electrolytic"),
    (
        re.compile(r"(?i)ceramic\s*(?:disc\s*)?capacitor|\bmlcc\b|disc\s*capacitor"),
        "capacitor_ceramic",
    ),
    (re.compile(r"(?i)\bdiodes?\b|\b1n4\d{3}\b|\b1n58\d\d\b|zener|schottky|rectifier"), "diode"),
    (
        re.compile(r"(?i)transistor|mosfet|\bbjt\b|\b(?:bc|2n|tip|irf|irlz?)\d{2,4}[a-z]?\b"),
        "transistor",
    ),
    (
        re.compile(
            r"(?i)\bics?\b|integrated circuit|op-?amp|\bne555\b|\b555\b|timer ic|\blm\d{2,4}\b"
            r"|\bcd40\d\d\b|\b74(?:hc|ls)\d+\b|\batmega\d*|\battiny\d*"
        ),
        "ic",
    ),
    (re.compile(r"(?i)switch|push[\s-]*button|tactile|\bbuttons?\b"), "switch"),
    (
        re.compile(r"(?i)batter(?:y|ies)|\b18650\b|coin\s*cell|li-?po\b|li-?ion|\bcells?\b"),
        "battery",
    ),
    (
        re.compile(r"(?i)connector|\bheaders?\b|\bjst\b|terminal\s*block|\bsocket\b|\bjack\b"),
        "connector",
    ),
    (
        re.compile(r"(?i)\bwires?\b|\bawg\b|\bswg\b|hook-?up|bus\s*bar|enamel(?:led)?\s*copper"),
        "wire",
    ),
]
CAPACITOR = re.compile(r"(?i)capacitor")
INDUCTOR = re.compile(r"(?i)inductor|\bchoke\b|\bcoil\b")
NAME_THT = re.compile(r"(?i)through[\s-]*hole|\btht\b|\bpth\b|\bdip\b|\baxial\b|\bradial\b")
NAME_SMD = re.compile(r"(?i)\bsmd\b|\bsmt\b|surface[\s-]*mount")


def seed_category(name: str, measures: list[Measure]) -> str:
    for pattern, category in SEED_CATEGORIES:
        if pattern.search(name):
            return category
    if CAPACITOR.search(name):
        # Plain "capacitor": the value decides the usual kind; without one it stays open.
        farads = [m.value for m in measures if m.unit == "F"]
        if farads:
            return "capacitor_electrolytic" if farads[0] >= 1e-6 else "capacitor_ceramic"
    return "other"


def seed_spec(item: BomItem) -> BuyableSpec:
    """Labelled fallback when no AI spec exists: values from the name (and the user's own
    requirements), a category from name keywords, nothing inferred."""
    name = item.raw_name
    resistorish = bool(re.search(r"(?i)resist|\bldr\b|ohm", name))
    user = [r for r in item.requirements if r.origin == "user"]
    sources = [(name, "stated")] + [(f"{r.value} {r.unit or ''}", "user") for r in user]
    params, seen, all_measures = [], set(), []
    for text, origin in sources:
        found = find_measures(text, resistorish)
        all_measures += found
        for measure in found:
            param_name = QUANTITY_NAMES[measure.kind]
            if param_name in seen:
                continue
            seen.add(param_name)
            params.append(
                SpecParam(
                    name=param_name,
                    value=normalise_text(measure.text),
                    unit=measure.unit,
                    si_value=measure.value,
                    origin=origin,
                    required=param_name in {"resistance", "capacitance", "inductance"},
                )
            )
    category = seed_category(name, all_measures)
    units = {m.unit for m in all_measures}
    needs_value, needs_reason = False, None
    if category == "resistor" and "ohm" not in units:
        needs_value, kind = True, "resistance"
    elif (category.startswith("capacitor") or CAPACITOR.search(name)) and "F" not in units:
        needs_value, kind = True, "capacitance"
    elif INDUCTOR.search(name) and category == "other" and "H" not in units:
        needs_value, kind = True, "inductance"
    if needs_value:
        needs_reason = (
            f"The part name gives no {kind} value; choose the value before buying "
            "(a single-value listing would be a guess)."
        )
    mount, mount_origin = "any", "default"
    if NAME_SMD.search(name):
        mount, mount_origin = "smd", "stated"
    elif NAME_THT.search(name):
        mount, mount_origin = "tht", "stated"
    exclude = SMD_EXCLUDES if mount == "tht" and category in {"resistor", "led", "diode"} else []
    query = " ".join(normalise_text(name).split())[:120]
    return BuyableSpec(
        origin="seed",
        category=category,
        mount=mount,
        mount_origin=mount_origin,
        mount_reason="The part name states the mount." if mount != "any" else None,
        params=params,
        must=[p.name for p in params if p.required],
        exclude=list(exclude),
        queries=[query] if query else [],
        needs_value=needs_value,
        needs_value_reason=needs_reason,
        reasons=["Seed spec from the part name; no AI buying spec was available."],
    )


def with_seller_queries(spec: BuyableSpec, name: str) -> BuyableSpec:
    """Add the wording sellers use when the part name differs from it.

    Indian sellers list clear (water-clear) LEDs as white, so a clear LED with no colour
    named also gets a "white LED" query.
    """
    text = name.lower()
    if spec.category != "led" or not re.search(r"\b(clear|transparent)\b", text):
        return spec
    colours = r"\b(red|green|blue|yellow|orange|white|pink|purple|rgb|uv|ir|infrared)\b"
    if re.search(colours, text) or any("white" in q.lower() for q in spec.queries):
        return spec
    size = re.search(r"\d+(?:\.\d+)?\s*mm", text)
    query = f"{size.group(0).replace(' ', '')} white LED" if size else "white LED clear"
    # Second, so it falls inside the few queries seller search uses.
    return spec.model_copy(update={"queries": [*spec.queries[:1], query, *spec.queries[1:3]]})


def buyable_spec(item: BomItem, project: ProjectContext | None = None) -> BuyableSpec:
    """The spec sourcing uses for a line: the item's AI/user spec, guarded, or a seed."""
    name = item.raw_name[:200]
    if item.buyable_spec is None:
        spec = seed_spec(item).model_copy(update={"part_name": name})
        return with_seller_queries(spec, name)
    spec = guard_spec(item.buyable_spec, item_text(item), project_text(project, item))
    if not spec.queries:
        spec = spec.model_copy(update={"queries": seed_spec(item).queries})
    return with_seller_queries(spec.model_copy(update={"part_name": name}), name)


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


ASSORTMENT = re.compile(
    r"(?i)\bkits?\b|assort(?:ment|ed)?\b|\bcombo\b|\b\d{1,3}\s*(?:different\s+)?values?\b"
    r"|\bvalues?\s+(?:kit|pack|set|box)\b|\bmixed\s+values?\b"
)


def is_assortment(text: str) -> bool:
    """A kit or assortment of several values, not a pack of one value ("pack of 10")."""
    return bool(ASSORTMENT.search(text or ""))


PRIMARY_UNITS = {"ohm", "F", "H"}


def awg_m(gauge: float) -> float:
    """Diameter in metres of an AWG gauge (24 AWG ≈ 0.51 mm, 18 AWG ≈ 1.02 mm)."""
    return 0.000127 * 92 ** ((36 - gauge) / 39)


# Spec-row labels that state each length-like param. Other params match their own name words.
# "Dimensions" rows are usually the shipping package, so they never state a part's size.
ROW_LABELS = {
    "size": {"size", "diameter", "dia", "lens"},
    "diameter": {"size", "diameter", "dia", "thickness"},
    "wire_gauge": {"gauge", "awg", "swg", "diameter", "dia", "thickness", "size"},
}
# Lengths are rounded differently by sellers (5 mm vs 5.1 mm); compare within 15%.
LENGTH_TOLERANCE = 0.15


def row_states(param: SpecParam, label: str) -> bool:
    """Whether a spec row's label names this param's quantity."""
    words = set(re.findall(r"[a-z]+", label.lower()))
    return bool(words & ROW_LABELS.get(param.name, set(param.name.lower().split("_"))))


def length_fits(param: SpecParam, measure: Measure) -> bool:
    if param.unit != "m" or measure.unit != "m" or param.si_value is None:
        return False
    low = param.si_value * (1 - LENGTH_TOLERANCE)
    high = (param.si_value_max or param.si_value) * (1 + LENGTH_TOLERANCE)
    if param.operator == "at_least":
        high = float("inf")
    elif param.operator == "at_most":
        low = 0.0
    return low <= measure.value <= high


def measure_conflicts(spec: BuyableSpec, texts: list[str]) -> list[str]:
    """Spec params a listing's own numbers contradict, after unit normalisation.

    Each text (the title, then each spec row) is checked separately: a param conflicts when
    the text states a value of the same quantity and none of its values fits the param.
    For a diameter-like length (under 1 cm) spool lengths of 10 cm or more are ignored, so
    "0.8 mm wire, 10 m" is not a conflict. An assortment's primary values (ohm, F, H) are
    compared as a range: the kit fits when it spans the param. Spec rows (every text after
    the title, as "label: value") are checked only for params their label names, so a lead
    length is never read as a diameter.
    """
    resistorish = spec.category in {"resistor", "ldr"}
    conflicts: list[str] = []
    for index, text in enumerate(texts):
        if not text:
            continue
        label = text.split(":", 1)[0] if index and ":" in text else None
        measures = find_measures(text, resistorish)
        kit = is_assortment(text)
        for param in spec.params:
            if param.si_value is None or param.name in conflicts:
                continue
            if label is not None and not row_states(param, label):
                continue
            top = param.si_value_max if param.si_value_max is not None else param.si_value
            same = [m for m in measures if m.unit == param.unit]
            if param.unit == "AWG" and not same:
                # A gauge range against a stated diameter: compare in metres (±10%).
                thick, thin = awg_m(min(param.si_value, top)), awg_m(max(param.si_value, top))
                if param.operator == "at_least":
                    thick = awg_m(param.si_value)
                    thin = 0.0
                elif param.operator == "at_most":
                    thin, thick = awg_m(param.si_value), float("inf")
                diameters = [m.value for m in measures if m.unit == "m" and m.value < 0.01]
                if diameters and not any(thin * 0.9 <= d <= thick * 1.1 for d in diameters):
                    conflicts.append(param.name)
                continue
            if param.unit == "m" and top < 0.01:
                # A small part's size: far larger lengths (spools, boxes) are other quantities.
                same = [m for m in same if m.value < min(0.1, top * 5)]
            if not same:
                continue
            if kit and param.unit in PRIMARY_UNITS:
                values = [m.value for m in same]
                low = min(values)
                fits = low <= param.si_value * (1 + 1e-9) and max(values) >= top * (1 - 1e-9)
                if not fits and not any(param_matches(param, m) for m in same):
                    conflicts.append(param.name)
                continue
            if not any(param_matches(param, m) or length_fits(param, m) for m in same):
                conflicts.append(param.name)
    return conflicts


def spec_hash(spec: BuyableSpec) -> str:
    return hashlib.sha256(spec.model_dump_json().encode()).hexdigest()[:32]
