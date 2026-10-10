"""Separate schematic references from purchasable component identities."""

import re

from bharat_sourcer.schemas import BuyableSpec

REFERENCE = r"(?:VR|IC|ZD|PZ|R|C|D|Q|T|U|L|J|SW)\d+"
REFERENCES = rf"{REFERENCE}(?:\s*[,/]\s*{REFERENCE})*"


def without_reference(name: str) -> str:
    # Only whole labels and explicit parenthesized annotations: Uno R3 is a model.
    if re.fullmatch(REFERENCES, name.strip(), re.I):
        return ""
    return re.sub(rf"\s*\({REFERENCES}\)\s*$", "", name, flags=re.I).strip()


def sourcing_name(name: str, spec: BuyableSpec) -> str:
    clean = without_reference(name)
    if clean:
        return clean
    category = spec.category.replace("_", " ")
    values = [
        p.value
        for p in spec.params
        if p.origin in {"stated", "user"}
        and p.operator == "equals"
        and p.name in {"resistance", "capacitance", "ic_part_number", "buzzer_type", "diode_type"}
    ]
    # A potentiometer is not interchangeable with a fixed resistor.
    if re.fullmatch(r"VR\d+", name.strip(), re.I):
        category = "potentiometer"
    return " ".join([*values, category if category != "other" else ""]).strip() or name
