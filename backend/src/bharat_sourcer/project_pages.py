"""Supported maker project pages: URL recognition, readable text and quote checks.

Only Instructables, Hackster and GitHub repository READMEs are recognised. Fetching always
goes through `SafeFetcher` (HTTPS, public-address pinning, robots.txt, size limits); this
module never opens connections itself.

Instructables project pages are client-rendered: their HTML carries no step or supplies
text. The page itself loads that content from the public, robots-allowed
`/json-api/showInstructableModel` endpoint, so that JSON is fetched and turned into text,
while evidence still cites the canonical project page.
"""

import json
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Literal
from urllib.parse import quote, urlsplit

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
# Instructables category, account and asset paths that are not single projects.
INSTRUCTABLES_RESERVED = {
    "about",
    "account",
    "circuits",
    "classes",
    "contest",
    "contests",
    "cooking",
    "craft",
    "editinstructable",
    "file",
    "howto",
    "image",
    "json-api",
    "living",
    "member",
    "oauth",
    "outside",
    "projects",
    "search",
    "sitemap",
    "teachers",
    "workshop",
}
INSTRUCTABLES_API = "https://www.instructables.com/json-api/showInstructableModel?urlString="
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
    cite_url: str | None = None
    """URL cited by evidence; None cites the fetched document itself."""


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
        # Projects live at /<slug>/; /id/<slug>/ is the legacy form of the same page.
        if len(segments) == 2 and segments[0] == "id":
            segments = segments[1:]
        if len(segments) != 1 or segments[0].lower() in INSTRUCTABLES_RESERVED:
            return None
        canonical = f"https://www.instructables.com/{segments[0]}/"
        return ProjectPageSource(
            "instructables",
            canonical,
            (INSTRUCTABLES_API + quote(segments[0], safe=""),),
            frozenset({"www.instructables.com"}),
            cite_url=canonical,
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


# Section headings whose content is page chrome rather than the project itself.
BOILERPLATE_HEADING = re.compile(
    r"(?:\d+\s+)?(?:comments?|discussions?|leave a comment|add (?:a )?comment|post a comment"
    r"|related (?:projects|posts|instructables|content)|similar projects"
    r"|you (?:might|may) also like|recommended(?: for you| projects)?"
    r"|more (?:projects|from|by)\b.*|credits|respect project|share(?: this)?(?: project)?"
    r"|newsletter|sign up\b.*|subscribe\b.*)(?:\s*\(\d+\))?",
    re.IGNORECASE,
)
SKIP_ROLES = {"banner", "complementary", "contentinfo", "dialog", "navigation", "search"}
SKIP_IDS = re.compile(r"comments?|disqus_thread|related|recommendations?", re.IGNORECASE)


class ReadableText(HTMLParser):
    """Collect visible article text; drop scripts, styles, navigation, forms and chrome.

    Besides markup-level chrome (nav, footer, aside, forms, ARIA navigation roles, hidden
    elements), sections introduced by boilerplate headings such as "Comments" or
    "You might also like" are dropped up to the next heading of the same or higher level.
    """

    SKIP = {
        "aside",
        "button",
        "dialog",
        "footer",
        "form",
        "iframe",
        "nav",
        "noscript",
        "script",
        "select",
        "style",
        "svg",
        "template",
    }
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
    HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        # Element currently skipped, and how deeply that tag name is nested inside itself.
        self.skip_tag: str | None = None
        self.skip_nesting = 0
        # Open heading: (level, index into parts where its text starts).
        self.heading: tuple[int, int] | None = None
        # Level of the boilerplate heading whose section is being dropped.
        self.drop_level: int | None = None

    def _skips(self, tag, attrs) -> bool:
        if tag in self.SKIP:
            return True
        values = dict(attrs)
        if "hidden" in values or values.get("aria-hidden") == "true":
            return True
        if (values.get("role") or "").lower() in SKIP_ROLES:
            return True
        return bool(SKIP_IDS.fullmatch(values.get("id") or ""))

    def handle_starttag(self, tag, attrs):
        if self.skip_tag is not None:
            if tag == self.skip_tag:
                self.skip_nesting += 1
            return
        if self._skips(tag, attrs):
            self.skip_tag, self.skip_nesting = tag, 1
            return
        level = self.HEADINGS.get(tag)
        if level is not None:
            if self.drop_level is not None and level <= self.drop_level:
                self.drop_level = None
            if self.drop_level is None:
                self.heading = (level, len(self.parts))
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_startendtag(self, tag, attrs):
        if self.skip_tag is None and tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if self.skip_tag is not None:
            if tag == self.skip_tag:
                self.skip_nesting -= 1
                if self.skip_nesting == 0:
                    self.skip_tag = None
            return
        if self.heading is not None and self.HEADINGS.get(tag) == self.heading[0]:
            level, start = self.heading
            self.heading = None
            if BOILERPLATE_HEADING.fullmatch(" ".join("".join(self.parts[start:]).split())):
                del self.parts[start:]
                self.drop_level = level
                return
        if tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if self.skip_tag is None and self.drop_level is None:
            # HTML source line breaks are not text breaks; block tags add those.
            self.parts.append(re.sub(r"\s+", " ", data))


def tidy(text: str) -> str:
    lines = (" ".join(line.split()) for line in text.splitlines())
    return "\n".join(line for line in lines if line)


def html_text(markup: str) -> str:
    parser = ReadableText()
    parser.feed(markup)
    parser.close()
    return tidy("".join(parser.parts))


def media_type(page: Page) -> str:
    return page.headers.get("content-type", "").split(";")[0].strip().lower()


def readable_text(page: Page, limit: int) -> str:
    """Bounded readable text from an HTML page or a plain-text/Markdown README."""
    if page.status != 200:
        return ""
    media = media_type(page)
    decoded = page.body.decode("utf-8", errors="replace")
    if media in {"text/plain", "text/markdown", "text/x-markdown", "text/x-rst"}:
        return tidy(decoded)[:limit]
    if media not in {"text/html", "application/xhtml+xml"}:
        return ""
    return html_text(decoded)[:limit]


def instructables_text(page: Page, limit: int) -> str:
    """Bounded text of a published Instructables project from its page-model JSON.

    Mirrors what the project page renders: title, the Supplies section, then each step's
    title and body. Supplies come first, so a long project loses late steps, not its parts.
    Comments, related projects and navigation are not part of this document.
    """
    if page.status != 200 or media_type(page) != "application/json":
        return ""
    try:
        model = json.loads(page.body.decode("utf-8", errors="replace"))
    except ValueError:
        return ""
    if not isinstance(model, dict) or model.get("status", "PUBLISHED") != "PUBLISHED":
        return ""
    steps = model.get("steps")
    if not isinstance(steps, list):
        return ""
    blocks = [str(model.get("title") or "")]
    supplies = model.get("supplies")
    if isinstance(supplies, str) and supplies.strip():
        blocks += ["Supplies", html_text(supplies)]
    for number, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        title = str(step.get("title") or "")
        # The first entry is the unnumbered introduction; the rest render as "Step N: ...".
        blocks.append(title if number == 0 else f"Step {number}: {title}")
        body = step.get("body")
        if isinstance(body, str):
            blocks.append(html_text(body))
    return tidy("\n".join(blocks))[:limit]


def document_text(source: ProjectPageSource, page: Page, limit: int) -> str:
    """Bounded readable text of a fetched project document of the source's kind."""
    if source.kind == "instructables":
        return instructables_text(page, limit)
    return readable_text(page, limit)


def normalise(text: str) -> str:
    return " ".join(text.split())


def quote_found(quote: str, text: str) -> bool:
    """True when the whitespace-normalised quote appears verbatim in the document text."""
    needle = normalise(quote)
    return len(needle) >= 3 and needle in normalise(text)
