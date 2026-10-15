"""Verified account identities and signed, expiring guest sessions."""

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass

import google.auth
import requests
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token

# Firebase ID token signing certificates (what id_token.verify_firebase_token downloads).
FIREBASE_CERTS_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com"
)


@dataclass(frozen=True)
class Principal:
    owner: str
    guest: bool = False
    expires_at: int | None = None


class IdentityUnavailable(Exception):
    """Provider status could not be checked; never admit the request."""


class CachedCerts:
    """google-auth transport that keeps downloaded signing certificates for their max-age.

    google-auth fetches the certificates on every verification, costing every account
    request a fresh HTTPS round trip. Google publishes them with a Cache-Control max-age
    (hours) and rotates keys within it, so one download serves every request until then.
    Only plain GETs are cached; anything else passes through.
    """

    max_age_cap_s = 6 * 3600
    timeout_s = 10

    def __init__(self, transport=None, clock=time.monotonic):
        self.transport = transport or Request(requests.Session())
        self.clock = clock
        self._lock = threading.Lock()
        self._cache: dict[str, tuple[float, float, object]] = {}

    def __call__(self, url, method="GET", body=None, headers=None, timeout=None, **kwargs):
        if method != "GET" or body is not None:
            return self.transport(
                url, method=method, body=body, headers=headers, timeout=timeout, **kwargs
            )
        now = self.clock()
        with self._lock:
            cached = self._cache.get(url)
        if cached and cached[1] > now:
            return cached[2]
        response = self.transport(
            url, method="GET", headers=headers, timeout=timeout or self.timeout_s, **kwargs
        )
        match = re.search(r"max-age=(\d+)", response.headers.get("Cache-Control", ""))
        if response.status == 200 and match and int(match.group(1)) > 0:
            lifetime = min(int(match.group(1)), self.max_age_cap_s)
            with self._lock:
                self._cache[url] = (now, now + lifetime, response)
        return response

    def expire(self, url: str, older_than_s: float) -> bool:
        """Drop the cached copy of `url` if it was fetched over `older_than_s` ago."""
        with self._lock:
            cached = self._cache.get(url)
            if cached is None or self.clock() - cached[0] < older_than_s:
                return False
            del self._cache[url]
            return True


_session_lock = threading.Lock()
_session: AuthorizedSession | None = None


def account_session() -> AuthorizedSession:
    """One authorised session per process. Credentials, their access token (refreshed when
    it expires) and the HTTPS connection are reused instead of rebuilt on every request."""
    global _session  # noqa: PLW0603 - one shared session per process, built on first use
    with _session_lock:
        if _session is None:
            credentials, _ = google.auth.default(
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            _session = AuthorizedSession(credentials)
        return _session


def lookup_account(project: str, uid: str, session: AuthorizedSession | None = None) -> dict:
    try:
        response = (session or account_session()).post(
            "https://identitytoolkit.googleapis.com/v1/accounts:lookup",
            json={"targetProjectId": project, "localId": [uid]},
            timeout=10,
        )
        response.raise_for_status()
        users = response.json().get("users", [])
        if not isinstance(users, list):
            raise ValueError("Invalid account response")
    except Exception as exc:
        raise IdentityUnavailable("Account verification unavailable") from exc
    if not users:
        raise ValueError("Account no longer exists")
    if len(users) != 1 or not isinstance(users[0], dict) or users[0].get("localId") != uid:
        raise IdentityUnavailable("Unexpected account response")
    return users[0]


class FirebaseVerifier:
    # A token the cached certificates reject gets one retry with a fresh download (keys
    # rotate), at most once per this interval so bad tokens cannot force repeated fetches.
    refetch_after_s = 300

    def __init__(self, project: str, account_lookup=None, certs: CachedCerts | None = None):
        self.project = project
        self.account_lookup = account_lookup or lookup_account
        self.certs = certs or CachedCerts()

    def claims(self, token: str) -> dict:
        try:
            return id_token.verify_firebase_token(token, self.certs, audience=self.project)
        except ValueError:
            if not self.certs.expire(FIREBASE_CERTS_URL, self.refetch_after_s):
                raise
            return id_token.verify_firebase_token(token, self.certs, audience=self.project)

    def verify(self, token: str) -> Principal:
        claims = self.claims(token)
        uid = claims.get("sub")
        if (
            claims.get("iss") != f"https://securetoken.google.com/{self.project}"
            or not isinstance(uid, str)
            or not 1 <= len(uid) <= 128
            or claims.get("firebase", {}).get("sign_in_provider") != "google.com"
            or claims.get("email_verified") is not True
            or claims.get("auth_time", time.time() + 1) > time.time()
        ):
            raise ValueError("Invalid account identity")
        account = self.account_lookup(self.project, uid)
        try:
            valid_since = int(account.get("validSince", 0))
        except (ValueError, TypeError) as exc:
            raise IdentityUnavailable("Invalid account status") from exc
        if account.get("disabled", False) or claims["auth_time"] < valid_since:
            raise ValueError("Account disabled or session revoked")
        return Principal("user:" + uid, expires_at=int(claims["exp"]))


class GuestSessions:
    # Firebase Hosting forwards only a cookie named `__session` to Cloud Run.
    cookie_name = "__session"
    # Read until sessions issued under the old name expire.
    legacy_cookie_name = "bs_guest"

    def __init__(self, secret: str, lifetime: int):
        self.secret, self.lifetime = secret.encode(), lifetime

    def cookie(self, request) -> str | None:
        return request.cookies.get(self.cookie_name) or request.cookies.get(self.legacy_cookie_name)

    def signature(self, value):
        return hmac.new(self.secret, value.encode(), hashlib.sha256).hexdigest()

    def issue(self):
        if not self.secret:
            # An empty HMAC key would make every session forgeable.
            raise RuntimeError("Guest session secret is not configured")
        value = f"{secrets.token_hex(24)}.{int(time.time()) + self.lifetime}"
        return value + "." + self.signature(value)

    def verify(self, cookie: str | None) -> Principal:
        """The guest principal of a valid cookie; ValueError for anything else."""
        if not self.secret:
            raise ValueError("Guest sessions are not configured")
        if not cookie or len(cookie) > 200 or not cookie.isascii():
            raise ValueError("Guest session required")
        parts = cookie.split(".")
        if len(parts) != 3:
            raise ValueError("Invalid guest session")
        key, expiry, signature = parts
        if (
            len(key) != 48
            or not all(c in "0123456789abcdef" for c in key)
            or not expiry.isdigit()
            or not hmac.compare_digest(
                signature.encode(), self.signature(key + "." + expiry).encode()
            )
            or int(expiry) <= time.time()
        ):
            raise ValueError("Invalid guest session")
        return Principal("guest:" + key, True, int(expiry))
