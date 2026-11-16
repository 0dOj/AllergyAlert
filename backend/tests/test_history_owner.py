"""이력 쿼리에 소유자 조건이 들어가는지 확인한다. DB 대신 가짜 connection 을 쓴다."""
import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user
from app.main import app
from app.routers import history

ME = "11111111-1111-1111-1111-111111111111"


class FakeResult:
    rowcount = 0

    def mappings(self):
        return self

    def all(self):
        return []

    def first(self):
        return None

    def one(self):
        return {"id": 1, "scanned_at": "2026-01-01T00:00:00"}


class FakeConn:
    def __init__(self):
        self.calls = []

    def execute(self, stmt, params=None):
        self.calls.append((str(stmt), params or {}))
        return FakeResult()


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
    monkeypatch.setattr(history, "get_engine", lambda: FakeEngine(conn))
    monkeypatch.setattr(history, "get_profile_codes", lambda c: ["MILK"])
    monkeypatch.setattr(history, "get_dictionary", lambda: None)
    monkeypatch.setattr(history, "build_result", lambda *a: {
        "product": {"barcode": "880", "product_name": "x"}, "verdict": "safe"})
    app.dependency_overrides[current_user] = lambda: CurrentUser(id=ME, is_anonymous=True)
    yield TestClient(app), conn
    app.dependency_overrides.clear()


def last(conn):
    assert len(conn.calls) == 1
    return conn.calls[0]


def test_list_filters_by_owner(env):
    client, conn = env
    assert client.get("/history").status_code == 200
    sql, params = last(conn)
    assert "where owner_id = :owner" in sql and params["owner"] == ME


def test_read_filters_by_owner_and_other_is_404(env):
    client, conn = env
    assert client.get("/history/5").status_code == 404   # 행이 없는 것 = 남의 이력과 같은 상황
    sql, params = last(conn)
    assert "id = :i and owner_id = :owner" in sql and params == {"i": 5, "owner": ME}


def test_delete_filters_by_owner_and_other_is_404(env):
    client, conn = env
    assert client.delete("/history/5").status_code == 404
    sql, params = last(conn)
    assert "id = :i and owner_id = :owner" in sql and params == {"i": 5, "owner": ME}


def test_insert_sets_owner(env):
    client, conn = env
    r = client.post("/history", json={"report_no": "123", "barcode": "8801007702780"})
    assert r.status_code == 201
    sql, params = last(conn)
    assert sql.lstrip().startswith("insert into scan_history (owner_id,") and params["owner"] == ME


def test_input_length_limits(env):
    client, conn = env
    assert client.post("/history", json={"report_no": "1" * 31}).status_code == 422
    assert client.post("/history", json={"report_no": "1", "barcode": "1" * 21}).status_code == 422
    assert conn.calls == []
