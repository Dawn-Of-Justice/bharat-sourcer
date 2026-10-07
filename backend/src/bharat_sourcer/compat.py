"""Conservative, deterministic comparison of declared module specifications."""

import re

from bharat_sourcer.catalog import CatalogEntry, Resolution, legacy_specs, resolve_name
from bharat_sourcer.compat_rules import LABELS, Context, Outcome, Side, evaluate, side_from_entry
from bharat_sourcer.schemas import (
    BomItem,
    CatalogCandidate,
    CatalogMatch,
    Clarification,
    CompatFinding,
    Compatibility,
    PartRequirement,
    PartResolution,
    PartSpecs,
    ProjectContext,
    Report,
    SpecEvidence,
    VerifiedOffer,
    WhatChanges,
)

REFERENCES = {
    "pro_micro": "https://learn.sparkfun.com/tutorials/pro-micro--fio-v3-hookup-guide/all",
    "oled": "https://learn.adafruit.com/monochrome-oled-breakouts?view=all",
    "ttp223": "https://www.tontek.com.tw/uploads/product/245/TTP223-HA6_V1.1_EN.pdf",
}
# Chip datasheets explain rules, but never supply module specs for an unknown clone.
REQUIRED = {
    "pro_micro": ["controller", "logic_v", "clock_mhz", "pinout"],
    "oled": [
        "controller",
        "interface",
        "resolution",
        "logic_v",
        "supply_min_v",
        "supply_max_v",
        "pinout",
        "i2c_address",
    ],
    "ttp223": [
        "controller",
        "interface",
        "logic_v",
        "supply_min_v",
        "supply_max_v",
        "pinout",
        "output_mode",
        "active_level",
    ],
    "usb_cable": ["connector_a", "connector_b", "data_support"],
}


def parse_name(name: str) -> PartSpecs:
    text = name.lower()
    values = {}
    if "pro micro" in text:
        values["family"] = "pro_micro"
    elif "oled" in text:
        values["family"] = "oled"
    elif re.search(r"\bttp223\b", text):
        values["family"] = "ttp223"
    elif "usb" in text and "cable" in text:
        values["family"] = "usb_cable"
    for field, options in {
        "controller": ["atmega32u4", "ssd1306", "sh1106", "ttp223"],
        "interface": ["i2c", "spi"],
    }.items():
        found = [value for value in options if re.search(r"\b" + value + r"\b", text)]
        if len(found) == 1:
            values[field] = found[0]
    clocks = re.findall(r"(?<![\d.])(8|16)\s*mhz\b", text)
    if len(set(clocks)) == 1:
        values["clock_mhz"] = int(clocks[0])
    # A title's generic '5V' may describe power input, not I/O levels.
    voltages = re.findall(r"\blogic\s*(3\.3|5(?:\.0)?)\s*v\b", text)
    if len(set(voltages)) == 1:
        values["logic_v"] = float(voltages[0])
    dimensions = re.findall(r"\b128\s*[x×]\s*(32|64)\b", text)
    if len(set(dimensions)) == 1:
        values["resolution"] = "128x" + dimensions[0]
    try:
        return PartSpecs(**values)
    except ValueError:
        return PartSpecs()


def required_fields(specs: PartSpecs) -> list[str]:
    fields = list(REQUIRED.get(specs.family, []))
    if specs.family == "oled" and specs.interface == "spi":
        fields.remove("i2c_address")
    return fields


def resolve_part(item: BomItem) -> PartResolution:
    found = resolve_name(item.raw_name)
    entry = found.entry if found.status == "matched" else None
    inferred = parse_name(item.raw_name).model_dump(exclude_none=True)
    declared = item.specs.model_dump(exclude_none=True)
    catalogued = legacy_specs(entry) if entry else {}
    try:
        specs = PartSpecs(**(catalogued | inferred | declared))
    except ValueError:
        # The name or the user disagrees with the catalogue: drop the catalogue values.
        specs = PartSpecs(**(inferred | declared))

    def provenance(field: str) -> tuple[str, str]:
        if field in declared:
            return "user", f"bom:{item.line_id}"
        if field in inferred:
            return "part_name", f"bom:{item.line_id}"
        return "catalog", f"catalog:{entry.id}"

    evidence = [
        SpecEvidence(
            field=field,
            value=str(value),
            source=provenance(field)[0],
            locator=provenance(field)[1],
        )
        for field, value in specs.model_dump(exclude_none=True).items()
    ]
    missing = [field for field in required_fields(specs) if getattr(specs, field) is None]
    if specs.family is None:
        missing = []
    questions = [
        Clarification(field=field, question=f"Confirm {field.replace('_', ' ')} for this part")
        for field in missing
    ]
    if specs.family is None and not item.requirements and entry is None:
        questions.append(
            Clarification(
                field="requirements",
                question="What must this part do, and what must it connect or fit to?",
            )
        )
    return PartResolution(
        query=item.raw_name,
        specs=specs,
        evidence=evidence,
        missing_specs=missing,
        clarifications=questions,
        catalog=catalog_match(found),
    )


