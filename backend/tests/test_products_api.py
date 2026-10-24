"""DB 연결이 필요한 테스트. DATABASE_URL 이 없으면 건너뛴다."""
import os

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT  # noqa: F401  (.env 로드)

pytestmark = pytest.mark.skipif(not os.environ.get("DATABASE_URL"), reason="DATABASE_URL 없음")


@pytest.fixture(scope="module")
def client():
    from app.main import app
    return TestClient(app)


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_lookup_found(client):
    r = client.get("/products/barcode/8801118001802")
    assert r.status_code == 200
    body = r.json()
    assert body["source"] == "C005"
    assert body["product_name"] == "스파게티면"
    assert body["has_raw_material"] is True
    assert body["discontinued"] in (True, False)


def test_lookup_not_found_is_normal_branch(client):
    r = client.get("/products/barcode/0000000000000")
    assert r.status_code == 404
    assert r.json()["fallback"] == "search_by_name"


def test_lookup_with_hyphens_is_normalized(client):
    assert client.get("/products/barcode/880-1118-001802").status_code == 200


def test_too_short_is_422(client):
    assert client.get("/products/barcode/1234").status_code == 422


def test_dictionary_from_db_equals_seed(client):
    """DB 에 올라간 사전이 seed.json 과 같은지 (시드 적재 확인)"""
    from pathlib import Path

    from app.db import get_engine
    from app.services.matcher import Dictionary

    seed = Path(__file__).resolve().parents[1] / "DB" / "seed.json"
    if not seed.exists():
        pytest.skip("seed.json 없음")
    with get_engine().connect() as conn:
        db = Dictionary.from_db(conn)
    s = Dictionary.from_seed(seed)
    assert db.names == s.names
    assert {k: sorted(v) for k, v in db.keywords.items()} == {k: sorted(v) for k, v in s.keywords.items()}
    assert {k: sorted(v) for k, v in db.exclusions.items()} == {k: sorted(v) for k, v in s.exclusions.items()}
    assert sorted(db.rules) == sorted(s.rules)


# ---------- F-04 제품명 검색 (읽기 전용) ----------
def test_search_validation(client):
    assert client.get("/products/search?q=").status_code == 422
    assert client.get("/products/search?q=a").status_code == 422
    assert client.get("/products/search").status_code == 422


def test_search_basic_limit_and_fields(client):
    r = client.get("/products/search", params={"q": "김치"})
    assert r.status_code == 200
    items = r.json()
    assert 0 < len(items) <= 20
    assert all("김치" in i["product_name"] for i in items)
    assert {"report_no", "product_name", "maker_name", "food_type"} <= set(items[0])


def test_search_no_result_is_200_empty_list(client):
    r = client.get("/products/search", params={"q": "zzqqxwv"})
    assert r.status_code == 200 and r.json() == []


def test_search_multiple_words_and_literal_wildcards(client):
    items = client.get("/products/search", params={"q": "김치 볶음밥"}).json()
    assert items and all("김치" in i["product_name"] and "볶음밥" in i["product_name"] for i in items)
    # % 와 _ 는 글자 그대로 검색한다 (모든 행에 걸리지 않는다)
    pct = client.get("/products/search", params={"q": "100%"}).json()
    assert pct and all("100%" in i["product_name"] for i in pct)
    assert client.get("/products/search", params={"q": "__"}).json() == [] or all(
        "__" in i["product_name"] for i in client.get("/products/search", params={"q": "__"}).json())


def test_search_sql_injection_text_is_harmless(client):
    r = client.get("/products/search", params={"q": "'; drop table barcodes; --"})
    assert r.status_code == 200 and r.json() == []
    assert client.get("/products/barcode/8801118001802").status_code == 200


def test_search_relevance_sort(client):
    items = client.get("/products/search", params={"q": "김치", "sort": "relevance"}).json()
    keys = [(len(i["product_name"]), i["product_name"]) for i in items]
    assert keys == sorted(keys)


def test_search_scope_barcodes(client):
    items = client.get("/products/search", params={"q": "스파게티", "scope": "barcodes"}).json()
    assert items and {"barcode", "discontinued"} <= set(items[0])


def test_search_timeout_returns_503(client, monkeypatch):
    monkeypatch.setenv("SEARCH_TIMEOUT_MS", "1")
    r = client.get("/products/search", params={"q": "zzqqxwv"})
    assert r.status_code == 503 and "오래 걸려" in r.json()["detail"]
    monkeypatch.delenv("SEARCH_TIMEOUT_MS")
    assert client.get("/products/search", params={"q": "zzqqxwv"}).status_code == 200   # 풀이 정상 복구
