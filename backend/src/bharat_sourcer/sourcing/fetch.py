"""HTTPS fetching with public-address pinning, robots checks and response limits."""

import http.client
import ipaddress
import re
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

# RuleLine and RobotFileParser.entries are undocumented stdlib internals missing from typeshed.
from urllib.robotparser import RobotFileParser, RuleLine  # type: ignore[attr-defined]

USER_AGENT = "BharatSourcer/0.4 (+product-data-verification)"


class FetchError(Exception):
    pass


def public_addresses(host: str) -> list[str]:
    try:
        addresses = list(
            dict.fromkeys(
                str(answer[4][0])
                for answer in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            )
        )
    except OSError as exc:
        raise FetchError("DNS lookup failed") from exc
    if not addresses or any(not ipaddress.ip_address(value).is_global for value in addresses):
        raise FetchError("Non-public address rejected")
    return addresses


def validate_url(url: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or len(url) > 4096
        ):
            raise ValueError
        host = parsed.hostname.encode("idna").decode("ascii")
        if any(c in host for c in "\r\n\t /\\"):
            raise ValueError
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query
        return host, path
    except (ValueError, UnicodeError) as exc:
        raise FetchError("Only public HTTPS URLs are supported") from exc


class PatternRule:
    """A robots.txt rule with RFC 9309 `*` wildcards and `$` end anchors."""

    def __init__(self, rule: RuleLine):
        # RuleLine stores the percent-quoted path, so `*` and `$` arrive as %2A and %24.
        self.path = rule.path
        self.allowance = rule.allowance
        pattern = re.escape(rule.path).replace("%2A", ".*")
        if pattern.endswith("%24"):
            pattern = pattern[: -len("%24")] + r"\Z"
        self.pattern = re.compile(pattern)

    def applies_to(self, filename: str) -> bool:
        return self.pattern.match(filename) is not None


def robots_parser(text: str) -> RobotFileParser:
    """Parse robots.txt closer to RFC 9309 than the standard library does alone.

    The stdlib parser ends a group at blank or comment-only lines (dropping rules such as
    Hackster's commented `User-Agent: *` group), matches rules literally and takes the
    first matching rule. Here comment-only and blank lines are removed first, `*`/`$`
    patterns are honoured and the longest matching rule wins (Allow on ties).
    """
    lines = [line for line in text.splitlines() if line.split("#", 1)[0].strip()]
    parser = RobotFileParser()
    parser.parse(lines)
    default = parser.default_entry  # type: ignore[attr-defined]
    entries = [*parser.entries, *([default] if default else [])]  # type: ignore[attr-defined]
    for entry in entries:
        rules = [PatternRule(rule) for rule in entry.rulelines]
        entry.rulelines = sorted(rules, key=lambda rule: (-len(rule.path), not rule.allowance))
    return parser


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        self.tls_context = ssl.create_default_context()
        super().__init__(host, timeout=timeout, context=self.tls_context)
        self.address = address

    def connect(self):
        # Connect to the checked address while preserving TLS hostname validation.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self.tls_context.wrap_socket(sock, server_hostname=self.host)
        except Exception:
            sock.close()
            raise


@dataclass
class Page:
    url: str
    status: int
    headers: dict[str, str]
    body: bytes


class SafeFetcher:
    def __init__(self):
        self._robots: dict[str, RobotFileParser | None] = {}
        self._robots_expiry: dict[str, float] = {}
        self._last_request: dict[str, float] = {}

    def _request(self, url: str, max_bytes: int) -> Page:
        host, path = validate_url(url)
        addresses = public_addresses(host)
        delay = 1.0 - (time.monotonic() - self._last_request.get(host, 0))
        if delay > 0:
            time.sleep(delay)
        self._last_request[host] = time.monotonic()
        connection = PinnedHTTPSConnection(host, addresses[0], timeout=8)
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Encoding": "identity",
                    "Accept": (
                        "text/html,application/ld+json,application/json;q=0.9,text/plain;q=0.5"
                    ),
                },
            )
            response = connection.getresponse()
            headers = {key.lower(): value for key, value in response.getheaders()}
            if 300 <= response.status < 400:
                return Page(url, response.status, headers, b"")
            if headers.get("content-encoding", "identity") != "identity":
                raise FetchError("Compressed response not supported")
            data = bytearray()
            deadline = time.monotonic() + 12
            while len(data) <= max_bytes:
                if time.monotonic() > deadline:
                    raise FetchError("Page read deadline exceeded")
                chunk = response.read1(min(65536, max_bytes + 1 - len(data)))
                if not chunk:
                    return Page(url, response.status, headers, bytes(data))
                data.extend(chunk)
            raise FetchError("Page exceeds size limit")
        except (OSError, http.client.HTTPException) as exc:
            raise FetchError("Page fetch failed") from exc
        finally:
            connection.close()

    def _allowed(self, url: str) -> bool:
        host, _ = validate_url(url)
        origin = f"https://{host}"
        if self._robots_expiry.get(origin, float("inf")) <= time.monotonic():
            self._robots.pop(origin, None)
        if origin not in self._robots:
            response = self.get(origin + "/robots.txt", robots=False, max_bytes=128_000)
            if response.status == 404:
                parser = robots_parser("")
            elif response.status == 200:
                parser = robots_parser(response.body.decode("utf-8", errors="replace"))
            else:
                parser = None
            self._robots[origin] = parser
            self._robots_expiry[origin] = time.monotonic() + 600 if parser is None else float("inf")
        parser = self._robots[origin]
        if parser is None or not parser.can_fetch(USER_AGENT, url):
            return False
        delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 1
        rate = parser.request_rate(USER_AGENT) or parser.request_rate("*")
        if rate and rate.seconds / rate.requests > 1:
            return False
        # Skip long-delay sites rather than holding workers open.
        # typeshed declares crawl_delay as str | None; CPython returns an int.
        return float(delay) <= 1

    def get(self, url: str, *, robots: bool = True, max_bytes: int = 2_000_000) -> Page:
        for _ in range(6):
            host, path = validate_url(url)
            grounding_redirect = host == "vertexaisearch.cloud.google.com" and path.startswith(
                "/grounding-api-redirect/"
            )
            if robots and not grounding_redirect and not self._allowed(url):
                raise FetchError("Robots policy prevents verification")
            response = self._request(url, max_bytes)
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise FetchError("Redirect without location")
                url = urljoin(url, location)
                continue
            return response
        raise FetchError("Too many redirects")
