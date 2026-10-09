"""Curated code changes for catalogue substitutes (tier 1 of docs/plans/code-adapt).

Recipes in `data/code_recipes.json` implement the `code` changes of one substitute edge
for one library. They are pure text edits applied outside comments and string literals.
A required step that matches nothing, or more places than it allows, refuses the whole
recipe, and so does a `refuse_if` step that finds a form the recipe cannot change safely
(for example a humidity reading on a sensor without humidity): a curated patch is either
exactly what the recipe describes or absent, with a reason. Wiring, power and verification
changes are never patched; they become notes, and a refused recipe lists every catalogue
change as a note because nothing was patched. Nothing here compiles code or calls a model.
"""

import difflib
import json
import re
from dataclasses import dataclass, field
from functools import cache
from importlib import resources
from posixpath import basename

from bharat_sourcer.catalog import load_catalog

CODE_SUFFIXES = (".ino", ".cpp", ".c", ".h", ".hpp", ".py")
BUILD_FILES = {"platformio.ini", "library.json", "library.properties"}


@dataclass
class FilePatch:
    path: str
    original: str
    patched: str
    diff: str


@dataclass
class PatchResult:
    ok: bool
    files: list[FilePatch] = field(default_factory=list)
    applied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    reason: str | None = None
    detail: str | None = None


@cache
def recipes() -> dict[tuple[str, str], dict]:
    data = json.loads(
        resources.files("bharat_sourcer").joinpath("data/code_recipes.json").read_text("utf-8")
    )
    return {(r["from_id"], r["to_id"]): r for r in data["recipes"]}


def recipe_for(from_id: str | None, to_id: str | None) -> dict | None:
    return recipes().get((from_id, to_id)) if from_id and to_id else None


def edge_changes(from_id: str, to_id: str) -> list[tuple[str, str]]:
    """(area, text) for a catalogue substitute edge, or [] when the edge is not curated."""
    entry = load_catalog().get(from_id)
    edge = next((s for s in (entry.substitutes if entry else []) if s.id == to_id), None)
    return [(change.area, change.text) for change in edge.changes] if edge else []


def is_code(path: str) -> bool:
    return path.casefold().endswith(CODE_SUFFIXES)


def is_build(path: str) -> bool:
    return basename(path).casefold() in BUILD_FILES


def code_mask(text: str, python: bool) -> list[bool]:
    """True for characters that are code, False inside comments and string literals."""
    mask = [True] * len(text)
    i, n = 0, len(text)
    while i < n:
        two = text[i : i + 2]
        char = text[i]
        if not python and two == "//" or python and char == "#":
            end = text.find("\n", i)
            end = n if end == -1 else end
        elif not python and two == "/*":
            end = text.find("*/", i + 2)
            end = n if end == -1 else end + 2
        elif python and text[i : i + 3] in ('"""', "'''"):
            quote = text[i : i + 3]
            end = text.find(quote, i + 3)
            end = n if end == -1 else end + 3
        elif char in "\"'":
            end = i + 1
            while end < n and text[end] != char and text[end] != "\n":
                end += 2 if text[end] == "\\" else 1
            end = min(end + 1, n)
        else:
            i += 1
            continue
        for k in range(i, end):
            mask[k] = False
        i = end
    return mask


def code_matches(pattern: re.Pattern, text: str, python: bool) -> list[re.Match]:
    mask = code_mask(text, python)
    return [m for m in pattern.finditer(text) if all(mask[m.start() : m.end()])]


def substitute(text: str, matches: list[re.Match], replacement) -> str:
    out, last = [], 0
    for match in matches:
        out.append(text[last : match.start()])
        out.append(replacement(match))
        last = match.end()
    out.append(text[last:])
    return "".join(out)


