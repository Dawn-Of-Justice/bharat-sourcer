"""Deterministic part hints from a public GitHub repository's code and build files.

Besides the README, a bounded set of files is read from the same public
`raw.githubusercontent.com` endpoint through the guarded fetcher: `platformio.ini`,
`library.json`, `requirements.txt`, the usual Arduino, PlatformIO, CircuitPython and
MicroPython entry points, and code files the README links to. `#include` lines, Python
imports, `lib_deps`/dependencies and `board =` targets are mapped to part hints with the
curated `data/library_parts.json` table. No model is involved, every hint cites
`file:line`, and code never establishes how many of a part the build uses.
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
CODE_FILE_BYTES = 200_000
MAX_CODE_FILES = 8
MAX_LINES = 5000
MAX_CODE_ITEMS = 30
MAX_EVIDENCE = 5
CODE_SUFFIXES = (".ino", ".cpp", ".c", ".h", ".hpp", ".py")
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


def candidate_files(owner: str, repo: str, readme: str) -> list[tuple[str, str]]:
    """Bounded, ordered list of (ref, path) to try; most files will simply not exist."""
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


def read_code(fetcher: Fetcher, repository_url: str, readme: str) -> list[BomItem]:
    """Fetch the bounded file list and turn every mapped hint into a code-evidence BOM line.

    Missing, refused (including robots.txt) or oversized files are skipped silently: code
    evidence is supplementary to the README and never fails a job.
    """
    owner, repo = urlsplit(repository_url).path.strip("/").split("/")[:2]
    items: dict[str, list[Evidence]] = {}
    for ref, path in candidate_files(owner, repo, readme):
        raw = f"https://{RAW_HOST}/{owner}/{repo}/{ref}/{path}"
        try:
            page = fetcher.get(raw, max_bytes=CODE_FILE_BYTES)
        except FetchError:
            continue
        if page.status != 200 or (urlsplit(page.url).hostname or "").lower() != RAW_HOST:
            continue
        if b"\0" in page.body[:4096]:
            continue
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
