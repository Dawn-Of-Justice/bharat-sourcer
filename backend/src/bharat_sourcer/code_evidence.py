"""Deterministic part hints from a public GitHub repository's code and build files.

Besides the README, a bounded set of files is read from the same public
`raw.githubusercontent.com` endpoint through the guarded fetcher: `platformio.ini`,
`library.json`, `requirements.txt`, the usual Arduino, PlatformIO, CircuitPython and
MicroPython entry points, and code files the README links to. When the repository has no
README, or none of those guesses is a code file, the file list comes from the repository
tree (one GitHub REST `git/trees/HEAD` request through the same fetcher, robots and size
limits). `#include` lines, Python imports, `lib_deps`/dependencies and `board =` targets
are mapped to part hints with the curated `data/library_parts.json` table. No model is
involved, every hint cites `file:line`, and code never establishes how many of a part the
build uses.

A deep read (no README, or a README that names no parts) also reads up to
`MAX_SCHEMATICS` KiCad schematics (`*.kicad_sch`) from the tree. Each placed symbol that is
fitted and on the BOM becomes a line named by its value and designator kind, counted by its
references, and citing the `Value` property line. Test points, power flags and
do-not-fit symbols are skipped.
"""

import json
import re
from functools import cache
from importlib import resources
from posixpath import basename
from typing import Protocol
from urllib.parse import unquote, urlsplit

from bharat_sourcer.schemas import BomItem, Evidence
from bharat_sourcer.sourcing.fetch import FetchError, Page

RAW_HOST = "raw.githubusercontent.com"
API_HOST = "api.github.com"
TREE_BYTES = 1_000_000
MAX_TREE_ENTRIES = 5000
# Vendored libraries, build output and docs are not the project's own code.
SKIP_DIRS = {
    "archive",
    "archived",
    "legacy",
    "superseded",
    ".git",
    ".github",
    ".pio",
    ".vscode",
    "build",
    "doc",
    "docs",
    "examples",
    "lib",
    "libraries",
    "node_modules",
    "test",
    "tests",
    "vendor",
}
CODE_FILE_BYTES = 200_000
MAX_CODE_FILES = 8
MAX_LINES = 5000
MAX_CODE_ITEMS = 30
MAX_EVIDENCE = 5
CODE_SUFFIXES = (".ino", ".cpp", ".c", ".h", ".hpp", ".py")
SCHEMATIC_SUFFIX = ".kicad_sch"
SCHEMATIC_BYTES = 1_000_000
MAX_SCHEMATICS = 3
MAX_SCHEMATIC_ITEMS = 40
MAX_REFS_IN_NAME = 6
LIB_ID = re.compile(r'^\s*\(lib_id\s+"([^"]{1,200})"')
PROPERTY = re.compile(r'^\s*\(property\s+"([^"]{1,60})"\s+"([^"]{0,200})"')
FLAG = re.compile(r"^\s*\((in_bom|dnp|exclude_from_bom)\s+(yes|no)\)")
REFERENCE = re.compile(r"^([A-Z]+)\d+$")
# Designator prefixes (IEEE 315 / KiCad convention) to a part kind for the line name.
DESIGNATORS = {
    "R": "resistor",
    "C": "capacitor",
    "L": "inductor",
    "D": "diode",
    "Q": "transistor",
    "SW": "switch",
    "S": "switch",
    "J": "connector",
    "P": "connector",
    "Y": "crystal",
    "X": "crystal",
    "F": "fuse",
    "BT": "battery",
    "LS": "speaker",
    "SP": "speaker",
    "BZ": "buzzer",
    "K": "relay",
}
# KiCad libraries of generic symbols, whose default value is just the symbol name ('R').
GENERIC_LIBRARIES = {"device", "connector", "connector_generic", "switch"}
# Library symbols that are board features, not parts to buy.
NOT_PARTS = ("testpoint", "mountinghole", "fiducial", "pwr_flag", "net_tie", "logo")
BUILD_FILES = {"platformio.ini", "library.json", "requirements.txt"}
PATH_SEGMENT = re.compile(r"[A-Za-z0-9._~ +-]{1,100}")
QTY_REASON = "Code names the library or board, not how many are used; assumed one."

INCLUDE = re.compile(r'^\s*#\s*include\s*[<"]([^>"]{1,200})[>"]')
PY_IMPORT = re.compile(r"^\s*import\s+([\w.]+(?:\s*,\s*[\w.]+)*)")
PY_FROM = re.compile(r"^\s*from\s+([\w.]+)\s+import\b")
INI_KEY = re.compile(r"^\s*([A-Za-z_][\w.-]*)\s*=\s*(.*)$")
REQUIREMENT = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)")


