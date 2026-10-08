"""Conservative part relevance, independent of a seller's search query."""

import re
import unicodedata

from bharat_sourcer.sourcing.part_spec import find_measures, normalise_text, same_value

FILLER = set(
    ("a an the of for with to and pack set pcs piece pieces compatible development "
     "board module sensor display capacitive").split()
)
ACCESSORIES = set("case holder bracket mount cover enclosure stand clip".split())
UNITS = set(
    ("mm cm m v mv a ma w watt watts uf nf pf mfd ohm ohms k mhz mah awg "
     "pin pins cell cells inch").split()
)


def compact(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def _text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("μ", "u").replace("µ", "u")
    text = re.sub(r"(?i)\bmfd\b", "uF", text)
    text = re.sub(r"(?i)(\d)\s*(?:″|”|\"|inches\b|inch\b|in\.)", r"\1 inch", text)
    return text


def model_numbers(text: str) -> list[str]:
    text = re.sub(r"(?i)-channel\b", " channel", _text(text))
    # Join a split MPN suffix, but never swallow the following descriptive word.
    text = re.sub(r"(?i)\b([a-z]+\d+)\s+([a-z])(?=-|\b)", r"\1\2", text)
    text = re.sub(r"(?i)\b(nema|hc|sr|wroom)\s+(\d+|sr\d+)\b", r"\1\2", text)
    found = []
    for token in re.findall(r"(?i)\b[a-z0-9]+(?:-[a-z0-9]+)*\b", text):
        key = compact(token)
        if key == "18650":
            found.append(token)
        elif len(key) >= 3 and any(c.isdigit() for c in key) and any(c.isalpha() for c in key):
            if re.fullmatch(
                r"(?i)\d+(?:mm|cm|mv|v|ma|a|w|uf|nf|pf|k|ohm|mah|mhz|pin|pcs|cell|x\d+mm)", key
            ):
                continue
            if re.fullmatch(r"(?i)(?:x\d+|\d+[rkm]\d+)", key):
                continue
            found.append(token)
    return list(dict.fromkeys(found))


def values(text: str) -> dict[str, set[float]]:
    text = _text(text)
    result: dict[str, set[float]] = {}
    for measure in find_measures(text, resistor_context=True):
        result.setdefault(measure.kind, set()).add(measure.value)
    for kind, pattern in {
        "pins": r"(?i)\b(\d+)\s*-?\s*pins?\b",
        "cells": r"(?i)\b(\d+)\s*-?\s*cells?\b",
    }.items():
        for number in re.findall(pattern, text):
            result.setdefault(kind, set()).add(float(number))
    if re.search(r"(?i)\b(?:dual|double)\b", text):
        result.setdefault("cells", set()).add(2.0)
    return result


def pack_size(text: str) -> int | None:
    match = re.search(
        r"(?i)\b(?:pack|set|lot|bag)\s+of\s+(\d+)|\b(\d+)\s*(?:pcs?|pieces?|units?)\b|\bx\s*(\d+)\b",
        text,
    )
    return next(int(v) for v in match.groups() if v) if match else None


def _tokens(text: str) -> set[str]:
    text = normalise_text(_text(text))
    for measure in find_measures(text, resistor_context=True):
        text = text.replace(measure.text, " ")
    text = re.sub(
        r"(?i)\b(?:pack|set|lot|bag)\s+of\s+\d+|\b\d+\s*(?:pcs?|pieces?)\b|\bx\s*\d+\b|\d+\s*%",
        " ",
        text,
    )
    text = re.sub(r"(?i)\b(\d+)\s*-?\s*(?:pins?|cells?)\b", " ", text)
    words = re.findall(r"[^\W_]+", text.casefold())
    plurals = {"switches": "switch", "inches": "inch"}
    return {
        plurals.get(w, w[:-1] if len(w) > 3 and w.endswith("s") else w)
        for w in words
        if w not in FILLER and w not in UNITS
    }


def is_accessory_for(title: str, part: str) -> bool:
    offered, wanted = _tokens(title), _tokens(part)
    return bool((offered & ACCESSORIES) - wanted) and bool(re.search(r"(?i)\bfor\b", title))


def relevance(part_terms: str | list[str], title: str) -> float:
    part = part_terms if isinstance(part_terms, str) else " ".join(part_terms)
    if not title or is_accessory_for(title, part):
        return 0.0
    wanted_models = {compact(m) for m in model_numbers(part)}
    actual_models = {compact(m) for m in model_numbers(title)}
    if wanted_models and not wanted_models <= actual_models:
        return 0.0
    wanted_values, actual_values = values(part), values(title)
    for kind in wanted_values.keys() & actual_values.keys():
        if not all(any(same_value(a, b) for b in actual_values[kind]) for a in wanted_values[kind]):
            return 0.0
    # Remove model spellings from noun tokens after comparing their compact identities.
    for model in model_numbers(part):
        part = re.sub(r"[-\s]*".join(re.escape(c) for c in compact(model)), " ", part, flags=re.I)
    expected, actual = _tokens(part), _tokens(title)
    actual |= {compact(m) for m in model_numbers(title)}
    if not expected:
        return 1.0 if wanted_models or wanted_values else 0.0
    return len(expected & actual) / len(expected)


def title_gate(query: str | None, title: str) -> bool:
    return query is None or relevance(query, title) >= 0.8
