import pytest

from app.services.search import build_where, escape_like, parse_query


# ---------- 순수 함수 (DB 불필요) ----------
def test_parse_query_rules():
    assert parse_query("  진라면   매운맛 ") == ["진라면", "매운맛"]
    for bad in ("", " ", "a"):
        with pytest.raises(ValueError):
            parse_query(bad)
    assert parse_query("김치") == ["김치"]
    assert parse_query("쏘 팝") == ["쏘", "팝"]              # 합쳐서 2글자 이상이면 허용
    with pytest.raises(ValueError):
        parse_query("가" * 51)
    with pytest.raises(ValueError):
        parse_query("가 나 다 라 마 바")


def test_escape_like():
    assert escape_like("100%") == "100\\%"
    assert escape_like("a_b") == "a\\_b"
    assert escape_like("a\\b") == "a\\\\b"


def test_build_where_uses_bind_params_only():
    where, params = build_where("product_name", ["김치", "100%"])
    assert where.count(":t") == 2 and "김치" not in where
    assert params == {"t0": "%김치%", "t1": "%100\\%%"}