class Fetcher(Protocol):
    def get(self, url: str, *, robots: bool = True, max_bytes: int = 2_000_000) -> Page: ...


@cache
def library_map() -> dict:
    """Lookup tables built from the curated library map (hints, not verified parts)."""
    data = json.loads(
        resources.files("bharat_sourcer").joinpath("data/library_parts.json").read_text("utf-8")
    )
    headers, python, libraries = {}, {}, {}
    for part in data["parts"]:
        for header in part["headers"]:
            headers[header.casefold()] = part["name"]
        for module in part["python"]:
            python[module.casefold()] = part["name"]
        for library in part["libraries"]:
            libraries[library] = part["name"]
    boards = {board.casefold(): name for board, name in data["boards"].items()}
    return {"headers": headers, "python": python, "libraries": libraries, "boards": boards}


def squash(text: str) -> str:
    return re.sub(r"[^0-9a-z]", "", text.casefold())


def library_part(dependency: str) -> str | None:
    """Part for a PlatformIO/library.json dependency name, by its longest known fragment."""
    # Drop version pins, owners and URL paths: "adafruit/Adafruit BME280 Library@^2.2".
    name = dependency.split("@", maxsplit=1)[0].strip().rstrip("/").removesuffix(".git")
    name = squash(name.rsplit("/", 1)[-1])
    matches = [key for key in library_map()["libraries"] if key in name]
    return library_map()["libraries"][max(matches, key=len)] if matches else None


def python_part(module: str) -> str | None:
    return library_map()["python"].get(module.split(".", maxsplit=1)[0].casefold())


def requirement_part(line: str) -> str | None:
    match = REQUIREMENT.match(line)
    if not match:
        return None
    name = match.group(1).casefold().replace("-", "_").replace(".", "_")
    for prefix, module_prefix in (("adafruit_circuitpython_", "adafruit_"), ("micropython_", "")):
        if name.startswith(prefix):
            name = module_prefix + name.removeprefix(prefix)
    return python_part(name)


def uncommented(lines: list[str], hash_comments: bool):
    """Yield (number, line) for lines outside /* */ blocks; whole-line comments are dropped."""
    in_block = False
    for number, line in enumerate(lines[:MAX_LINES], start=1):
        stripped = line.strip()
        if in_block:
            if "*/" in stripped:
                in_block = False
            continue
        if not hash_comments and stripped.startswith("/*"):
            in_block = "*/" not in stripped[2:]
            continue
        if stripped.startswith("//") or (hash_comments and stripped.startswith((";", "#"))):
            continue
        yield number, line


def scan(path: str, text: str) -> list[tuple[str, int, str, str]]:
    """Deterministic hints in one file: (part name, line number, line text, what matched)."""
    lines = text.splitlines()
    name = basename(path).casefold()
    hints = []
    tables = library_map()
    if name.endswith((".ino", ".cpp", ".c", ".h", ".hpp")):
        for number, line in uncommented(lines, hash_comments=False):
            match = INCLUDE.match(line)
            part = match and tables["headers"].get(basename(match.group(1)).casefold())
            if match and basename(match.group(1)).casefold() in {"irremote.h", "irremote.hpp"}:
                active = "\n".join(value for _, value in uncommented(lines, hash_comments=False))
                receiver = bool(re.search(r"\b(?:IrReceiver|IRrecv)\b", active))
                sender = bool(re.search(r"\b(?:IrSender|IRsend)\b", active))
                if sender:
                    hints.append(("IR LED", number, line, "uses IR transmit API"))
                if not receiver:
                    part = None
            if part:
                hints.append((part, number, line, f"includes {basename(match.group(1))}"))
    elif name.endswith(".py"):
        for number, line in uncommented(lines, hash_comments=True):
            modules = []
            if match := PY_FROM.match(line):
                modules = [match.group(1)]
            elif match := PY_IMPORT.match(line):
                modules = [module.strip() for module in match.group(1).split(",")]
            for module in modules:
                if part := python_part(module):
                    hints.append((part, number, line, f"imports {module}"))
    elif name == "platformio.ini":
        in_deps = False
        for number, line in uncommented(lines, hash_comments=True):
            key = INI_KEY.match(line)
            if key and not line[:1].isspace():
                in_deps = key.group(1) == "lib_deps"
                if key.group(1) == "board":
                    board = key.group(2).split(";")[0].strip()
                    if part := tables["boards"].get(board.casefold()):
                        hints.append((part, number, line, f"targets board {board}"))
                values = key.group(2) if in_deps else ""
            elif in_deps and line[:1].isspace():
                values = line
            else:
                in_deps, values = False, ""
            for value in values.split(","):
                if value.strip() and (part := library_part(value.strip())):
                    hints.append((part, number, line, f"depends on {value.strip()}"))
    elif name == "requirements.txt":
        for number, line in uncommented(lines, hash_comments=True):
            if part := requirement_part(line):
                hints.append((part, number, line, f"requires {line.strip()}"))
    elif name == "library.json":
        try:
            dependencies = json.loads(text).get("dependencies") or []
        except (ValueError, AttributeError):
            return []
        if isinstance(dependencies, dict):
            dependencies = list(dependencies)
        names = [entry.get("name") if isinstance(entry, dict) else entry for entry in dependencies]
        for dependency in (value for value in names if isinstance(value, str)):
            part = library_part(dependency)
            number = next((n for n, line in enumerate(lines, start=1) if dependency in line), None)
            if part and number:
                hints.append((part, number, lines[number - 1], f"depends on {dependency}"))
    return hints


