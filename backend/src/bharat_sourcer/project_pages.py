"""Supported maker project pages: URL recognition, readable text and quote checks.

Only Instructables, Hackster and GitHub repository READMEs are recognised. Fetching always
goes through `SafeFetcher` (HTTPS, public-address pinning, robots.txt, size limits); this
module never opens connections itself.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import urlsplit

from bharat_sourcer.sourcing.fetch import Page

ProjectKind = Literal["instructables", "hackster", "github"]

SEGMENT = r"[A-Za-z0-9._~%-]+"
GITHUB_OWNER = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
GITHUB_REPO = re.compile(r"[A-Za-z0-9._-]{1,100}")
# Site sections that are not user projects or repositories.
GITHUB_RESERVED = {
    "about",
    "apps",
    "collections",
    "enterprise",
    "explore",
    "features",
    "login",
    "marketplace",
    "notifications",
    "orgs",
    "organizations",
    "pricing",
    "search",
    "settings",
    "sponsors",
    "topics",
    "trending",
    "users",
}
HACKSTER_RESERVED = {"api", "auth", "channels", "contests", "news", "projects", "search", "users"}
# Try the common README spellings; HEAD resolves the repository's default branch.
README_NAMES = ("README.md", "readme.md", "README.rst", "README")


@dataclass(frozen=True)
class ProjectPageSource:
    kind: ProjectKind
    url: str
    """Canonical project URL shown to users."""
    fetch_urls: tuple[str, ...]
    """Documents to try in order; the first HTTP 200 response is used."""
    hosts: frozenset[str]
    """Hosts a fetched document may come from after redirects."""


def project_page_source(url: str) -> ProjectPageSource | None:
    """Recognise a supported project URL; return None for every other input."""
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or port not in (None, 80, 443)
    ):
        return None
    path = parsed.path
    if not re.fullmatch(rf"(?:/{SEGMENT})+/?", path or ""):
        return None
    segments = [segment for segment in path.split("/") if segment]
    if any(segment in {".", ".."} for segment in segments):
        return None
    if host in {"instructables.com", "www.instructables.com"}:
        canonical = "https://www.instructables.com/" + "/".join(segments) + "/"
        return ProjectPageSource(
            "instructables", canonical, (canonical,), frozenset({"www.instructables.com"})
        )
    if host in {"hackster.io", "www.hackster.io"}:
        if len(segments) != 2 or segments[0].lower() in HACKSTER_RESERVED:
            return None
        canonical = "https://www.hackster.io/" + "/".join(segments)
        return ProjectPageSource(
            "hackster", canonical, (canonical,), frozenset({"www.hackster.io"})
        )
    if host in {"github.com", "www.github.com"}:
        if len(segments) != 2:
            return None
        owner, repo = segments[0], segments[1].removesuffix(".git")
        if (
            not GITHUB_OWNER.fullmatch(owner)
            or not GITHUB_REPO.fullmatch(repo)
            or repo in {".", ".."}
            or owner.lower() in GITHUB_RESERVED
        ):
            return None
        raw = f"https://raw.githubusercontent.com/{owner}/{repo}/HEAD/"
        return ProjectPageSource(
            "github",
            f"https://github.com/{owner}/{repo}",
            tuple(raw + name for name in README_NAMES),
            frozenset({"raw.githubusercontent.com"}),
        )
    return None


class ReadableText(HTMLParser):
    """Collect visible article text; drop scripts, styles, navigation and forms."""

    SKIP = {"script", "style", "noscript", "svg", "template", "iframe", "nav", "footer", "form"}
    BLOCK = {
        "address",
        "article",
        "br",
        "dd",
        "div",
        "dt",
        "figcaption",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "hr",
        "li",
        "main",
        "ol",
        "p",
        "pre",
        "section",
        "table",
        "td",
        "th",
        "tr",
        "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.depth += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.depth = max(0, self.depth - 1)
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.depth == 0:
            # HTML source line breaks are not text breaks; block tags add those.
            self.parts.append(re.sub(r"\s+", " ", data))


def tidy(text: str) -> str:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def readable_text(page: Page, limit: int) -> str:
    """Bounded readable text from an HTML page or a plain-text/Markdown README."""
    if page.status != 200:
        return ""
    media = page.headers.get("content-type", "").split(";")[0].strip().lower()
    decoded = page.body.decode("utf-8", errors="replace")
    if media in {"text/plain", "text/markdown", "text/x-markdown", "text/x-rst"}:
        return tidy(decoded)[:limit]
    if media not in {"text/html", "application/xhtml+xml"}:
        return ""
    parser = ReadableText()
    parser.feed(decoded)
    parser.close()
    return tidy("".join(parser.parts))[:limit]


def normalise(text: str) -> str:
    return " ".join(text.split())


def quote_found(quote: str, text: str) -> bool:
    """True when the whitespace-normalised quote appears verbatim in the document text."""
    needle = normalise(quote)
    return len(needle) >= 3 and needle in normalise(text)
