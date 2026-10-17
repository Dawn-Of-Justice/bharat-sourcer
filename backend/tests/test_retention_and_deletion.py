"""Project retention and delete-my-data. Identities and projects are synthetic."""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound

from bharat_sourcer.config import Settings
from bharat_sourcer.dispatch import CloudDispatcher
from bharat_sourcer.identity import Principal, delete_auth_user
from bharat_sourcer.jobs import JobService
from bharat_sourcer.main import create_app
from bharat_sourcer.schemas import AccountSettings, CreateJob, now
from bharat_sourcer.sharing import token_hash
from bharat_sourcer.storage import FirestoreJobStore, MemoryJobStore, Retention, StoredJob


class Verifier:
    def verify(self, token):
        if token not in {"alice", "bob"}:
            raise ValueError("Invalid mock signature")
        return Principal("user:" + token)


def setup(**overrides):
    settings = Settings(
        _env_file=None,
        auth_enabled=True,
        gcp_project="fixture-project",
        guest_session_secret="test-secret-only-not-production-123456",
        **overrides,
    )
    app = create_app(settings, identity_verifier=Verifier())
    client = TestClient(app, base_url="https://testserver")
    client.headers["X-Requested-With"] = "BharatSourcer"
    deleted_users = []
    app.state.access.delete_user = lambda project, uid: deleted_users.append((project, uid))
    return client, app, deleted_users


def auth(user):
    return {"Authorization": "Bearer " + user}


def create(client, user=None):
    headers = auth(user) if user else {}
    response = client.post("/v1/jobs", json={"url": "https://example.com"}, headers=headers)
    assert response.status_code in {200, 201, 202}, response.text
    return response.json()["job_id"]


def age(store, key, days):
    def change(record):
        record.job.updated_at = now() - timedelta(days=days)

    assert store.mutate(key, change) is not None


def share(store, key):
    token = f"{key}.{'s' * 32}"
    store.mutate(key, lambda record: setattr(record, "share_token_hash", token_hash(token)))
    return token


def delete_me(client, headers=None, body=None):
    return client.request(
        "DELETE",
        "/v1/account",
        json={"confirm": "DELETE"} if body is None else body,
        headers=headers or {},
    )


# Retention.


def test_expiry_math_by_owner_kind():
    retention = Retention(guest_days=30, account_days=365)
    updated = datetime(2026, 1, 1, tzinfo=UTC)
    assert retention.expiry("guest:" + "a" * 48, updated) == updated + timedelta(days=30)
    assert retention.expiry(None, updated) == updated + timedelta(days=30)
    assert retention.expiry("user:alice", updated) == updated + timedelta(days=365)
    # Naive timestamps are read as UTC.
    assert retention.expiry("user:alice", updated.replace(tzinfo=None)) == updated + timedelta(
        days=365
    )


def test_settings_drive_retention_periods():
    client, app, _ = setup(guest_retention_days=7, account_retention_days=90)
    store = app.state.job_service.store
    assert store.retention == Retention(7, 90)
    key = create(client, "alice")
    record = store.get(key)
    assert record.expires_at == record.job.updated_at + timedelta(days=90)


def test_every_save_recomputes_expires_at():
    client, app, _ = setup()
    store = app.state.job_service.store
    key = create(client, "alice")
    age(store, key, 100)
    record = store.get(key)
    assert record.expires_at == record.job.updated_at + timedelta(days=365)


def test_expired_projects_read_as_not_found_everywhere():
    client, app, _ = setup()
    store = app.state.job_service.store
    key = create(client, "alice")
    token = share(store, key)
    kept = create(client, "alice")
    age(store, key, 366)
    age(store, kept, 364)
    assert store.get(key) is None
    assert store.mutate(key, lambda record: None) is None
    assert client.get(f"/v1/jobs/{key}", headers=auth("alice")).status_code == 404
    assert client.get(f"/v1/shared/{token}").status_code == 404
    assert client.delete(f"/v1/projects/{key}", headers=auth("alice")).status_code == 404
    listed = client.get("/v1/projects", headers=auth("alice")).json()["projects"]
    assert [project["job_id"] for project in listed] == [kept]
    assert client.get(f"/v1/jobs/{kept}", headers=auth("alice")).status_code == 200