def safe_path(path: str) -> str | None:
    segments = [segment for segment in unquote(path).strip("/").split("/") if segment]
    if not segments or len(segments) > 8:
        return None
    if any(seg in {".", ".."} or not PATH_SEGMENT.fullmatch(seg) for seg in segments):
        return None
    return "/".join(segments)


def wanted(path: str) -> bool:
    name = basename(path).casefold()
    return name in BUILD_FILES or name.endswith(CODE_SUFFIXES)


def schematic(path: str) -> bool:
    return path.casefold().endswith(SCHEMATIC_SUFFIX)


def placed_symbols(text: str) -> list[dict]:
    """Fitted, on-BOM symbols placed in a KiCad 6+ schematic, one per reference.

    Library definitions (under `lib_symbols`) have no `lib_id`, so only placed symbols are
    collected; multi-unit symbols repeat a reference and are kept once.
    """
    symbols: list[dict] = []
    current: dict | None = None
    for number, line in enumerate(text.splitlines()[: MAX_LINES * 20], start=1):
        if match := LIB_ID.match(line):
            current = {"lib_id": match.group(1), "props": {}, "flags": {}}
            symbols.append(current)
        elif current is None:
            continue
        elif match := PROPERTY.match(line):
            current["props"].setdefault(match.group(1), (match.group(2), number, line))
        elif match := FLAG.match(line):
            current["flags"].setdefault(match.group(1), match.group(2))
    placed: list[dict] = []
    seen: set[str] = set()
    for symbol in symbols:
        reference = symbol["props"].get("Reference", ("", 0, ""))[0]
        value = symbol["props"].get("Value")
        flags = symbol["flags"]
        lib = symbol["lib_id"].casefold()
        if (
            not reference
            or reference.startswith("#")
            or value is None
            or not value[0].strip()
            or reference in seen
            or flags.get("in_bom") == "no"
            or flags.get("exclude_from_bom") == "yes"
            or flags.get("dnp") == "yes"
            or lib.startswith("power:")
            or any(word in lib for word in NOT_PARTS)
        ):
            continue
        seen.add(reference)
        placed.append(
            {
                "reference": reference,
                "lib_id": symbol["lib_id"],
                "value": " ".join(value[0].split()),
                "line": value[1],
                "quote": " ".join(value[2].split()),
                "footprint": symbol["props"].get("Footprint", ("", 0, ""))[0],
            }
        )
    return placed


def part_kind(reference: str, lib_id: str) -> str | None:
    match = REFERENCE.match(reference)
    kind = DESIGNATORS.get(match.group(1)) if match else None
    symbol = lib_id.rsplit(":", 1)[-1].casefold()
    if kind == "capacitor" and ("polarized" in symbol or symbol.startswith("cp")):
        return "electrolytic capacitor"
    if kind == "diode" and symbol.startswith("led"):
        return "LED"
    return kind


def schematic_name(value: str, lib_id: str, kind: str | None) -> str:
    """'220uF/16V electrolytic capacitor'; a generic symbol's unset value ('R') names only the
    kind. A part-number symbol ('Transistor_FET:AO3400A') keeps its value."""
    library, _, symbol = lib_id.rpartition(":")
    if value.casefold() == symbol.casefold() and library.casefold() in GENERIC_LIBRARIES:
        return kind or value
    if kind and kind.casefold() not in value.casefold():
        return f"{value} {kind}"
    return value


