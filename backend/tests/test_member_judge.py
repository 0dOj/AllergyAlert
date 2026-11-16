"""판정과 이력의 member_id 연결을 확인한다. DB 대신 가짜 connection 을 쓰고 판정은 실제 matcher 로 한다."""
import uuid

import pytest
from fastapi.testclient import TestClient

from app.auth import CurrentUser, current_user, user_if_member
from app.main import app
from app.routers import history, products
from app.services.matcher import Dictionary

ME = "11111111-1111-1111-1111-111111111111"
OTHER = "33333333-3333-3333-3333-333333333333"
MID = "22222222-2222-2222-2222-222222222222"
RN = "123"

D = Dictionary({"MILK": "우유", "EGG": "달걀"}, {"MILK": ["우유"], "EGG": ["달걀"]},
               {"MILK": [], "EGG": []}, [])
PRODUCT = {"in_reports": True, "raw_material": "우유, 설탕", "p_name": "테스트", "p_maker": "m",
           "p_type": "t", "barcode": "880", "source": "C005", "b_name": None, "b_maker": None,
           "b_type": None, "shelf_life_text": None, "discontinued": False, "in_barcodes": True}


class FakeResult:
    def __init__(self, row=None):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        return {"id": 7, "scanned_at": "2026-01-01T00:00:00"}

    def all(self):
        return [self.row] if self.row else []


class FakeConn:
    """member: 구성원 행(소유자는 ME). profile: 공유 프로필 코드."""

    def __init__(self, member=None, profile=("EGG",)):
        self.member = member
        self.profile = list(profile)
        self.calls = []

    def execute(self, stmt, params=None):
        sql, params = str(stmt), dict(params or {})
        self.calls.append((sql, params))
        if "from member where id = :i and owner_id = :owner" in sql:
            ok = self.member is not None and params["owner"] == ME
            return FakeResult(self.member if ok else None)
        if "from user_profile" in sql:
            return FakeResult((self.profile,) if self.profile else None)
        if "cast(:r as text)" in sql:
            return FakeResult(PRODUCT)
        return FakeResult()

    def find(self, prefix):
        return [(s, p) for s, p in self.calls if s.lstrip().startswith(prefix)]


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


def member_row(codes, name="민수"):
    return {"id": uuid.UUID(MID), "name": name, "allergen_codes": codes}


def patch_db(monkeypatch, conn):
    for mod in (products, history):
        monkeypatch.setattr(mod, "get_engine", lambda: FakeEngine(conn))
        monkeypatch.setattr(mod, "get_dictionary", lambda: D)


@pytest.fixture()
def env(monkeypatch):
    conn = FakeConn(member=member_row(["MILK"]))
    patch_db(monkeypatch, conn)
    me = CurrentUser(id=ME, is_anonymous=False)
    app.dependency_overrides[user_if_member] = lambda: me
    app.dependency_overrides[current_user] = lambda: me
    yield TestClient(app), conn
    app.dependency_overrides.clear()


def test_without_member_id_uses_shared_profile_and_no_token(monkeypatch):
    conn = FakeConn(profile=["EGG"])
    patch_db(monkeypatch, conn)
    app.dependency_overrides.clear()
    r = TestClient(app).get(f"/products/{RN}/judge")
    assert r.status_code == 200
    body = r.json()
    assert body["profile"] == ["EGG"] and body["verdict"] == "safe" and body["member"] is None
    assert {"product", "verdict", "matched", "allergens", "unresolved", "reasons", "disclaimer"} <= set(body)
    assert not any("from member" in s for s, _ in conn.calls)


def test_empty_shared_profile_is_still_set_profile_400(monkeypatch):
    patch_db(monkeypatch, FakeConn(profile=[]))
    app.dependency_overrides.clear()
    r = TestClient(app).get(f"/products/{RN}/judge")
    assert r.status_code == 400 and r.json()["action"] == "set_profile"


def test_member_id_without_token_is_401(monkeypatch):
    conn = FakeConn(member=member_row(["MILK"]))
    patch_db(monkeypatch, conn)
    app.dependency_overrides.clear()
    r = TestClient(app).get(f"/products/{RN}/judge", params={"member_id": MID})
    assert r.status_code == 401
    assert conn.calls == []