def assess(required: PartSpecs, offered: PartSpecs) -> Compatibility:
    references = [REFERENCES[required.family]] if required.family in REFERENCES else []
    missing = []
    reasons = []
    changes = []
    blocked = False
    if required.family not in REQUIRED:
        return Compatibility(
            status="unknown",
            missing_fields=["project_requirements"],
            reasons=["Review the cited part research and confirm project requirements"],
        )
    if offered.family is None:
        missing.append("offered.family")
    elif required.family != offered.family:
        blocked = True
        reasons.append("Part family differs")
    for field in required_fields(required):
        left, right = getattr(required, field), getattr(offered, field)
        if left is None:
            missing.append("required." + field)
        if right is None:
            missing.append("offered." + field)
        if left is None or right is None or left == right:
            continue
        if field in {"supply_min_v", "supply_max_v"}:
            mismatch = right > left if field == "supply_min_v" else right < left
            if mismatch:
                blocked = True
                reasons.append("Candidate supply range does not cover the required range")
        elif field == "data_support":
            if left and not right:
                blocked = True
                reasons.append("Project requires USB data; candidate is charge-only")
        elif field == "i2c_address":
            changes.append(f"Change the configured I2C address from {left} to {right}")
        elif field == "pinout":
            # No automatic rewire recommendation without per-pin electrical analysis.
            blocked = True
            reasons.append("Pinout differs; a safe wiring adaptation has not been established")
        else:
            blocked = True
            reasons.append(f"{field.replace('_', ' ')} mismatch: required {left}, offered {right}")
    if blocked:
        return Compatibility(
            status="incompatible",
            grade="X",
            reasons=reasons,
            missing_fields=missing,
            references=references,
        )
    if missing:
        return Compatibility(
            status="unknown",
            reasons=["Insufficient declared specifications"],
            missing_fields=missing,
            changes=changes,
            references=references,
        )
    return Compatibility(
        status="changes_required" if changes else "compatible",
        grade="B" if changes else "A",
        reasons=[
            "Declared replacement specifications match; project wiring is not independently checked"
        ],
        changes=changes,
        references=references,
    )


# Catalogue rules (M5 resolution + M8 grading). The comparison above stays the fallback
# for parts the catalogue does not know.

FACT_FIELDS = (
    "chip",
    "supply_v",
    "logic_v",
    "interfaces",
    "i2c_addresses",
    "pins",
    "connector",
    "measures",
    "display_controller",
    "display_resolution",
    "current_a",
    "motor_supply_v",
    "output_v",
    "input_vac",
    "mains_rating_vac",
    "active_level",
    "protocol",
    "features",
    "board_target",
    "usb_serial",
)


def catalog_facts(entry: CatalogEntry) -> dict[str, str]:
    facts = {}
    for name in FACT_FIELDS:
        value = getattr(entry, name)
        if value is None or value == []:
            continue
        if isinstance(value, tuple):
            value = f"{value[0]:g}–{value[1]:g}"
        elif isinstance(value, list):
            value = ", ".join(str(v) for v in value)
        facts[name] = str(value)
    if entry.logic_follows_supply:
        facts["logic_v"] = "follows supply"
    if entry.mains:
        facts["mains"] = "true"
    return facts


def catalog_requirements(entry: CatalogEntry) -> list[PartRequirement]:
    """Reference values for research and review; never added to the maker's requirements."""
    reason = f"Curated catalogue reference for {entry.name}; not verified for any listing."

    def span(bounds):
        return f"{bounds[0]:g}–{bounds[1]:g}"

    found = [
        ("supply voltage", entry.supply_v and span(entry.supply_v), "V"),
        ("logic level", entry.logic_v and f"{entry.logic_v:g}", "V"),
        ("interface", ", ".join(entry.interfaces), None),
        ("I2C address", ", ".join(entry.i2c_addresses), None),
        ("measures", ", ".join(entry.measures), None),
        ("display controller", entry.display_controller, None),
        ("motor supply", entry.motor_supply_v and span(entry.motor_supply_v), "V"),
        ("output voltage", entry.output_v and f"{entry.output_v:g}", "V"),
        ("current rating", entry.current_a and f"{entry.current_a:g}", "A"),
    ]
    return [
        PartRequirement(name=name, value=value, unit=unit, origin="inferred", reason=reason)
        for name, value, unit in found
        if value
    ]


