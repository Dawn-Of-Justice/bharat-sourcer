"""Conservative part relevance, independent of a seller's search query."""

import re
import unicodedata

from bharat_sourcer.sourcing.part_spec import find_measures, normalise_text, same_value

FILLER = set(
    (
        "a an the of for with to and pack set pcs piece pieces compatible development "
        "board module sensor display capacitive"
    ).split()
)
ACCESSORIES = set("case holder bracket mount cover enclosure stand clip".split())
UNITS = set(
    (
        "mm cm m v mv a ma w watt watts uf nf pf mfd ohm ohms k mhz mah awg pin pins cell cells"
    ).split()
)


def compact(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold() if c.isalnum())


def _text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).replace("μ", "u").replace("µ", "u")
    text = re.sub(r"(?i)\bmfd\b", "uF", text)
    # "1.3-inch" is a size, not a "3-inch" model number.
    return re.sub(r"(?i)(\d)\s*-?\s*(?:′′|″|”|\"|inches\b|inch\b|in\.)", r"\1 inch", text)


def model_numbers(text: str) -> list[str]:
    text = re.sub(r"(?i)-channel\b", " channel", _text(text))
    text = normalise_text(text)
    for measure in find_measures(text, resistor_context=True):
        text = text.replace(measure.text, " ")
    # Join a split MPN suffix, but never swallow the following descriptive word.
    text = re.sub(r"(?i)\b([a-z]+\d+)\s+([a-z])(?=-|\b)", r"\1\2", text)
    text = re.sub(r"(?i)\b(nema|hc|sr|wroom)\s+(\d+|sr\d+)\b", r"\1\2", text)
    found = []
    for token in re.findall(r"(?i)\b[a-z0-9]+(?:-[a-z0-9]+)*\b", text):
        key = compact(token)
        if key in {"i2c", "i2s", "i3c"}:
            continue  # Interfaces are attributes, not standalone model-number queries.
        if key == "18650":
            found.append(token)
        elif len(key) >= 3 and any(c.isdigit() for c in key) and any(c.isalpha() for c in key):
            if re.fullmatch(
                r"(?i)\d+(?:mm|cm|inch|mv|v|ma|a|w|uf|nf|pf|k|ohm|mah|mhz|pin|pcs|cell|x\d+mm)", key
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
    if "18650" in text:
        for match in re.finditer(r"(?i)\b18650\s*x\s*(\d+)\b|\b(\d+)\s*x\s*18650\b", text):
            result.setdefault("cells", set()).add(float(next(v for v in match.groups() if v)))
    return result


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
    text = re.sub(r"(?i)\b(?:dual|double)\s*(?:cells?)?\b", " ", text)
    words = re.findall(r"[^\W_]+", text.casefold())
    plurals = {"switches": "switch", "inches": "inch"}
    return {
        plurals.get(w, w[:-1] if len(w) > 3 and w.endswith("s") else w)
        for w in words
        if w not in FILLER and w not in UNITS
    }


def is_accessory_for(title: str, part: str) -> bool:
    offered, wanted = _tokens(title), _tokens(part)
    accessory_words = (offered & ACCESSORIES) - wanted
    # "Surface mount" and an IC's "case" describe the component itself.
    if accessory_words - {"mount", "case"}:
        return True
    if (
        accessory_words
        and re.search(r"(?i)\bfor\b", title)
        and not re.search(r"(?i)\bsurface[- ]mount\b", title)
    ):
        return True
    # A board named as the target of a cable/shield is not the purchased board.
    return bool((offered & {"cable", "shield"}) - wanted) and bool(
        re.search(r"(?i)\b(?:for|compatible with)\b", title)
    )


def identity_conflict(part: str, title: str) -> bool:
    """High-confidence wrong-product cases, including when the AI judge is available."""
    if is_accessory_for(title, part):
        return True
    if re.search(r"(?i)\barduino\s+uno\b", part):
        # Unqualified Uno in legacy build guides refers to the AVR Uno, not R4/Q.
        wanted = re.search(r"(?i)\b(?:r[34]|rev\s*[34]|q)\b", part)
        actual = re.search(r"(?i)\b(?:r[34]|rev\s*[34]|q)\b", title)

        def normalize(m):
            return re.sub(r"rev\s*", "r", m.group().lower()) if m else "r3"

        if normalize(wanted) != normalize(actual):
            return True
    return False


def relevance(part_terms: str | list[str], title: str) -> float:
    part = part_terms if isinstance(part_terms, str) else " ".join(part_terms)
    if not title or identity_conflict(part, title):
        return 0.0
    # An unspecified DIP package may be plastic DIP; pin count and MPN must match.
    if re.search(r"(?i)\bdip[- ]?\d+\b", part):
        title = re.sub(r"(?i)\bpdip(?=[- ]?\d+\b)", "DIP", title)
    # Camera boards have different wiring and pin availability from plain dev boards.
    if re.search(r"(?i)\besp32\b", part):
        camera = r"(?i)\b(?:camera|esp32[- ]?cam|ov2640|ov5640)\b"
        if re.search(camera, title) and not re.search(camera, part):
            return 0.0
    wanted_models = {compact(m) for m in model_numbers(part)}
    actual_models = {compact(m) for m in model_numbers(title)}
    if wanted_models and not wanted_models <= actual_models:
        return 0.0
    wanted_values, actual_values = values(part), values(title)
    # A missing numeric constraint is unknown, not a positive title match. Tolerance
    # is a query qualifier; all other stated measurements need listing evidence.
    if wanted_values.keys() - actual_values.keys() - {"tolerance"}:
        return 0.0
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