def test_guest_projects_expire_after_thirty_days():
    client, app, _ = setup()
    store = app.state.job_service.store
    assert client.post("/v1/session/guest").status_code == 200
    key = create(client)
    age(store, key, 29)
    assert client.get(f"/v1/jobs/{key}").status_code == 200
    age(store, key, 30)
    assert client.get(f"/v1/jobs/{key}").status_code == 404


def test_claiming_moves_a_guest_project_to_the_account_rule():
    client, app, _ = setup()
    store = app.state.job_service.store
    assert client.post("/v1/session/guest").status_code == 200
    key = create(client)
    age(store, key, 20)
    assert client.post(f"/v1/projects/{key}/claim", json={}, headers=auth("alice")).status_code == (
        200
    )
    record = store.get(key)
    assert record.owner_id == "user:alice"
    assert record.expires_at == record.job.updated_at + timedelta(days=365)
    # Past the guest period, the claimed project is still there.
    store._records[key].job.updated_at = now() - timedelta(days=40)
    assert client.get(f"/v1/jobs/{key}", headers=auth("alice")).status_code == 200


def sweep_client(monkeypatch, **overrides):
    monkeypatch.setattr(CloudDispatcher, "enqueue", lambda self, key, kind, **kwargs: None)
    monkeypatch.setattr(CloudDispatcher, "authorize", lambda self, header: header == "Bearer w")
    settings = Settings(
        _env_file=None,
        dispatch_backend="cloud_tasks",
        storage_backend="firestore",
        gcp_project="test",
        tasks_url="https://worker.example",
        tasks_service_account="worker@test",
        **overrides,
    )
    store = MemoryJobStore()
    client = TestClient(create_app(settings, store=store))
    client.headers["Authorization"] = "Bearer w"
    return client, store


def stored(store, key, owner, days_old):
    base = MemoryJobStore()

    job, _ = JobService(store=base).create(CreateJob(url="https://example.com"))
    record = base.get(job.job_id)
    record.job.job_id = key
    record.job.status = "done"
    record.owner_id = owner
    record.job.updated_at = now() - timedelta(days=days_old)
    # Written before retention existed: no expires_at.
    record.expires_at = None
    store._records[key] = record


def test_sweep_backfills_and_deletes_in_bounded_batches(monkeypatch):
    client, store = sweep_client(monkeypatch, retention_batch=2)
    stored(store, "a0000000-0000-4000-8000-000000000001", "user:alice", 400)
    stored(store, "a0000000-0000-4000-8000-000000000002", "user:alice", 10)
    stored(store, "a0000000-0000-4000-8000-000000000003", "guest:" + "b" * 48, 31)
    stored(store, "a0000000-0000-4000-8000-000000000004", None, 5)
    stored(store, "a0000000-0000-4000-8000-000000000005", "user:bob", 1)

    first = client.post("/internal/sweep").json()["retention"]
    assert first == {"scanned": 2, "deleted": 1, "backfilled": 1, "complete": False}
    second = client.post("/internal/sweep").json()["retention"]
    assert second == {"scanned": 2, "deleted": 1, "backfilled": 1, "complete": False}
    third = client.post("/internal/sweep").json()["retention"]
    assert third == {"scanned": 1, "deleted": 0, "backfilled": 1, "complete": True}
    assert sorted(store._records) == [
        "a0000000-0000-4000-8000-000000000002",
        "a0000000-0000-4000-8000-000000000004",
        "a0000000-0000-4000-8000-000000000005",
    ]
    assert all(record.expires_at for record in store._records.values())
    # A full cycle restarts from the beginning and finds nothing left to do.
    again = client.post("/internal/sweep").json()["retention"]
    assert again["deleted"] == 0 and again["backfilled"] == 0


def test_sweep_requires_worker_identity(monkeypatch):
    client, store = sweep_client(monkeypatch)
    stored(store, "a0000000-0000-4000-8000-000000000001", "user:alice", 400)
    assert client.post("/internal/sweep", headers={"Authorization": "Bearer x"}).status_code == 401
    assert "a0000000-0000-4000-8000-000000000001" in store._records


