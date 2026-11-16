"""/members 동작과 소유자 조건을 확인한다. DB 대신 가짜 connection 을 쓴다."""
import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user
from app.main import app
from app.routers import members

ME = "11111111-1111-1111-1111-111111111111"
MID = "22222222-2222-2222-2222-222222222222"
NAMES = {"MILK": "우유", "EGG": "달걀", "PEANUT": "땅콩"}


class FakeResult:
    def __init__(self, row=None, rowcount=0):
        self.row = row
        self.rowcount = rowcount

    def mappings(self):
        return self

    def all(self):
        return [self.row] if self.row else []

    def first(self):
        return self.row


class FakeConn:
    """found=False 이면 update/delete 가 0행(없거나 남의 것), full=True 이면 insert 조건(10명 미만)이 거짓."""

    def __init__(self):
        self.calls = []
        self.found = False
        self.full = False

    def execute(self, stmt, params=None):
        sql, params = str(stmt), dict(params or {})
        self.calls.append((sql, params))
        head = sql.lstrip().split(None, 1)[0]
        if head == "select" and "pg_advisory_xact_lock" in sql:
            return FakeResult()
        if head == "insert":
            if self.full:
                return FakeResult()
            return FakeResult(self._row(params))
        if head == "update":
            return FakeResult(self._row(params) if self.found else None)
        if head == "delete":
            return FakeResult(rowcount=1 if self.found else 0)
        return FakeResult()

    @staticmethod
    def _row(params):
        return {"id": uuid.UUID(MID), "name": params["name"], "relation": params["rel"],
                "allergen_codes": params["codes"], "notes": params.get("notes"),
                "avatar_color": params.get("color"), "created_at": "2026-01-01T00:00:00Z"}


class FakeEngine:
    def __init__(self, conn):
        self.conn = conn

    def _ctx(self):
        conn = self.conn

        class Ctx:
            def __enter__(self):
                return conn

            def __exit__(self, *a):
                return False
        return Ctx()

    begin = connect = _ctx


@pytest.fixture()
def env(monkeypatch):
    conn = FakeConn()
    monkeypatch.setattr(members, "get_engine", lambda: FakeEngine(conn))
    monkeypatch.setattr(members, "get_dictionary", lambda: SimpleNamespace(names=NAMES))
    app.dependency_overrides[current_user] = lambda: CurrentUser(id=ME, is_anonymous=False)
    yield TestClient(app), conn
    app.dependency_overrides.clear()


def body(**kw):
    return {"name": "민수", "relation": "자녀", "allergen_codes": ["MILK"], **kw}


def test_create_returns_201_and_member(env):
    client, conn = env
    r = client.post("/members", json=body())
    assert r.status_code == 201
    assert r.json() == {"id": MID, "name": "민수", "relation": "자녀",
                        "allergen_codes": ["MILK"], "notes": None, "avatar_color": None,
                        "created_at": "2026-01-01T00:00:00Z"}
    insert_sql, params = conn.calls[-1]
    assert insert_sql.lstrip().startswith("insert into member (owner_id,")
    assert params["owner"] == ME


def test_unknown_code_is_422_and_names_it(env):
    client, conn = env
    r = client.post("/members", json=body(allergen_codes=["MILK", "NOPE"]))
    assert r.status_code == 422
    assert "NOPE" in r.json()["detail"] and "MILK" not in r.json()["detail"]
    assert conn.calls == []


def test_duplicate_codes_removed_keeping_order(env):
    client, conn = env
    r = client.post("/members", json=body(allergen_codes=["EGG", "MILK", "EGG", "MILK"]))
    assert r.status_code == 201
    assert r.json()["allergen_codes"] == ["EGG", "MILK"]
    assert conn.calls[-1][1]["codes"] == ["EGG", "MILK"]


def test_empty_codes_allowed(env):
    client, _ = env
    assert client.post("/members", json=body(allergen_codes=[])).status_code == 201


def test_blank_name_is_422(env):
    client, conn = env
    assert client.post("/members", json=body(name="   ")).status_code == 422
    assert conn.calls == []


def test_name_31_chars_is_422_and_30_is_ok(env):
    client, conn = env
    assert client.post("/members", json=body(name="가" * 31)).status_code == 422
    assert conn.calls == []
    assert client.post("/members", json=body(name="가" * 30)).status_code == 201


def test_profile_fields_saved_and_returned(env):
    client, conn = env
    r = client.post("/members", json=body(notes="  견과류 주의  ", avatar_color="#ff8800"))
    assert r.status_code == 201
    assert r.json()["notes"] == "견과류 주의" and r.json()["avatar_color"] == "#ff8800"
    _, params = conn.calls[-1]
    assert params["notes"] == "견과류 주의" and params["color"] == "#ff8800"


