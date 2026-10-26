"""OCR 테스트. LLM 호출은 전부 가짜로 바꿔서 네트워크·키 없이 실행한다."""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app
from app.routers import ocr as ocr_router
from app.services import ocr
from app.services.matcher import Dictionary

SEED = Path(__file__).resolve().parents[1] / "DB" / "seed.json"
pytestmark = pytest.mark.skipif(not SEED.exists(), reason="backend/DB/seed.json 없음")

JPEG = b"\xff\xd8\xff\xe0" + b"0" * 100
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture(scope="module")
def d():
    return Dictionary.from_seed(SEED)


@pytest.fixture()
def client(monkeypatch, d):
    monkeypatch.setattr(ocr_router, "get_dictionary", lambda: d)
    ocr_router._hits.clear()
    return TestClient(app)


def fake_llm(result):
    return lambda image, mime, names: result


def post(client, data=JPEG, name="a.jpg"):
    return client.post("/ocr/allergens", files={"image": (name, data, "application/octet-stream")})


def test_detect_image_type():
    assert ocr.detect_image_type(JPEG) == "image/jpeg"
    assert ocr.detect_image_type(PNG) == "image/png"
    assert ocr.detect_image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert ocr.detect_image_type(b"GIF89a") is None
    assert ocr.detect_image_type(b"") is None


def test_parse_handles_code_fence_and_garbage():
    assert ocr.parse_llm_content('```json\n{"a": 1}\n```') == {"a": 1}
    assert ocr.parse_llm_content([{"type": "text", "text": '{"a": 2}'}]) == {"a": 2}
    for bad in ("", "no json", "[1,2]", None, "{broken"):
        with pytest.raises(ocr.OcrError):
            ocr.parse_llm_content(bad)


def test_combine_merges_dictionary_and_llm(d):
    llm = {"is_ingredient_label": True,
           "ingredients_text": "밀가루, 정제수, 탈지분유",
           "allergens": [{"code": "WHEAT", "evidence": "밀가루"},
                         {"code": "SOYBEAN", "evidence": "레시틴?"},   # 사전엔 없고 LLM 만 지목
                         {"code": "NOT_A_CODE", "evidence": "x"}],     # 지어낸 코드는 버린다
           "may_contain": ["EGG", "BOGUS"]}
    r = ocr.combine(llm, d)
    by = {a["code"]: a for a in r["allergens"]}
    assert by["WHEAT"]["level"] == "danger" and by["WHEAT"]["sources"] == ["dictionary", "llm"]
    assert by["MILK"]["level"] == "danger" and by["MILK"]["sources"] == ["dictionary"]   # LLM 이 놓쳐도 사전이 보완
    assert by["SOYBEAN"]["level"] == "caution" and by["SOYBEAN"]["sources"] == ["llm"]
    assert "NOT_A_CODE" not in by
    assert [a["level"] for a in r["allergens"]] == sorted((a["level"] for a in r["allergens"]), key=lambda x: x != "danger")
    assert r["may_contain"] == [{"code": "EGG", "name_ko": d.names["EGG"]}]


def test_combine_tolerates_bad_shapes(d):
    r = ocr.combine({"ingredients_text": None, "allergens": "x", "may_contain": None}, d)
    assert r["allergens"] == [] and r["ingredients_text"] == ""


def test_endpoint_ok(client, monkeypatch):
    monkeypatch.setattr(ocr, "call_llm", fake_llm(
        {"is_ingredient_label": True, "ingredients_text": "땅콩, 설탕", "allergens": [], "may_contain": []}))
    r = post(client)
    assert r.status_code == 200
    body = r.json()
    assert [a["code"] for a in body["allergens"]] == ["PEANUT"]
    assert body["disclaimer"] and body["model"]


def test_endpoint_rejects_non_image_and_big_file(client, monkeypatch):
    assert post(client, b"hello world", "a.txt").status_code == 415
    monkeypatch.setenv("OCR_MAX_IMAGE_MB", "1")
    assert post(client, JPEG + b"0" * (1024 * 1024)).status_code == 413


def test_endpoint_not_a_label_is_422(client, monkeypatch):
    monkeypatch.setattr(ocr, "call_llm", fake_llm(
        {"is_ingredient_label": False, "ingredients_text": "", "allergens": [], "may_contain": []}))
    assert post(client).status_code == 422


def test_endpoint_maps_llm_errors(client, monkeypatch):
    def boom(*a):
        raise ocr.OcrError(504, "시간 초과")
    monkeypatch.setattr(ocr, "call_llm", boom)
    r = post(client)
    assert r.status_code == 504 and "시간" in r.json()["detail"]


def test_missing_key_is_503_without_leaking(client, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    r = post(client)
    assert r.status_code == 503 and "OPENROUTER_API_KEY" in r.json()["detail"]


def test_rate_limit(client, monkeypatch):
    monkeypatch.setenv("OCR_RATE_LIMIT_PER_MIN", "2")
    monkeypatch.setattr(ocr, "call_llm", fake_llm(
        {"is_ingredient_label": True, "ingredients_text": "밀가루", "allergens": [], "may_contain": []}))
    assert [post(client).status_code for _ in range(3)] == [200, 200, 429]


def test_api_key_never_in_request_logs_or_errors(monkeypatch, d):
    """401 같은 실패에도 키가 응답/예외 메시지에 새지 않는다."""
    import httpx
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-v1-SECRETSECRET")
    monkeypatch.setattr(httpx, "post", lambda *a, **k: httpx.Response(401, json={"error": "bad key sk-or-v1-SECRETSECRET"}))
    with pytest.raises(ocr.OcrError) as e:
        ocr.call_llm(JPEG, "image/jpeg", d.names)
    assert "SECRET" not in e.value.message


def test_request_body_has_image_and_closed_code_set(monkeypatch, d):
    import httpx
    sent = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        sent.update(url=url, body=json, headers=headers)
        content = '{"is_ingredient_label": true, "ingredients_text": "밀", "allergens": [], "may_contain": []}'
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(httpx, "post", fake_post)
    out = ocr.call_llm(JPEG, "image/jpeg", d.names)
    assert out["is_ingredient_label"] is True
    assert sent["url"].startswith("https://openrouter.ai/")
    part = sent["body"]["messages"][0]["content"][1]["image_url"]["url"]
    assert part.startswith("data:image/jpeg;base64,")
    enum = sent["body"]["response_format"]["json_schema"]["schema"]["properties"]["allergens"]["items"]["properties"]["code"]["enum"]
    assert enum == list(d.names)
    assert config.openrouter_model() == sent["body"]["model"]
