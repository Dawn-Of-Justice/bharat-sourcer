"""Deterministic evidence fusion, look-alike warnings and confidence for extracted BOMs.

Each input group is one source's BOM (a video, a project page, a README, or the hints read
from a repository's code). Lines from different groups that name the same part are merged
so the line keeps every source's evidence; lines are never merged within one group.
Disagreements are kept as structured `conflicts` instead of being picked silently. No
model is involved; see docs/contracts/multi-source-intake.md for the rules.
"""

import json
import re
import unicodedata
from dataclasses import dataclass, field
from functools import cache
from importlib import resources

from bharat_sourcer.evaluation import name_match, tokens
from bharat_sourcer.schemas import (
    BomItem,
    ConflictValue,
    Evidence,
    ItemConflict,
    Lookalike,
)

MAX_ITEMS = 100
MAX_EVIDENCE = 20
MAX_REQUIREMENTS = 20
# Number-plus-unit words such as 420mah or 12v are specifications, not part numbers.
SPEC_WORD = re.compile(r"\d+(?:v|mv|a|ma|mah|w|mw|k|ohm|ohms|uf|nf|pf|mm|cm|m|mhz|ghz|hz|g|kg)")


def compact(name: str) -> str:
    """Lowercase name with '-' and '_' removed and other punctuation turned into spaces."""
    text = unicodedata.normalize("NFKC", name).casefold().replace("-", "").replace("_", "")
    return " ".join(re.sub(r"[^0-9a-z]", " ", text).split())


def model_codes(name: str) -> set[str]:
    """Part-number-like words (letters and digits, 4+ characters): ESP32-S3 -> esp32s3."""
    codes = set()
    for word in compact(name).split():
        if (
            len(word) >= 4
            and re.search(r"[a-z]", word)
            and re.search(r"\d", word)
            and not SPEC_WORD.fullmatch(word)
        ):
            codes.add(word)
    return codes


@cache
def lookalike_groups() -> list[dict]:
    data = json.loads(
        resources.files("bharat_sourcer").joinpath("data/lookalikes.json").read_text("utf-8")
    )
    groups = []
    for group in data["groups"]:
        members = [(m["name"], re.compile(m["pattern"])) for m in group["members"]]
        pattern = re.compile(group["pattern"]) if group.get("pattern") else None
        groups.append(
            {"id": group["id"], "note": group["note"], "members": members, "any": pattern}
        )
    return groups


def group_members(name: str) -> dict[str, set[str]]:
    """Look-alike group id -> member names the part name matches (empty set: group only)."""
    text = compact(name)
    found = {}
    for group in lookalike_groups():
        matched = {member for member, pattern in group["members"] if pattern.search(text)}
        if matched or (group["any"] and group["any"].search(text)):
            found[group["id"]] = matched
    return found


def table_lookalikes(name: str) -> list[Lookalike]:
    notes = {group["id"]: group for group in lookalike_groups()}
    result = []
    for group_id, matched in group_members(name).items():
        group = notes[group_id]
        for member, _ in group["members"]:
            if member not in matched:
                result.append(Lookalike(name=member, note=group["note"], origin="table"))
    return result


@dataclass
class Entry:
    item: BomItem
    groups: set[int]
    # Names each source kind used for this line, for code confirmation of look-alikes.
    names: list[tuple[str, str]] = field(default_factory=list)


def source_kind(item: BomItem) -> str:
    return item.evidence[0].source if item.evidence else "video"


def relation(a: str, b: str) -> tuple[int, str] | None:
    """Score and kind of match between two part names; None when they are different parts."""
    groups_a, groups_b = group_members(a), group_members(b)
    for group_id in groups_a.keys() & groups_b.keys():
        left, right = groups_a[group_id], groups_b[group_id]
        if left and right:
            return (5, "same") if left & right else (1, "lookalike")
    codes_a, codes_b = model_codes(a), model_codes(b)
    if codes_a & codes_b:
        return 4, "same"
    if codes_a and codes_b:
        return None
    kind = name_match(a, b) or name_match(b, a)
    if kind == "exact":
        return 3, "same"
    if kind == "contains":
        return 2, "same"
    return None


def conflict_value(item: BomItem, value: str) -> ConflictValue:
    evidence = item.evidence[0] if item.evidence else None
    locator = None
    if evidence is not None:
        locator = (
            evidence.timestamp
            or (f"{evidence.file}:{evidence.line}" if evidence.file else None)
            or evidence.quote
        )
    return ConflictValue(
        value=value[:200],
        source=evidence.source if evidence else "video",
        url=evidence.url if evidence else None,
        locator=locator[:300] if locator else None,
    )