def test_put_replaces_profile_fields_and_missing_become_null(env):
    client, conn = env
    conn.found = True
    r = client.put(f"/members/{MID}", json=body(notes="메모", avatar_color="blue"))
    assert r.json()["notes"] == "메모" and r.json()["avatar_color"] == "blue"
    r = client.put(f"/members/{MID}", json=body())
    assert r.json()["notes"] is None and r.json()["avatar_color"] is None
    assert conn.calls[-1][1]["notes"] is None and conn.calls[-1][1]["color"] is None


def test_notes_201_chars_is_422_and_200_is_ok(env):
    client, conn = env
    assert client.post("/members", json=body(notes="가" * 201)).status_code == 422
    assert conn.calls == []
    assert client.post("/members", json=body(notes="가" * 200)).status_code == 201


def test_avatar_color_41_chars_is_422_and_40_is_ok(env):
    client, conn = env
    assert client.post("/members", json=body(avatar_color="a" * 41)).status_code == 422
    assert conn.calls == []
    assert client.post("/members", json=body(avatar_color="a" * 40)).status_code == 201


def test_blank_notes_and_color_become_null(env):
    client, conn = env
    r = client.post("/members", json=body(notes="   ", avatar_color="  "))
    assert r.status_code == 201
    assert r.json()["notes"] is None and r.json()["avatar_color"] is None
    assert conn.calls[-1][1]["notes"] is None and conn.calls[-1][1]["color"] is None


def test_request_without_profile_fields_still_works(env):
    client, _ = env
    r = client.post("/members", json={"name": "민수", "allergen_codes": []})
    assert r.status_code == 201
    assert r.json()["notes"] is None and r.json()["avatar_color"] is None


def test_unknown_field_is_422(env):
    client, conn = env
    assert client.post("/members", json=body(owner_id=ME)).status_code == 422
    assert conn.calls == []


def test_eleventh_create_is_409(env):
    client, conn = env
    conn.full = True
    r = client.post("/members", json=body())
    assert r.status_code == 409
    assert "10" in r.json()["detail"]


def test_create_locks_before_insert_in_same_connection(env):
    client, conn = env
    client.post("/members", json=body())
    assert "pg_advisory_xact_lock" in conn.calls[0][0]
    assert conn.calls[1][0].lstrip().startswith("insert into member")


def test_missing_token_is_401():
    app.dependency_overrides.clear()
    client = TestClient(app)
    assert client.get("/members").status_code == 401
    assert client.post("/members", json=body()).status_code == 401
    assert client.put(f"/members/{MID}", json=body()).status_code == 401
    assert client.delete(f"/members/{MID}").status_code == 401


def test_put_other_or_missing_member_is_404(env):
    client, conn = env
    assert client.put(f"/members/{MID}", json=body()).status_code == 404
    sql, params = conn.calls[-1]
    assert "id = :i and owner_id = :owner" in sql
    assert params["i"] == uuid.UUID(MID) and params["owner"] == ME


def test_put_own_member_replaces(env):
    client, conn = env
    conn.found = True
    r = client.put(f"/members/{MID}", json=body(name="  지수  ", relation=None, allergen_codes=["EGG"]))
    assert r.status_code == 200
    assert r.json()["name"] == "지수" and r.json()["relation"] is None
    assert r.json()["allergen_codes"] == ["EGG"]


def test_delete_other_or_missing_member_is_404(env):
    client, conn = env
    assert client.delete(f"/members/{MID}").status_code == 404
    sql, params = conn.calls[-1]
    assert "id = :i and owner_id = :owner" in sql
    assert params["i"] == uuid.UUID(MID) and params["owner"] == ME


def test_delete_own_member_is_204(env):
    client, conn = env
    conn.found = True
    r = client.delete(f"/members/{MID}")
    assert r.status_code == 204 and r.content == b""


def test_every_query_is_scoped_to_current_user(env):
    client, conn = env
    conn.found = True
    client.get("/members")
    client.post("/members", json=body())
    client.put(f"/members/{MID}", json=body())
    client.delete(f"/members/{MID}")
    assert len(conn.calls) == 5   # list, lock, insert, update, delete
    for sql, params in conn.calls:
        assert "owner_id" in sql or "pg_advisory_xact_lock" in sql
        assert params["owner"] == ME
        assert ME not in sql   # 값은 바인딩으로만 전달한다


def test_list_orders_by_created_at_asc(env):
    client, conn = env
    assert client.get("/members").json() == []
    sql, _ = conn.calls[-1]
    assert "where owner_id = :owner" in sql and "order by created_at asc" in sql


@pytest.mark.parametrize("method", ["put", "delete"])
def test_bad_uuid_is_422(env, method):
    client, conn = env
    kwargs = {"json": body()} if method == "put" else {}
    assert getattr(client, method)("/members/not-a-uuid", **kwargs).status_code == 422
    assert conn.calls == []