def catalog_match(found: Resolution) -> CatalogMatch:
    entry = found.entry
    candidates = [
        CatalogCandidate(id=e.id, name=e.name, confidence=c) for e, c in found.candidates[:6]
    ]
    if entry is None:
        return CatalogMatch(status=found.status, confidence=found.confidence, candidates=candidates)
    return CatalogMatch(
        status="matched",
        id=entry.id,
        name=entry.name,
        category=entry.category,
        chip=entry.chip,
        confidence=found.confidence,
        facts=catalog_facts(entry),
        requirements=catalog_requirements(entry),
        lookalikes=entry.lookalikes,
        verify=entry.verify,
        notes=entry.notes,
        source_url=entry.source,
        verified=entry.verified,
    )


def apply_specs(side: Side, specs: PartSpecs, source) -> None:
    """Overlay typed `PartSpecs` values onto rule facts; `source(field)` labels each one."""
    values = specs.model_dump(exclude_none=True)
    if "controller" in values:
        side.set("chip", values["controller"], source("controller"))
        if side.get("category") == "display":
            side.set("display_controller", values["controller"], source("controller"))
    if "logic_v" in values:
        side.set("logic_v", values["logic_v"], source("logic_v"))
        side.set("logic_follows_supply", False, source("logic_v"))
    if "interface" in values:
        side.set("interfaces", [values["interface"]], source("interface"))
    if "resolution" in values:
        side.set("display_resolution", values["resolution"], source("resolution"))
    if "pinout" in values:
        pins = [p.strip() for p in values["pinout"].split(",") if p.strip()]
        side.set("pins", pins, source("pinout"))
    if "supply_min_v" in values and "supply_max_v" in values:
        bounds = (values["supply_min_v"], values["supply_max_v"])
        side.set("supply_v", bounds, source("supply_max_v"))
    if "i2c_address" in values:
        others = [a for a in side.get("i2c_addresses") or [] if a != values["i2c_address"]]
        side.set("i2c_addresses", [values["i2c_address"], *others], source("i2c_address"))
    for name in (
        "output_mode",
        "active_level",
        "connector_a",
        "connector_b",
        "clock_mhz",
        "data_support",
    ):
        if name in values:
            side.set(name, values[name], source(name))


def required_side(entry: CatalogEntry, resolution: PartResolution) -> Side:
    side = side_from_entry(entry)
    sources = {e.field: e.source for e in resolution.evidence}
    # Catalogue values already sit on the side; overlay only what the user or name stated.
    stated = {
        k: v
        for k, v in resolution.specs.model_dump(exclude_none=True).items()
        if sources.get(k, "user") in {"user", "part_name"}
    }
    apply_specs(side, PartSpecs.model_construct(**stated), lambda f: sources.get(f, "user"))
    return side


def offered_side(offer: VerifiedOffer, required: CatalogEntry) -> tuple[Side, CatalogEntry | None]:
    found = resolve_name(offer.title)
    entry = found.entry if found.status == "matched" else None
    side = side_from_entry(entry) if entry else Side()
    if entry:
        # The listing names this part; the catalogue's other values stay labelled "catalog".
        for name in ("id", "category", "chip"):
            side.set(name, getattr(entry, name), "seller_title")
    elif found.candidates:
        pool = [e for e, _ in found.candidates]
        for name in ("category", "chip"):
            values = {getattr(e, name) for e in pool}
            if len(values) == 1:
                side.set(name, values.pop(), "seller_title")
    if offer.specs.family and offer.specs.family == required.family:
        side.set("category", required.category, "seller_title")
    apply_specs(side, offer.specs, lambda field: "seller")
    return side, entry


VOLTS = re.compile(r"(\d+(?:\.\d+)?)\s*v\b", re.IGNORECASE)
BATTERY = re.compile(r"batter|li-?ion|li-?po|18650|\bcell\b", re.IGNORECASE)


