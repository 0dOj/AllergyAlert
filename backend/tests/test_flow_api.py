"""프로필 -> 판정 -> 이력 전체 흐름. 실제 DB 에 쓰기를 하므로 ALLOW_DB_WRITE_TESTS=1 일 때만 실행한다.
(시작 전 프로필을 저장해 두고 끝나면 복원하며, 만든 이력은 삭제한다.)"""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT  # noqa: F401  (.env 로드)

pytestmark = pytest.mark.skipif(
    not (os.environ.get("DATABASE_URL") and os.environ.get("ALLOW_DB_WRITE_TESTS") == "1"),
    reason="DATABASE_URL + ALLOW_DB_WRITE_TESTS=1 필요 (DB 에 쓰기)")

SPAGHETTI = "19950306274362"      # 건면, 채종유(...), 혼합제제  -> 밀: caution
MEMIL = "19960080359718"          # 메밀가루 x2, 밀가루
DONGCHIMI = "2000047506963"       # 안전 제품


@pytest.fixture(scope="module")
def client():
    from app.main import app
    c = TestClient(app)
    original = c.get("/profile").json()["allergens"]
    created: list[int] = []
    c.created = created
    yield c
    for i in created:
        c.delete(f"/history/{i}")
    c.put("/profile", json={"allergens": original})


def test_allergens_list(client):
    r = client.get("/allergens").json()
    assert len(r) == 22 and {"code", "name_ko", "is_statutory"} <= set(r[0])


def test_empty_profile_gives_400(client):
    assert client.put("/profile", json={"allergens": []}).status_code == 200
    r = client.get(f"/products/{DONGCHIMI}/judge")
    assert r.status_code == 400 and r.json()["action"] == "set_profile"
    assert client.post("/history", json={"report_no": DONGCHIMI}).status_code == 400


def test_profile_validation_and_dedupe(client):
    assert client.put("/profile", json={"allergens": ["NOPE"]}).status_code == 422
    r = client.put("/profile", json={"allergens": ["MILK", "WHEAT", "MILK"]}).json()
    assert r["allergens"] == ["MILK", "WHEAT"]
    assert client.get("/profile").json()["allergens"] == ["MILK", "WHEAT"]
    assert [i["name_ko"] for i in client.get("/profile").json()["items"]] == ["우유", "밀"]


def test_judge_uses_saved_profile(client):
    client.put("/profile", json={"allergens": ["WHEAT"]})
    r = client.get(f"/products/{MEMIL}/judge").json()
    assert r["verdict"] == "danger" and r["profile"] == ["WHEAT"]
    assert [(m["start"], m["end"]) for m in r["matched"]] == [(12, 15)]
    assert r["product"]["product_name"].endswith("메밀부침가루") and "참고용" in r["disclaimer"]
    # 메밀만 선택하면 메밀가루 두 곳
    client.put("/profile", json={"allergens": ["BUCKWHEAT"]})
    assert len(client.get(f"/products/{MEMIL}/judge").json()["matched"]) == 2


def test_judge_compound_is_caution_and_unknown_is_404(client):
    client.put("/profile", json={"allergens": ["WHEAT"]})
    r = client.get(f"/products/{SPAGHETTI}/judge").json()
    assert r["verdict"] == "caution" and r["reasons"] == ["compound"]
    assert client.get("/products/000000000/judge").status_code == 404


def test_history_snapshot_is_not_recomputed(client):
    client.put("/profile", json={"allergens": ["WHEAT"]})
    r = client.post("/history", json={"report_no": MEMIL, "barcode": "8801007702780"})
    assert r.status_code == 201
    hid = r.json()["id"]
    client.created.append(hid)
    assert r.json()["verdict"] == "danger"
    # 프로필을 바꿔도 저장된 판정은 그대로
    client.put("/profile", json={"allergens": ["MILK"]})
    saved = client.get(f"/history/{hid}").json()
    assert saved["verdict"] == "danger" and saved["profile"] == ["WHEAT"]
    assert client.get(f"/products/{MEMIL}/judge").json()["verdict"] == "safe"     # 새로 계산하면 다름
    row = next(i for i in client.get("/history").json() if i["id"] == hid)
    assert row["verdict"] == "danger" and row["barcode"] == "8801007702780"


def test_history_order_limit_and_delete(client):
    client.put("/profile", json={"allergens": ["MILK"]})
    ids = []
    for _ in range(2):
        ids.append(client.post("/history", json={"report_no": DONGCHIMI}).json()["id"])
    client.created.extend(ids)
    listing = client.get("/history").json()
    assert len(listing) <= 50
    assert [i["id"] for i in listing if i["id"] in ids] == sorted(ids, reverse=True)   # 최근순
    assert client.delete(f"/history/{ids[0]}").status_code == 204
    assert client.get(f"/history/{ids[0]}").status_code == 404
    assert client.delete(f"/history/{ids[0]}").status_code == 404


def test_product_without_raw_material_is_caution(client):
    # barcodes 에는 있으나 product_reports 에 없는 제품 (포장육·수입식품 등)
    from sqlalchemy import text

    from app.db import get_engine
    with get_engine().connect() as conn:
        rn = conn.execute(text(
            "select b.report_no from barcodes b where not exists "
            "(select 1 from product_reports p where p.report_no = b.report_no) limit 1")).scalar()
    client.put("/profile", json={"allergens": ["MILK"]})
    r = client.get(f"/products/{rn}/judge").json()
    assert r["verdict"] == "caution" and r["reasons"] == ["no_raw_material"]
    assert r["product"]["raw_material"] is None and r["product"]["product_name"]