def test_firestore_documents_store_expires_at_as_a_timestamp():
    store = FirestoreJobStore.__new__(FirestoreJobStore)
    base = MemoryJobStore()
    stored(base, "a0000000-0000-4000-8000-000000000001", "user:alice", 1)
    record = base._records["a0000000-0000-4000-8000-000000000001"]
    record.expires_at = Retention().of(record)
    document = store._document(record)
    assert isinstance(document["expires_at"], datetime)
    assert StoredJob.model_validate(document).expires_at == record.expires_at


# Delete my data.


def test_account_deletes_everything_it_owns_and_nothing_else():
    client, app, deleted_users = setup()
    store = app.state.job_service.store
    mine = [create(client, "alice"), create(client, "alice")]
    token = share(store, mine[0])
    theirs = create(client, "bob")
    their_token = share(store, theirs)
    store.put_account("user:alice", AccountSettings(country="IN", updated_at=now()))
    store.put_account("user:bob", AccountSettings(country="IN", updated_at=now()))
    # One of alice's projects is already expired; it is deleted all the same.
    age(store, mine[1], 400)

    response = delete_me(client, auth("alice"))
    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "account",
        "projects_deleted": 2,
        "share_links_revoked": 1,
        "settings_deleted": True,
        "auth_user_deleted": True,
    }
    assert response.headers["Cache-Control"] == "no-store"
    assert deleted_users == [("fixture-project", "alice")]
    assert all(key not in store._records for key in mine)
    assert client.get(f"/v1/shared/{token}").status_code == 404
    assert store.get_account("user:alice") is None
    assert client.get("/v1/projects", headers=auth("alice")).json()["projects"] == []
    # Bob is untouched.
    assert client.get(f"/v1/jobs/{theirs}", headers=auth("bob")).status_code == 200
    assert client.get(f"/v1/shared/{their_token}").status_code == 200
    assert store.get_account("user:bob") is not None


def test_repeating_the_deletion_is_harmless():
    client, _, deleted_users = setup()
    create(client, "alice")
    assert delete_me(client, auth("alice")).json()["projects_deleted"] == 1
    again = delete_me(client, auth("alice"))
    assert again.status_code == 200
    assert again.json() == {
        "kind": "account",
        "projects_deleted": 0,
        "share_links_revoked": 0,
        "settings_deleted": False,
        "auth_user_deleted": True,
    }
    assert len(deleted_users) == 2


def test_guest_deletes_own_projects_and_loses_the_cookie():
    client, app, deleted_users = setup()
    store = app.state.job_service.store
    assert client.post("/v1/session/guest").status_code == 200
    guest = app.state.access.sessions.verify(client.cookies.get("__session"))
    key = create(client)
    token = share(store, key)
    extra = StoredJob.model_validate(store._records[key].model_dump())
    extra.job.job_id = "a0000000-0000-4000-8000-00000000000a"
    extra.share_token_hash = None
    store.create(extra)
    other = create(client, "bob")

    response = delete_me(client)
    assert response.status_code == 200, response.text
    assert response.json() == {
        "kind": "guest",
        "projects_deleted": 2,
        "share_links_revoked": 1,
        "settings_deleted": False,
        "auth_user_deleted": None,
    }
    assert deleted_users == []
    cookies = response.headers.get_list("set-cookie")
    assert any(c.startswith("__session=") and "Max-Age=0" in c for c in cookies)
    assert any(c.startswith("bs_guest=") and "Max-Age=0" in c for c in cookies)
    assert not [r for r in store._records.values() if r.owner_id == guest.owner]
    assert client.get(f"/v1/shared/{token}").status_code == 404
    assert client.get(f"/v1/jobs/{other}", headers=auth("bob")).status_code == 200


def test_identity_scoped_counters_go_but_ip_counters_stay():
    client, app, _ = setup()
    store = app.state.job_service.store
    create(client, "alice")
    create(client, "bob")
    ip_keys = [key for key in store._usage if key.startswith(("actions-ip-", "actions-global-"))]
    assert ip_keys
    alice = app.state.access.principal_usage_keys(Principal("user:alice"))
    bob = app.state.access.principal_usage_keys(Principal("user:bob"))
    assert any(store._usage.get(key) for key in alice)
    before = {key: store._usage[key] for key in ip_keys}

    assert delete_me(client, auth("alice")).status_code == 200
    assert not any(store._usage.get(key) for key in alice)
    assert any(store._usage.get(key) for key in bob)
    assert {key: store._usage[key] for key in ip_keys} == before


