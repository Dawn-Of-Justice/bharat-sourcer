"""Conservative, deterministic comparison of declared module specifications."""

import re

from bharat_sourcer.schemas import (
    BomItem,
    Clarification,
    Compatibility,
    PartResolution,
    PartSpecs,
    SpecEvidence,
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
    inferred = parse_name(item.raw_name)
    declared = item.specs.model_dump(exclude_none=True)
    specs = PartSpecs(**(inferred.model_dump(exclude_none=True) | declared))
    evidence = [
        SpecEvidence(
            field=field,
            value=str(value),
            source="user" if field in declared else "part_name",
            locator=f"bom:{item.line_id}",
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
    if specs.family is None and not item.requirements:
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