def apply_step(step: dict, files: dict[str, str]) -> tuple[dict[str, str], int]:
    """Apply one step to every eligible file; returns (changed texts, total matches)."""
    kind = step["kind"]
    changed, total = {}, 0
    for path, text in files.items():
        python = path.casefold().endswith(".py")
        if kind == "replace_include":
            if not is_code(path):
                continue
            pattern = re.compile(
                r"^(\s*#\s*include\s*[<\"])" + re.escape(step["from"]) + r"([>\"])", re.M
            )
            matches = list(pattern.finditer(text))
            new = substitute(text, matches, lambda m: m.group(1) + step["to"] + m.group(2))
        elif kind in {"replace_identifier", "replace_regex"}:
            if step.get("files", "code") == "code" and not is_code(path):
                continue
            if kind == "replace_identifier":
                pattern = re.compile(r"\b" + re.escape(step["from"]) + r"\b")
                matches = code_matches(pattern, text, python)
                new = substitute(text, matches, lambda m: step["to"])
            else:
                pattern = re.compile(step["pattern"])
                matches = code_matches(pattern, text, python)
                new = substitute(text, matches, lambda m: m.expand(step["replacement"]))
        elif kind == "replace_lib_dep":
            if not is_build(path):
                continue
            # The old library's version constraint does not apply to the new library, so it
            # is dropped; commented-out lines (; or #) are left alone.
            pattern = re.compile(
                r"^(?![ \t]*[;#])([^\n]*?)"
                + re.escape(step["from"])
                + r"(?:[ \t]*@[ \t]*[^\s,;\"']+)?",
                re.I | re.M,
            )
            matches = list(pattern.finditer(text))
            new = substitute(text, matches, lambda m: m.group(1) + step["to"])
        elif kind == "refuse_if":
            if not is_code(path):
                continue
            matches = code_matches(re.compile(step["pattern"], re.M), text, python)
            new = text
        elif kind == "insert_after":
            if not is_code(path):
                continue
            anchor = re.compile(step["anchor"], re.M)
            matches = [
                m
                for m in code_matches(anchor, text, python)
                if not re.search(step["skip_if"].format(**m.groupdict()), text)
            ]
            new = substitute(
                text, matches, lambda m: m.group(0) + "\n" + step["insert"].format(**m.groupdict())
            )
        else:
            raise ValueError(f"Unknown recipe step: {kind}")
        if matches:
            total += len(matches)
            changed[path] = new
    return changed, total


def unified(path: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
        )
    )


def notes_for(from_id: str, to_id: str, recipe: dict | None) -> list[str]:
    """Every catalogue change this recipe does not implement, labelled by area."""
    implemented = set(recipe.get("implements", [])) if recipe else set()
    notes = []
    for area, text in edge_changes(from_id, to_id):
        if area == "code" and text in implemented:
            continue
        label = {"code": "Code (not patched)"}.get(area, area.capitalize())
        notes.append(f"{label}: {text}")
    return notes


def apply_recipe(files: dict[str, str], from_id: str, to_id: str) -> PatchResult:
    """Apply the curated recipe for a substitute edge to the project's code files."""
    recipe = recipe_for(from_id, to_id)
    notes = notes_for(from_id, to_id, recipe)
    if recipe is None:
        return PatchResult(
            False,
            notes=notes,
            reason="recipe_not_applicable",
            detail="No curated code recipe exists for this substitute.",
        )
    if recipe.get("no_code_change"):
        return PatchResult(
            False, notes=notes, reason="no_code_change_needed", detail=recipe["no_code_change"]
        )

    def refuse(reason: str, detail: str, **extra) -> PatchResult:
        # Nothing was patched, so every catalogue change (code included) stays a note.
        return PatchResult(
            False, notes=notes_for(from_id, to_id, None), reason=reason, detail=detail, **extra
        )

    if not files:
        return refuse("no_code", "No code files from this project could be read.")
    wanted = {h.casefold() for h in recipe.get("requires_any_include", [])}
    includes = {
        m.group(1).casefold()
        for path, text in files.items()
        if is_code(path)
        for m in re.finditer(r'^\s*#\s*include\s*[<"]([^>"]+)[>"]', text, re.M)
    }
    if wanted and not wanted & includes:
        return refuse(
            "recipe_not_applicable",
            f"The code does not use the library this recipe covers ({recipe['library']}).",
        )
    current = dict(files)
    applied, skipped = [], []
    for step in recipe["steps"]:
        changed, count = apply_step(step, current)
        if step["kind"] == "refuse_if":
            if count:
                return refuse(
                    "recipe_not_applicable",
                    f"The code uses a form this recipe does not change: '{step['describe']}' "
                    f"({count} place{'s' if count != 1 else ''}).",
                )
            continue
        limit = step.get("max_matches", 10)
        if count > limit:
            return refuse(
                "recipe_not_applicable",
                f"Ambiguous: '{step['describe']}' matched {count} places (limit {limit}).",
            )
        if count == 0:
            if step.get("required"):
                return refuse(
                    "recipe_not_applicable",
                    f"The code is not in the form this recipe expects: "
                    f"'{step['describe']}' found nothing to change.",
                )
            skipped.append(f"{step['describe']}: not used in this code")
            continue
        current.update(changed)
        applied.append(f"{step['describe']} ({count} change{'s' if count != 1 else ''})")
    patched = [
        FilePatch(path, files[path], current[path], unified(path, files[path], current[path]))
        for path in files
        if current[path] != files[path]
    ]
    if not patched:
        return refuse(
            "recipe_not_applicable", "The recipe made no changes to this code.", skipped=skipped
        )
    return PatchResult(True, files=patched, applied=applied, skipped=skipped, notes=notes)
