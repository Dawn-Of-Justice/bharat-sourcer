"""Bounded catalogue query ladder; every rung retains the original scoring terms."""

import re
import unicodedata

from bharat_sourcer.part_identity import without_reference
from bharat_sourcer.sourcing.textmatch import compact, model_numbers


class Rung(str):
    """A search string with routing metadata; also serialises as an ordinary string."""

    query: str
    kind: str
    part_terms: str

    def __new__(cls, query: str, kind: str, part_terms: str):
        obj = super().__new__(cls, query)
        obj.query, obj.kind, obj.part_terms = query, kind, part_terms
        return obj


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("µ", "u").replace("μ", "u")
    text = re.sub(r"(\d)\s*[Ωω]", r"\1 ohm", text)
    text = text.replace("Ω", " ").replace("ω", " ").lower()
    text = "".join(c if unicodedata.category(c)[0] in "LMN" or c in " .-/" else " " for c in text)
    return " ".join(text.split()).strip(" .-/")


def clean_name(name: str) -> str:
    name = re.sub(
        r"(?i)\b(?:pack|set|lot|bag)\s+of\s+\d+|\b\d+\s*(?:pcs?|pieces?)\b|\bx\s*\d+\b|^\s*\d+\s*x\s+|[±+]?\s*\d+(?:\.\d+)?\s*%",
        " ",
        name,
    )
    name = re.sub(r"[\[(]([^\])]+)[\])]", lambda m: m[1] if model_numbers(m[1]) else " ", name)
    name = re.sub(r"(?i)\bcompatible\b", " ", name)
    return normalise(name)


NOUNS = set(
    (
        "resistor capacitor wire wires jumper led diode switch button motor stepper servo holder "
        "battery breadboard board module sensor display oled mosfet transistor regulator driver "
        "strip arduino raspberry pico connector relay potentiometer thermistor inductor buzzer "
        "fuse crystal oscillator"
    ).split()
)
JUNK = set(
    (
        "to for with of and male female red blue green clear compatible solid core "
        "ohm awg watt watts v w a mm cm uf nf pf"
    ).split()
)


def route_queries(spec, raw_name: str, resolution_query: str) -> list[Rung]:
    """Model spellings, spec queries, cleaned names, value/category, then synonyms."""
    raw_name = without_reference(raw_name)
    resolution_query = without_reference(resolution_query)
    spec_name = without_reference(getattr(spec, "part_name", "") or "")
    part_terms = raw_name or spec_name or resolution_query
    names = [raw_name, resolution_query, spec_name]
    proposals = []
    for name in names:
        for model in model_numbers(clean_name(name)):
            proposals.append((model, "model"))
            if "-" in model:
                proposals.extend([(compact(model), "model"), (model.replace("-", " "), "model")])
            elif re.match(r"(?i)^nema\d+$", model):
                proposals.append((re.sub(r"(?<=\D)(?=\d)", " ", model), "model"))
    proposals.extend((q, "spec") for q in getattr(spec, "queries", []))
    proposals.extend((clean_name(n), "name") for n in names)
    for name in names:
        words = clean_name(name).split()
        nouns = [w for w in words if w in NOUNS]
        value = next(
            (w for w in words if any(c.isdigit() for c in w) and w not in model_numbers(name)), None
        )
        if nouns and value:
            proposals.append((" ".join([value, *nouns]), "value_category"))
    proposals.extend((q, "synonym") for q in getattr(spec, "synonyms", []))
    result, seen = [], set()
    for text, kind in proposals:
        query = clean_name(text)
        words = query.split()
        models = model_numbers(query)
        if not query or query in seen or (len(words) == 1 and not models):
            continue
        # Known nouns, models, or words in non-Latin scripts identify a part.
        if not models and not any(
            w in NOUNS or (w not in JUNK and any(ord(c) > 127 and c.isalpha() for c in w))
            for w in words
        ):
            continue
        seen.add(query)
        result.append(Rung(query, kind, part_terms))
    return result