def test_other_users_member_is_404(env):
    client, conn = env
    app.dependency_overrides[user_if_member] = lambda: CurrentUser(id=OTHER, is_anonymous=False)
    r = client.get(f"/products/{RN}/judge", params={"member_id": MID})
    assert r.status_code == 404
    assert not any("cast(:r as text)" in s for s, _ in conn.calls)   # 제품 조회까지 가지 않는다


def test_missing_member_is_404(env):
    client, conn = env
    conn.member = None
    assert client.get(f"/products/{RN}/judge", params={"member_id": MID}).status_code == 404


def test_member_with_no_codes_is_400_set_allergens(env):
    client, conn = env
    conn.member = member_row([])
    r = client.get(f"/products/{RN}/judge", params={"member_id": MID})
    assert r.status_code == 400 and r.json()["action"] == "set_allergens"


def test_member_with_only_unknown_codes_is_400_not_500(env):
    client, conn = env
    conn.member = member_row(["NOPE"])
    r = client.get(f"/products/{RN}/judge", params={"member_id": MID})
    assert r.status_code == 400 and r.json()["action"] == "set_allergens"


def test_value_error_from_judge_is_400_for_member(env, monkeypatch):
    client, _ = env

    def boom(*a):
        raise ValueError("선택된 알레르겐이 없습니다.")
    monkeypatch.setattr(products, "build_result", boom)
    r = client.get(f"/products/{RN}/judge", params={"member_id": MID})
    assert r.status_code == 400 and r.json()["action"] == "set_allergens"


def test_member_judged_with_member_codes_and_response_has_member(env):
    client, conn = env
    conn.profile = ["EGG"]    # 공유 프로필은 쓰이지 않아야 한다
    r = client.get(f"/products/{RN}/judge", params={"member_id": MID})
    assert r.status_code == 200
    body = r.json()
    assert body["verdict"] == "danger" and body["profile"] == ["MILK"]
    assert body["member"] == {"id": MID, "name": "민수"}
    assert not any("from user_profile" in s for s, _ in conn.calls)


def test_profile_field_has_only_codes_used(env):
    client, conn = env
    conn.member = member_row(["MILK", "NOPE", "MILK"])
    r = client.get(f"/products/{RN}/judge", params={"member_id": MID})
    assert r.json()["profile"] == ["MILK"]


def test_bad_uuid_is_422(env):
    client, conn = env
    assert client.get(f"/products/{RN}/judge", params={"member_id": "nope"}).status_code == 422
    assert client.post("/history", json={"report_no": RN, "member_id": "nope"}).status_code == 422
    assert client.get("/history", params={"member_id": "nope"}).status_code == 422
    assert conn.calls == []


def test_history_post_binds_member_id(env):
    client, conn = env
    r = client.post("/history", json={"report_no": RN, "member_id": MID})
    assert r.status_code == 201
    assert r.json()["member"] == {"id": MID, "name": "민수"}
    (sql, params), = conn.find("insert into scan_history")
    assert "member_id" in sql and params["mid"] == MID and params["owner"] == ME


def test_history_post_without_member_uses_profile_and_null_member(env):
    client, conn = env
    r = client.post("/history", json={"report_no": RN})
    assert r.status_code == 201 and r.json()["profile"] == ["EGG"] and r.json()["member"] is None
    (_, params), = conn.find("insert into scan_history")
    assert params["mid"] is None


def test_history_post_other_member_404_and_empty_member_400(env):
    client, conn = env
    conn.member = None
    assert client.post("/history", json={"report_no": RN, "member_id": MID}).status_code == 404
    conn.member = member_row([])
    r = client.post("/history", json={"report_no": RN, "member_id": MID})
    assert r.status_code == 400 and r.json()["action"] == "set_allergens"
    assert conn.find("insert into scan_history") == []


def test_history_list_has_owner_condition_left_join_and_member_columns(env):
    client, conn = env
    assert client.get("/history").status_code == 200
    (sql, params), = conn.calls
    assert "left join member m" in sql and "where h.owner_id = :owner" in sql
    assert "h.member_id" in sql and "m.name as member_name" in sql
    assert "mid" not in params and "h.member_id = :mid" not in sql


def test_history_list_member_filter_keeps_owner_condition(env):
    client, conn = env
    assert client.get("/history", params={"member_id": MID}).json() == []
    (sql, params), = conn.calls
    assert "h.owner_id = :owner" in sql and "h.member_id = :mid" in sql
    assert params["owner"] == ME and params["mid"] == uuid.UUID(MID)
