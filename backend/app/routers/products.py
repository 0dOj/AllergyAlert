import os
from typing import Literal

import psycopg
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ..barcode import MAX_LEN, MIN_LEN, is_valid_length, normalize_barcode
from ..db import get_engine
from ..deps import get_dictionary
from ..services.check import build_result
from ..services.profile import get_profile_codes
from ..services.search import LIMIT, build_where, parse_query

router = APIRouter(prefix="/products", tags=["products"])

# F-03: C005 -> I2570 순서. 같은 바코드에 품목보고번호가 여러 개일 수 있어 limit 1
LOOKUP_SQL = text("""
    select b.barcode, b.source, b.report_no, b.product_name, b.maker_name, b.food_type,
           b.industry, b.shelf_life_text,
           (b.end_dt is not null or b.clsbiz_dt is not null) as discontinued,
           (p.raw_material is not null) as has_raw_material
    from barcodes b
    left join product_reports p on p.report_no = b.report_no
    where b.barcode = :barcode
    order by case b.source when 'C005' then 0 else 1 end
    limit 1
""")


@router.get("/barcode/{barcode}")
def lookup_by_barcode(barcode: str):
    normalized = normalize_barcode(barcode)
    if not is_valid_length(normalized):
        raise HTTPException(status_code=422,
                            detail=f"바코드는 숫자 {MIN_LEN}~{MAX_LEN}자리여야 합니다.")
    with get_engine().connect() as conn:
        row = conn.execute(LOOKUP_SQL, {"barcode": normalized}).mappings().first()
    if row is None:
        # 미조회는 에러가 아니라 정상 분기: 프론트가 제품명 검색으로 넘어간다
        return JSONResponse(status_code=404,
                            content={"barcode": normalized, "fallback": "search_by_name"})
    return dict(row)


@router.get("/{report_no}/judge")
def judge_product(report_no: str, barcode: str | None = None):
    """F-05/06/07: 저장된 프로필 기준 알레르기 판정. 프로필이 비어 있으면 400.
    barcode 는 선택: 같은 품목보고번호에 바코드가 여러 개일 때 보여줄 바코드를 고른다."""
    bc = normalize_barcode(barcode) if barcode else None
    with get_engine().connect() as conn:
        selected = get_profile_codes(conn)
        if not selected:
            return JSONResponse(status_code=400, content={
                "detail": "알레르겐 프로필을 먼저 설정하세요.", "action": "set_profile"})
        result = build_result(conn, report_no, bc, selected, get_dictionary())
    if result is None:
        return JSONResponse(status_code=404, content={"detail": "제품을 찾을 수 없습니다."})
    return result


@router.get("/search")
def search_products(q: str, scope: Literal["reports", "barcodes"] = "reports",
                    sort: Literal["fast", "relevance"] = "fast"):
    """F-04 제품명 검색. 2글자 이상, 부분 일치, 최대 20건, 결과 0건도 200 + 빈 배열.

    scope=reports  : 원재료가 있는 품목(product_reports) 대상 (기본)
    scope=barcodes : 바코드가 있는 제품(barcodes) 대상. 원재료 없는 포장육·수입식품도 찾는다.
    sort=fast      : 정렬 없이 처음 20건 (빠름, 순서는 임의)
    sort=relevance : 이름이 짧은 순 -> 가나다순 (전체를 훑어서 느림)
    여러 단어는 공백으로 구분하며 모두 포함된 제품을 찾는다."""
    try:
        tokens = parse_query(q)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if scope == "reports":
        where, params = build_where("product_name", tokens)
        select = "select report_no, product_name, maker_name, food_type from product_reports"
    else:
        where, params = build_where("b.product_name", tokens)
        select = ("select b.report_no, b.barcode, b.product_name, b.maker_name, b.food_type, "
                  "(b.end_dt is not null or b.clsbiz_dt is not null) as discontinued from barcodes b")
    col = "product_name" if scope == "reports" else "b.product_name"
    order = f" order by length({col}), {col}" if sort == "relevance" else ""
    sql = text(f"{select} where {where}{order} limit {LIMIT}")

    timeout_ms = int(os.environ.get("SEARCH_TIMEOUT_MS", "3000"))
    try:
        with get_engine().begin() as conn:
            conn.execute(text(f"set local statement_timeout = {timeout_ms}"))   # 이 검색에만 적용
            rows = conn.execute(sql, params).mappings().all()
    except DBAPIError as e:
        if isinstance(e.orig, psycopg.errors.QueryCanceled):
            return JSONResponse(status_code=503, content={
                "detail": "검색이 오래 걸려 중단했습니다. 검색어를 더 구체적으로 입력해 보세요."})
        raise
    return [dict(r) for r in rows]
