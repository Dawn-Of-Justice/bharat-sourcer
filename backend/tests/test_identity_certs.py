"""Firebase token signatures checked for real against generated keys; no network."""

import json
import time
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from google.auth import crypt, jwt

from bharat_sourcer.identity import FIREBASE_CERTS_URL, CachedCerts, FirebaseVerifier


def keypair(kid):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture")])
    start = datetime.now(UTC) - timedelta(days=1)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(1)
        .not_valid_before(start)
        .not_valid_after(start + timedelta(days=3))
        .sign(key, hashes.SHA256())
    )
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return crypt.RSASigner.from_string(pem, key_id=kid), cert.public_bytes(
        serialization.Encoding.PEM
    ).decode()


@pytest.fixture(scope="module")
def keys():
    return {kid: keypair(kid) for kid in ("old", "new")}


def token(signer, uid="alice"):
    now = int(time.time())
    return jwt.encode(
        signer,
        {
            "iss": "https://securetoken.google.com/test",
            "aud": "test",
            "sub": uid,
            "iat": now - 10,
            "auth_time": now - 10,
            "exp": now + 3600,
            "email_verified": True,
            "firebase": {"sign_in_provider": "google.com"},
        },
    ).decode()


class Response:
    def __init__(self, certs, status=200, cache_control="public, max-age=20000"):
        self.status, self.data = status, json.dumps(certs).encode()
        self.headers = {"Cache-Control": cache_control} if cache_control else {}


class Transport:
    """Serves the published certificate set and records each download."""

    def __init__(self, certs, **response):
        self.certs, self.response, self.calls = certs, response, []

    def __call__(self, url, method="GET", **kwargs):
        self.calls.append((url, method, kwargs.get("timeout")))
        return Response(dict(self.certs), **self.response)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def verifier(transport, clock):
    return FirebaseVerifier(
        "test",
        account_lookup=lambda project, uid: {"localId": uid},
        certs=CachedCerts(transport, clock),
    )


def test_certificates_download_once_per_max_age_not_per_request(keys):
    signer, cert = keys["old"]
    transport, clock = Transport({"old": cert}), Clock()
    check = verifier(transport, clock)
    for uid in ("alice", "bob", "alice"):
        assert check.verify(token(signer, uid)).owner == "user:" + uid
    assert transport.calls == [(FIREBASE_CERTS_URL, "GET", CachedCerts.timeout_s)]
    clock.now += 20001
    assert check.verify(token(signer)).owner == "user:alice"
    assert len(transport.calls) == 2


def test_a_rotated_key_gets_one_fresh_download(keys):
    old, old_cert = keys["old"]
    new, new_cert = keys["new"]
    transport, clock = Transport({"old": old_cert}), Clock()
    check = verifier(transport, clock)
    assert check.verify(token(old)).owner == "user:alice"
    transport.certs["new"] = new_cert
    # A fresh cache is trusted: unknown keys cannot force repeated downloads.
    with pytest.raises(ValueError):
        check.verify(token(new))
    assert len(transport.calls) == 1
    clock.now += FirebaseVerifier.refetch_after_s
    assert check.verify(token(new)).owner == "user:alice"
    assert len(transport.calls) == 2
    with pytest.raises(ValueError):
        check.verify(token(keypair("unknown")[0]))
    assert len(transport.calls) == 2


@pytest.mark.parametrize(
    "response", [{"status": 500}, {"cache_control": None}, {"cache_control": "no-cache"}]
)
def test_failed_or_uncacheable_downloads_are_not_kept(keys, response):
    signer, cert = keys["old"]
    transport = Transport({"old": cert}, **response)
    check = verifier(transport, Clock())
    for _ in range(2):
        if response.get("status") == 500:
            with pytest.raises(Exception, match="Could not fetch certificates"):
                check.verify(token(signer))
        else:
            assert check.verify(token(signer)).owner == "user:alice"
    assert len(transport.calls) == 2


def test_requests_other_than_plain_gets_pass_through():
    transport = Transport({})
    certs = CachedCerts(transport, Clock())
    for _ in range(2):
        certs(FIREBASE_CERTS_URL, method="POST", body=b"{}")
    assert len(transport.calls) == 2
