"""Verified account identities and signed, expiring guest sessions."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

import google.auth
from google.auth.transport.requests import AuthorizedSession, Request
from google.oauth2 import id_token


@dataclass(frozen=True)
class Principal:
    owner: str
    guest: bool = False
    expires_at: int | None = None


class IdentityUnavailable(Exception):
    """Provider status could not be checked; never admit the request."""


def lookup_account(project: str, uid: str) -> dict:
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        with AuthorizedSession(credentials) as session:
            response = session.post(
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
    def __init__(self, project: str, account_lookup=None):
        self.project = project
        self.account_lookup = account_lookup or lookup_account

    def verify(self, token: str) -> Principal:
        claims = id_token.verify_firebase_token(token, Request(), audience=self.project)
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
        value = f"{secrets.token_hex(24)}.{int(time.time()) + self.lifetime}"
        return value + "." + self.signature(value)

    def verify(self, cookie: str | None) -> Principal:
        if not cookie or len(cookie) > 200:
            raise ValueError("Guest session required")
        key, expiry, signature = cookie.split(".")
        if (
            len(key) != 48
            or not all(c in "0123456789abcdef" for c in key)
            or not hmac.compare_digest(signature, self.signature(key + "." + expiry))
            or int(expiry) <= time.time()
        ):
            raise ValueError("Invalid guest session")
        return Principal("guest:" + key, True, int(expiry))
