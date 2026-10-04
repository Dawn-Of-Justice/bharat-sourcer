"""Controlled Firebase status responses; no real accounts or credentials."""

import time
from unittest.mock import Mock, patch

import pytest
from test_identity import create, setup

from bharat_sourcer.identity import FirebaseVerifier, IdentityUnavailable, lookup_account


@pytest.mark.parametrize(
    "account,accepted",
    [
        ({"disabled": False, "validSince": "100"}, True),
        ({"disabled": True}, False),
        ({"validSince": "101"}, False),
        ({"validSince": "99"}, True),
    ],
)
def test_revocation_compares_auth_time_not_token_issue_time(account, accepted):
    claims = {
        "sub": "alice",
        "iss": "https://securetoken.google.com/test",
        "firebase": {"sign_in_provider": "google.com"},
        "email_verified": True,
        "auth_time": 100,
        "iat": 200,
        "exp": int(time.time()) + 3600,
    }
    lookup = Mock(return_value=account)
    verifier = FirebaseVerifier("test", account_lookup=lookup)
    with patch("google.oauth2.id_token.verify_firebase_token", return_value=claims):
        if accepted:
            assert verifier.verify("fixture").owner == "user:alice"
        else:
            with pytest.raises(ValueError):
                verifier.verify("fixture")
    lookup.assert_called_once_with("test", "alice")


def test_provider_outage_fails_closed_without_falling_back_to_guest_or_charging():
    client, app = setup()
    assert client.post("/v1/session/guest").status_code == 200
    with patch.object(app.state.access.verifier, "verify", side_effect=IdentityUnavailable()):
        response = create(client, "alice")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "IDENTITY_UNAVAILABLE"
    assert app.state.job_service.store.owned("user:alice", "", 10) == []


@pytest.mark.parametrize("users", [[], [{"localId": "other"}]])
def test_deleted_or_mismatched_account_is_rejected(users):
    session = Mock()
    session.post.return_value.json.return_value = {"users": users}
    with (
        patch("google.auth.default", return_value=(Mock(), "test")),
        patch("bharat_sourcer.identity.AuthorizedSession") as factory,
    ):
        factory.return_value.__enter__.return_value = session
        with pytest.raises(ValueError if not users else IdentityUnavailable):
            lookup_account("test", "alice")
        assert session.post.call_args.kwargs["json"] == {
            "targetProjectId": "test",
            "localId": ["alice"],
        }
        assert session.post.call_args.kwargs["timeout"] == 10


def test_status_lookup_http_error_is_unavailable():
    session = Mock()
    session.post.return_value.raise_for_status.side_effect = RuntimeError("unavailable")
    with (
        patch("google.auth.default", return_value=(Mock(), "test")),
        patch("bharat_sourcer.identity.AuthorizedSession") as factory,
    ):
        factory.return_value.__enter__.return_value = session
        with pytest.raises(IdentityUnavailable):
            lookup_account("test", "alice")
