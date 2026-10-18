"""Bounded repository documentation discovery; source text is data, never instructions."""

import json
import re
from posixpath import basename
from urllib.parse import unquote, urlsplit

from bharat_sourcer.code_evidence import safe_path
from bharat_sourcer.sourcing.fetch import FetchError

MAX_DOCUMENTS = 16
DOCUMENT_BYTES = 100_000
EXCLUDED = {"archive", "archived", "legacy", "vendor", "node_modules", ".git", "superseded"}


def relevant(path: str) -> bool:
    return bool(
        safe_path(path) == path
        and not any(p.casefold() in EXCLUDED for p in path.split("/"))
        and path.lower().endswith((".md", ".rst", ".txt", ".csv", ".tsv"))
        and re.search(r"bom|parts|components|wiring|hardware|assembly|pcb|readme", path, re.I)
    )


def repository_documents(fetcher, repository_url: str, readme: str, char_limit: int):
    owner, repo = urlsplit(repository_url).path.strip("/").split("/")[:2]
    base = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/"
    paths = set()
    # Relative README links remain useful if GitHub tree access is unavailable.
    for target in re.findall(r"\]\(([^)\s]+)", readme):
        parsed = urlsplit(target)
        if not parsed.scheme and not parsed.netloc:
            path = unquote(parsed.path).removeprefix("./")
            if relevant(path):
                paths.add(path)
    try:
        tree = fetcher.get(
            f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1",
            max_bytes=1_000_000,
        )
        if tree.status == 200 and urlsplit(tree.url).hostname == "api.github.com":
            for entry in json.loads(tree.body).get("tree", [])[:5000]:
                path = entry.get("path", "")
                if (
                    entry.get("type") == "blob"
                    and relevant(path)
                    and entry.get("size", 0) <= DOCUMENT_BYTES
                ):
                    paths.add(path)
    except (FetchError, ValueError, TypeError, AttributeError):
        pass

    def rank(path):
        name = basename(path).lower()
        return (
            0
            if re.search(r"bom|parts|components", name)
            else 1
            if re.search(r"wiring|hardware|assembly", name)
            else 2
            if re.search(r"pcb|firmware|hardware", path, re.I)
            and not re.search(r"capture|test|scan", path, re.I)
            else 3,
            path.count("/"),
            path,
        )

    documents: list[tuple[str, str]] = []
    remaining = char_limit
    for path in sorted(paths, key=rank):
        if "/" not in path and basename(path).lower().startswith("readme"):
            continue
        if len(documents) >= MAX_DOCUMENTS or remaining <= 0:
            break
        url = base + path
        try:
            page = fetcher.get(url, max_bytes=DOCUMENT_BYTES)
        except FetchError:
            continue
        if page.status != 200 or page.url != url or b"\0" in page.body:
            continue
        text = page.body.decode("utf-8", errors="replace")[: min(32000, remaining)]
        if text.strip():
            documents.append((url, text))
            remaining -= len(text)
    return documents