@pytest.mark.parametrize(
    "body",
    [{}, {"confirm": "delete"}, {"confirm": "yes"}, {"confirm": None}],
)
def test_confirmation_body_is_required(body):
    client, app, deleted_users = setup()
    key = create(client, "alice")
    response = delete_me(client, auth("alice"), body=body)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert app.state.job_service.store.get(key) is not None
    assert deleted_users == []


def test_missing_body_is_rejected():
    client, app, _ = setup()
    key = create(client, "alice")
    response = client.delete("/v1/account", headers=auth("alice"))
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
    assert app.state.job_service.store.get(key) is not None


def test_needs_identity_and_the_application_header():
    client, app, _ = setup()
    key = create(client, "alice")
    assert delete_me(client).status_code == 401
    response = delete_me(client, auth("alice") | {"X-Requested-With": ""})
    assert response.status_code == 403
    assert app.state.job_service.store.get(key) is not None


def test_deletion_is_rate_limited():
    client, _, _ = setup()
    codes = [delete_me(client, auth("alice")).status_code for _ in range(6)]
    assert codes == [200] * 5 + [429]


def test_auth_user_failure_still_deletes_the_data(caplog):
    client, app, _ = setup()
    store = app.state.job_service.store
    key = create(client, "alice")

    def fail(project, uid):
        raise RuntimeError("identity toolkit said no for alice@example.com")

    app.state.access.delete_user = fail
    response = delete_me(client, auth("alice"))
    assert response.status_code == 200
    assert response.json()["auth_user_deleted"] is False
    assert response.json()["projects_deleted"] == 1
    assert key not in store._records
    assert "AUTH_USER_DELETE_FAILED" in caplog.text and "RuntimeError" in caplog.text
    assert "ACCOUNT_DELETED" in caplog.text
    # No identifiers or provider messages in the log.
    assert "alice" not in caplog.text


class Reply:
    def __init__(self, status_code, text=""):
        self.status_code, self.text = status_code, text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class Session:
    def __init__(self, reply):
        self.reply, self.calls = reply, []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.reply


def test_identity_toolkit_delete_call():
    session = Session(Reply(200))
    delete_auth_user("fixture-project", "alice", session)
    url, kwargs = session.calls[0]
    assert url == (
        "https://identitytoolkit.googleapis.com/v1/projects/fixture-project/accounts:delete"
    )
    assert kwargs["json"] == {"localId": "alice"}
    # Already gone counts as deleted.
    gone = Reply(400, '{"error": {"message": "USER_NOT_FOUND"}}')
    delete_auth_user("fixture-project", "alice", Session(gone))
    with pytest.raises(RuntimeError):
        delete_auth_user("fixture-project", "alice", Session(Reply(403, "PERMISSION_DENIED")))


# Firestore store logic against a minimal in-process fake (no network).


class FakeSnapshot:
    def __init__(self, reference, data):
        self.reference, self.id, self.data = reference, reference.id, data
        self.exists = data is not None

    def to_dict(self):
        return None if self.data is None else dict(self.data)


class FakeRef:
    def __init__(self, collection, key):
        self.collection, self.id = collection, key

    def get(self, **kwargs):
        return FakeSnapshot(self, self.collection.docs.get(self.id))

    def set(self, data):
        self.collection.docs[self.id] = dict(data)

    def update(self, fields):
        if self.id not in self.collection.docs:
            raise NotFound("gone")
        self.collection.docs[self.id].update(fields)

    def delete(self):
        self.collection.docs.pop(self.id, None)