def linked_files(owner: str, repo: str, readme: str) -> list[tuple[str, str]]:
    """(ref, path) of repository code files the README links to, in order of appearance."""
    found = []
    blob = re.compile(
        rf"https://github\.com/{re.escape(owner)}/{re.escape(repo)}/blob/([\w.-]{{1,100}})/"
        r"([^\s)#?\"'>]+)",
        re.IGNORECASE,
    )
    for match in blob.finditer(readme):
        found.append((match.group(1), match.group(2)))
    for target in re.findall(r"\]\(([^)\s]+)\)", readme):
        if not urlsplit(target).scheme and not target.startswith("#"):
            found.append(("HEAD", target.split("#")[0].split("?")[0]))
    result = []
    for ref, path in found:
        clean = safe_path(path)
        if clean and wanted(clean) and (ref, clean) not in result:
            result.append((ref, clean))
    return result


def discover_files(fetcher: Fetcher, owner: str, repo: str) -> list[str] | None:
    """Code and build file paths from the repository tree, most useful first.

    None when the tree could not be read (refused, missing, oversized or malformed).
    """
    url = f"https://{API_HOST}/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    try:
        page = fetcher.get(url, max_bytes=TREE_BYTES)
    except FetchError:
        return None
    if page.status != 200 or (urlsplit(page.url).hostname or "").lower() != API_HOST:
        return None
    try:
        tree = json.loads(page.body.decode("utf-8", errors="replace")).get("tree")
    except (ValueError, AttributeError):
        return None
    if not isinstance(tree, list):
        return None
    paths = []
    for entry in tree[:MAX_TREE_ENTRIES]:
        if not isinstance(entry, dict) or entry.get("type") != "blob":
            continue
        path, size = entry.get("path"), entry.get("size")
        if not isinstance(path, str) or safe_path(path) != path:
            continue
        if not (wanted(path) or schematic(path)):
            continue
        limit = SCHEMATIC_BYTES if schematic(path) else CODE_FILE_BYTES
        if isinstance(size, int) and size > limit:
            continue
        if any(segment.casefold() in SKIP_DIRS for segment in path.split("/")[:-1]):
            continue
        paths.append(path)

    def rank(path: str) -> tuple[int, int, str]:
        name = basename(path).casefold()
        kind = 0 if name in BUILD_FILES else 1 if name.endswith(".ino") else 2
        return kind, path.count("/"), path.casefold()

    return sorted(paths, key=rank)


def candidate_files(
    owner: str, repo: str, readme: str, discovered: list[str] | None = None
) -> list[tuple[str, str]]:
    """Bounded, ordered list of (ref, path) to try.

    With `discovered` (paths from the repository tree) the list is the files that exist;
    otherwise it is conventional guesses, most of which will simply not exist.
    """
    if discovered:
        candidates = [("HEAD", path) for path in discovered]
    else:
        candidates = [("HEAD", "platformio.ini")]
        candidates += linked_files(owner, repo, readme)[:3]
        candidates += [
            ("HEAD", path)
            for path in (
                "src/main.cpp",
                f"{repo}.ino",
                f"{repo}/{repo}.ino",
                "code.py",
                "main.py",
                "requirements.txt",
                "library.json",
            )
        ]
    unique = []
    for candidate in candidates:
        if candidate not in unique and safe_path(candidate[1]):
            unique.append(candidate)
    return unique[:MAX_CODE_FILES]


def read_code(
    fetcher: Fetcher, repository_url: str, readme: str, deep: bool = False
) -> list[BomItem]:
    """Fetch the bounded file list and turn every mapped hint into a code-evidence BOM line.

    Without a README (empty `readme`) or with `deep` (the README named no parts) the
    repository tree chooses the files and KiCad schematics are read too. Otherwise the
    README links and conventional names are tried first and the tree is read only when no
    code file was found that way. Missing, refused (including robots.txt) or oversized
    files are skipped silently: code evidence is supplementary and never fails a job.
    """
    owner, repo = urlsplit(repository_url).path.strip("/").split("/")[:2]
    items: dict[str, list[Evidence]] = {}
    deep = deep or not readme.strip()
    tree = discover_files(fetcher, owner, repo) if deep else None
    discovered = [path for path in tree or [] if not schematic(path)] or None
    tried = candidate_files(owner, repo, readme, discovered)
    found_code = scan_files(fetcher, owner, repo, tried, items)
    if not deep and not found_code:
        found = [path for path in discover_files(fetcher, owner, repo) or [] if not schematic(path)]
        if found:
            extra = [c for c in candidate_files(owner, repo, "", found) if c not in tried]
            scan_files(fetcher, owner, repo, extra, items)
    boards = [path for path in tree or [] if schematic(path)][:MAX_SCHEMATICS]
    return [*code_lines(items), *read_schematics(fetcher, owner, repo, boards)]