def project_context(
    project: ProjectContext | None, items=(), item: BomItem | None = None
) -> Context:
    """Rule context from the AI-inferred project reading plus the other BOM lines."""
    ctx = Context()
    if project and project.controller:
        found = resolve_name(project.controller)
        pool = [found.entry] if found.entry else [e for e, _ in found.candidates]
        boards = [e for e in pool if e.category == "dev_board"]
        if boards and len({(b.logic_v, b.io_5v_tolerant) for b in boards}) == 1:
            board = boards[0]
            ctx.controller = board.name if found.entry else project.controller
            ctx.controller_logic_v = board.logic_v
            ctx.controller_5v_tolerant = board.io_5v_tolerant
            ctx.rails = tuple(board.rails_v)
            if found.entry:
                ctx.strapping_pins = tuple(board.strapping_pins)
                ctx.input_only_pins = tuple(board.input_only_pins)
    if project and project.power:
        rails = [float(v) for v in VOLTS.findall(project.power) if float(v) <= 24]
        ctx.rails = tuple(dict.fromkeys([*ctx.rails, *rails]))
        ctx.uses_battery = bool(BATTERY.search(project.power))
    used = set()
    for other in items:
        if (item is not None and other.line_id == item.line_id) or other.user_has_it:
            continue
        found = resolve_name(other.raw_name)
        if found.entry and found.entry.i2c_addresses:
            used.add(found.entry.i2c_addresses[0])
    ctx.i2c_in_use = frozenset(used)
    for requirement in item.requirements if item else []:
        name, unit = requirement.name.lower(), (requirement.unit or "").lower()
        try:
            number = float(requirement.value)
        except ValueError:
            continue
        if "motor" in name and unit == "v":
            ctx.motor_supply_v = number
        elif "motor" in name and unit == "a":
            ctx.motor_current_a = number
        elif "load" in name and unit == "a":
            ctx.load_current_a = number
        elif "temperature" in name and "resolution" in name:
            ctx.steps["temperature_c"] = number
        elif "temperature" in name:
            low, high = ctx.ranges.get("temperature_c", (None, None))
            if "min" in name or requirement.operator == "at_most":
                low = number
            else:
                high = number
            ctx.ranges["temperature_c"] = (low, high)
        elif "led" in name and ("count" in name or "number" in name):
            ctx.led_count = int(number)
    return ctx


def to_compatibility(
    outcome: Outcome,
    required: CatalogEntry,
    offered: CatalogEntry | None,
    references: list[str | None],
) -> Compatibility:
    findings = [CompatFinding(**vars(f)) for f in outcome.findings]
    grouped = WhatChanges()
    for finding in findings:
        bucket = getattr(grouped, finding.area)
        if finding.change and finding.change not in bucket:
            bucket.append(finding.change)
    reasons = [f.message for f in findings if f.grade != "A"] or [
        "No rule found a difference between the original and the declared offer specs"
    ]
    reasons.append(
        "Rules compare the catalogue's description of the original with the seller's "
        "declared specs; catalogue values are unverified references and project wiring "
        "is not independently checked"
    )
    if outcome.grade in {"C", "D", "X"} and outcome.missing:
        reasons.append("Other specifications are unknown, so the grade may be worse")
    return Compatibility(
        status=outcome.status,
        grade=outcome.grade,
        reasons=reasons,
        missing_fields=outcome.missing,
        changes=list(dict.fromkeys(f.change for f in findings if f.change and f.grade != "A")),
        references=list(dict.fromkeys(r for r in references if r)),
        method="catalog_rules",
        grade_label=LABELS[outcome.grade] if outcome.grade else None,
        findings=findings,
        what_changes=grouped,
        required_catalog_id=required.id,
        offered_catalog_id=offered.id if offered else None,
    )


def assess_offer(
    resolution: PartResolution,
    offer: VerifiedOffer,
    project: ProjectContext | None = None,
    items=(),
    item: BomItem | None = None,
) -> Compatibility:
    """Grade an offer: catalogue rules when the BOM part is a known entry, else `assess`."""
    found = resolve_name(resolution.query)
    entry = found.entry if found.status == "matched" else None
    if entry is None:
        result = assess(resolution.specs, offer.specs)
        result.references.append(str(offer.url))
        return result
    offered, offered_entry = offered_side(offer, entry)
    context = project_context(project, items, item)
    outcome = evaluate(required_side(entry, resolution), offered, context)
    references = [entry.source, offered_entry and offered_entry.source, str(offer.url)]
    return to_compatibility(outcome, entry, offered_entry, references)


def reassess_report(report: Report | None, project: ProjectContext | None) -> None:
    """Re-grade unselected offers with project context (controller, power, other parts)."""
    if report is None or project is None:
        return
    items = [line.item for line in report.lines]
    for line in report.lines:
        if line.selected_offer_url or not line.offers:
            continue  # Never change the grade behind an existing selection.
        try:
            resolution = line.resolution or resolve_part(line.item)
        except ValueError:
            continue
        for offer in line.offers:
            offer.compatibility = assess_offer(resolution, offer, project, items, line.item)
            offer.compatibility_status = offer.compatibility.status