class FakeQuery:
    def __init__(self, collection, filters=(), after=None, count=None):
        self.source, self.filters, self.after, self.count = collection, filters, after, count

    def where(self, filter):
        return FakeQuery(self.source, (*self.filters, filter), self.after, self.count)

    def order_by(self, field):
        return self

    def select(self, fields):
        return self

    def start_after(self, values):
        return FakeQuery(self.source, self.filters, values["__name__"].id, self.count)

    def limit(self, count):
        return FakeQuery(self.source, self.filters, self.after, count)

    def stream(self):
        def match(data, condition):
            value = data.get(condition.field_path)
            if condition.op_string == "==":
                return value == condition.value
            return isinstance(value, datetime) and value <= condition.value

        docs = self.source.docs
        keys = [
            key
            for key in sorted(docs)
            if (self.after is None or key > self.after)
            and all(match(docs[key], c) for c in self.filters)
        ]
        for key in keys[: self.count]:
            yield FakeSnapshot(FakeRef(self.source, key), docs[key])


class FakeCollection(FakeQuery):
    def __init__(self, name):
        super().__init__(self)
        self.id, self.docs = name, {}

    def document(self, key):
        return FakeRef(self, key)


class FakeBatch:
    def __init__(self):
        self.refs = []

    def delete(self, ref):
        self.refs.append(ref)

    def commit(self):
        for ref in self.refs:
            ref.delete()


def fake_firestore():
    store = FirestoreJobStore.__new__(FirestoreJobStore)
    store.retention = Retention()
    store.client = type("Client", (), {"batch": staticmethod(FakeBatch)})()
    store.collection = FakeCollection("jobs")
    store.accounts = FakeCollection("jobs_accounts")
    store.usage = FakeCollection("jobs_usage")
    store.meta = FakeCollection("jobs_meta")
    return store


def put(store, key, owner, days_old, with_expiry):
    base = MemoryJobStore()
    stored(base, key, owner, days_old)
    record = base._records[key]
    record.share_token_hash = "h" if owner == "user:alice" else None
    record.expires_at = Retention().of(record) if with_expiry else None
    store.collection.docs[key] = store._document(record)


def test_firestore_retention_pass_is_bounded_and_resumable():
    store = fake_firestore()
    put(store, "a0000000-0000-4000-8000-000000000001", "user:alice", 400, True)
    put(store, "a0000000-0000-4000-8000-000000000002", "guest:" + "b" * 48, 40, False)
    put(store, "a0000000-0000-4000-8000-000000000003", "user:bob", 3, False)
    put(store, "a0000000-0000-4000-8000-000000000004", None, 1, False)

    first = store.retention_pass(2)
    # Phase 1 finds the one stored past its expiry; the scan sees it again plus #2 (legacy).
    assert first["deleted"] == 2 and first["backfilled"] == 0 and first["complete"] is False
    assert sorted(store.collection.docs) == [
        "a0000000-0000-4000-8000-000000000003",
        "a0000000-0000-4000-8000-000000000004",
    ]
    second = store.retention_pass(2)
    assert second["deleted"] == 0 and second["backfilled"] == 2 and second["complete"] is True
    assert all(isinstance(d["expires_at"], datetime) for d in store.collection.docs.values())
    assert store.meta.docs["retention"] == {"cursor": ""}


def test_firestore_reads_hide_expired_and_owner_deletion_counts():
    store = fake_firestore()
    put(store, "a0000000-0000-4000-8000-000000000001", "user:alice", 400, True)
    put(store, "a0000000-0000-4000-8000-000000000002", "user:alice", 3, True)
    put(store, "a0000000-0000-4000-8000-000000000003", "user:bob", 3, True)
    store.accounts.docs["user:alice"] = {"country": "IN"}
    assert store.get("a0000000-0000-4000-8000-000000000001") is None
    assert store.get("a0000000-0000-4000-8000-000000000002") is not None
    owned = store.owned("user:alice", "", 1)
    assert [r.job.job_id for r in owned] == ["a0000000-0000-4000-8000-000000000002"]

    removed = store.delete_owned("user:alice")
    assert removed.projects == 2 and removed.share_links == 2
    assert store.delete_account("user:alice") is True
    assert store.delete_account("user:alice") is False
    assert list(store.collection.docs) == ["a0000000-0000-4000-8000-000000000003"]
    store.usage.docs["k"] = {"count": 1}
    store.delete_usage(["k", "missing"])
    assert store.usage.docs == {}