def code_lines(items: dict[str, list[Evidence]]) -> list[BomItem]:
    return [
        BomItem(
            line_id=f"C{index:02d}",
            raw_name=part,
            qty=1,
            qty_source="inferred",
            qty_reason=QTY_REASON,
            evidence=evidence,
        )
        for index, (part, evidence) in enumerate(items.items(), start=1)
        if evidence
    ][:MAX_CODE_ITEMS]


def read_schematics(fetcher: Fetcher, owner: str, repo: str, paths: list[str]) -> list[BomItem]:
    """BOM lines from KiCad schematics: one per (symbol, value), counted by its references."""
    groups: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for path in paths:
        page = fetch_raw(fetcher, owner, repo, path, SCHEMATIC_BYTES)
        if page is None:
            continue
        text = page.body.decode("utf-8", errors="replace")
        if not text.lstrip().startswith("(kicad_sch"):
            continue
        for symbol in placed_symbols(text):
            key = (symbol["lib_id"].casefold(), symbol["value"].casefold())
            groups.setdefault(key, {}).setdefault(path, []).append(symbol)
    items: list[BomItem] = []
    for files in list(groups.values())[:MAX_SCHEMATIC_ITEMS]:
        first = next(iter(files.values()))[0]
        kind = part_kind(first["reference"], first["lib_id"])
        references = [symbol["reference"] for symbols in files.values() for symbol in symbols]
        name = schematic_name(first["value"], first["lib_id"], kind)
        if len(files) == 1 and len(references) <= MAX_REFS_IN_NAME:
            name = f"{name} ({', '.join(references)})"
        evidence = []
        for path, symbols in list(files.items())[:MAX_EVIDENCE]:
            symbol = symbols[0]
            footprint = f", footprint {symbol['footprint']}" if symbol["footprint"] else ""
            placed = ", ".join(s["reference"] for s in symbols)
            evidence.append(
                Evidence(
                    source="code",
                    observation=(
                        f"KiCad schematic {path} places {placed} ({symbol['lib_id']}"
                        f"{footprint}) with value {symbol['value']}."
                    )[:1000],
                    quote=symbol["quote"][:500],
                    url=f"https://github.com/{owner}/{repo}/blob/HEAD/{path}#L{symbol['line']}",
                    file=path,
                    line=symbol["line"],
                )
            )
        items.append(
            BomItem(
                line_id=f"K{len(items) + 1:02d}",
                raw_name=name[:200],
                qty=min(len(references), 10000),
                qty_source="stated",
                evidence=evidence,
            )
        )
    return items


def fetch_raw(fetcher: Fetcher, owner: str, repo: str, path: str, max_bytes: int) -> Page | None:
    """A text file from raw.githubusercontent.com, or None when missing, refused or binary."""
    raw = f"https://{RAW_HOST}/{owner}/{repo}/HEAD/{path}"
    try:
        page = fetcher.get(raw, max_bytes=max_bytes)
    except FetchError:
        return None
    if page.status != 200 or (urlsplit(page.url).hostname or "").lower() != RAW_HOST:
        return None
    if b"\0" in page.body[:4096]:
        return None
    return page


def scan_files(
    fetcher: Fetcher,
    owner: str,
    repo: str,
    candidates: list[tuple[str, str]],
    items: dict[str, list[Evidence]],
) -> bool:
    """Fetch and scan `candidates` into `items`; True when any code file was read."""
    found_code = False
    for ref, path in candidates:
        raw = f"https://{RAW_HOST}/{owner}/{repo}/{ref}/{path}"
        try:
            page = fetcher.get(raw, max_bytes=CODE_FILE_BYTES)
        except FetchError:
            continue
        if page.status != 200 or (urlsplit(page.url).hostname or "").lower() != RAW_HOST:
            continue
        if b"\0" in page.body[:4096]:
            continue
        found_code = found_code or path.casefold().endswith(CODE_SUFFIXES)
        text = page.body.decode("utf-8", errors="replace")
        for part, number, line, matched in scan(path, text):
            evidence = items.setdefault(part, [])
            if len(evidence) >= MAX_EVIDENCE or len(items) > MAX_CODE_ITEMS:
                continue
            quote = " ".join(line.split())[:500]
            if len(quote) < 3:
                continue
            evidence.append(
                Evidence(
                    source="code",
                    observation=f"{path} line {number} {matched}; the curated library map "
                    f"links this to {part}. Code shows the library, not the exact module.",
                    quote=quote,
                    url=f"https://github.com/{owner}/{repo}/blob/{ref}/{path}#L{number}",
                    file=path,
                    line=number,
                )
            )
    return found_code