def merge(entry: Entry, item: BomItem, kind: str, group: int) -> None:
    target = entry.item
    entry.groups.add(group)
    entry.names.append((source_kind(item), item.raw_name))
    if kind == "lookalike":
        target.conflicts.append(
            ItemConflict(
                kind="identity_mismatch",
                message=(
                    f"Sources name different parts: {target.raw_name} and {item.raw_name}. "
                    "Check which one this build uses."
                )[:500],
                values=[
                    conflict_value(target, target.raw_name),
                    conflict_value(item, item.raw_name),
                ],
            )
        )
    elif (
        not model_codes(target.raw_name)
        and model_codes(item.raw_name)
        and set(tokens(target.raw_name)) < set(tokens(item.raw_name))
    ):
        # A generic name ("ultrasonic sensor") takes the part number another source names.
        target.raw_name = item.raw_name
    if target.qty_source == "stated" and item.qty_source == "stated":
        if target.qty != item.qty:
            target.conflicts.append(
                ItemConflict(
                    kind="qty_mismatch",
                    message=f"Sources state different quantities ({target.qty} and "
                    f"{item.qty}); kept {target.qty}. Check the count.",
                    values=[
                        conflict_value(target, str(target.qty)),
                        conflict_value(item, str(item.qty)),
                    ],
                )
            )
    elif item.qty_source == "stated":
        target.qty, target.qty_source, target.qty_reason = item.qty, "stated", None
    seen = {(e.source, e.timestamp, e.quote, str(e.url)) for e in target.evidence}
    for evidence in item.evidence:
        key = (evidence.source, evidence.timestamp, evidence.quote, str(evidence.url))
        if key not in seen and len(target.evidence) < MAX_EVIDENCE:
            target.evidence.append(evidence)
            seen.add(key)
    names = {requirement.name.casefold() for requirement in target.requirements}
    for requirement in item.requirements:
        if requirement.name.casefold() not in names and len(target.requirements) < MAX_REQUIREMENTS:
            target.requirements.append(requirement)
            names.add(requirement.name.casefold())
    known = {lookalike.name.casefold() for lookalike in target.lookalikes}
    for lookalike in item.lookalikes:
        if lookalike.name.casefold() not in known:
            target.lookalikes.append(lookalike)
            known.add(lookalike.name.casefold())


def origin(evidence: Evidence) -> str:
    if evidence.source == "video":
        return "video"
    if evidence.source in ("code", "youtube_description"):
        return evidence.source
    return str(evidence.url)


def code_confirms(entry: Entry) -> bool:
    """True when a code-derived name pins the line to one member of each look-alike group."""
    groups = group_members(entry.item.raw_name)
    code_names = [name for kind, name in entry.names if kind == "code"]
    if not code_names or not groups:
        return False
    for group_id, matched in groups.items():
        confirmed = False
        for name in code_names:
            members = group_members(name).get(group_id, set())
            if len(members) == 1 and (not matched or members <= matched):
                confirmed = True
        if not confirmed:
            return False
    return True


def assess(entry: Entry) -> None:
    """Deterministic confidence from evidence: check > verified > likely (first rule wins)."""
    item = entry.item
    origins = {origin(evidence) for evidence in item.evidence}
    if not item.evidence:
        level, reason = "check", "No source evidence for this line; it was inferred or added."
    elif item.conflicts:
        level, reason = "check", "Sources disagree about this line; review the conflict."
    elif item.lookalikes and not code_confirms(entry):
        names = ", ".join(lookalike.name for lookalike in item.lookalikes[:3])
        level, reason = "check", f"Easily confused with {names}; confirm the exact part."
    elif "code" in origins:
        level, reason = "verified", "The project code uses a library or board for this part."
    elif len(origins) >= 2:
        level, reason = "verified", f"{len(origins)} sources agree on this part."
    elif "video" in origins:
        level, reason = "likely", "One source: model-reported video timestamps."
    elif "youtube_description" in origins:
        level, reason = "likely", "One source: a quote checked in the video description."
    else:
        level, reason = "likely", "One source: a quote checked on the page."
    item.confidence, item.confidence_reason = level, reason[:300]


def fuse(groups: list[list[BomItem]]) -> list[BomItem]:
    """Merge per-source BOMs, add table look-alikes and assess confidence.

    Lines of the first group keep their order and names; later groups merge into the best
    matching line (one line per source, strongest match first, ties by order) or are
    appended. Line ids are renumbered L01, L02, ...
    """
    entries: list[Entry] = []
    for index, items in enumerate(groups):
        items = [item.model_copy(deep=True) for item in items]
        candidates = []
        for i, entry in enumerate(entries):
            for j, item in enumerate(items):
                found = relation(entry.item.raw_name, item.raw_name)
                if found:
                    candidates.append((-found[0], i, j, found[1]))
        candidates.sort()
        used_entries, used_items = set(), set()
        for _, i, j, kind in candidates:
            if i in used_entries or j in used_items or index in entries[i].groups:
                continue
            merge(entries[i], items[j], kind, index)
            used_entries.add(i)
            used_items.add(j)
        for j, item in enumerate(items):
            if j not in used_items:
                entries.append(Entry(item, {index}, [(source_kind(item), item.raw_name)]))
    result = []
    for number, entry in enumerate(entries[:MAX_ITEMS], start=1):
        item = entry.item
        item.line_id = f"L{number:02d}"
        known = {lookalike.name.casefold() for lookalike in item.lookalikes}
        own = {name.casefold() for name in model_codes(item.raw_name)}
        for lookalike in table_lookalikes(item.raw_name):
            if lookalike.name.casefold() not in known and len(item.lookalikes) < 10:
                item.lookalikes.append(lookalike)
                known.add(lookalike.name.casefold())
        # A model-named look-alike that is the line's own part number is not a look-alike.
        item.lookalikes = [
            lookalike
            for lookalike in item.lookalikes
            if not (model_codes(lookalike.name) and model_codes(lookalike.name) <= own)
        ]
        assess(entry)
        result.append(item)
    return result
