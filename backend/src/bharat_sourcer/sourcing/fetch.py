"""HTTPS fetching with public-address pinning, robots checks and response limits."""

import http.client
import ipaddress
import socket
import ssl
import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

USER_AGENT = "BharatSourcer/0.4 (+product-data-verification)"


class FetchError(Exception):
    pass


def public_addresses(host: str) -> list[str]:
    try:
        addresses = list(
            dict.fromkeys(
                answer[4][0] for answer in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
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


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host: str, address: str, timeout: float):
        super().__init__(host, timeout=timeout, context=ssl.create_default_context())
        self.address = address

    def connect(self):
        # Connect to the checked address while preserving TLS hostname validation.
        sock = socket.create_connection((self.address, 443), self.timeout)
        try:
            self.sock = self._context.wrap_socket(sock, server_hostname=self.host)
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
                    "Accept": "text/html,application/ld+json,text/plain;q=0.5",
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
        if origin not in self._robots:
            response = self.get(origin + "/robots.txt", robots=False, max_bytes=128_000)
            if response.status == 404:
                parser = RobotFileParser()
                parser.parse([])
            elif response.status == 200:
                parser = RobotFileParser()
                parser.parse(response.body.decode("utf-8", errors="replace").splitlines())
            else:
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        if parser is None or not parser.can_fetch(USER_AGENT, url):
            return False
        delay = parser.crawl_delay(USER_AGENT) or parser.crawl_delay("*") or 1
        rate = parser.request_rate(USER_AGENT) or parser.request_rate("*")
        if rate and rate.seconds / rate.requests > 1:
            return False
        # Skip long-delay sites rather than holding workers open.
        return delay <= 1

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
