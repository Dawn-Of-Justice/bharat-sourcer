"""Verified account identities and signed, expiring guest sessions."""

import hashlib
import hmac
import secrets
import time
from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2 import id_token


@dataclass(frozen=True)
class Principal:
    owner: str
    guest: bool = False
    expires_at: int | None = None


class FirebaseVerifier:
    def __init__(self, project: str):
        self.project = project

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
        return Principal("user:" + uid, expires_at=int(claims["exp"]))


class GuestSessions:
    cookie_name = "bs_guest"

    def __init__(self, secret: str, lifetime: int):
        self.secret, self.lifetime = secret.encode(), lifetime

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
