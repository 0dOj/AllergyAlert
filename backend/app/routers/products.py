import os
import uuid
from typing import Literal

import psycopg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from ..auth import CurrentUser, user_if_member
from ..barcode import MAX_LEN, MIN_LEN, is_valid_length, normalize_barcode
from ..db import get_engine
from ..deps import get_dictionary
from ..services.check import build_result
from ..services.members import NO_ALLERGENS_BODY, get_member, member_problem
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
def judge_product(report_no: str, barcode: str | None = None, member_id: uuid.UUID | None = None,
                  user: CurrentUser | None = Depends(user_if_member)):
    """F-05/06/07: 알레르기 판정. 기본은 저장된 공유 프로필 기준이며 비어 있으면 400.
    barcode 는 선택: 같은 품목보고번호에 바코드가 여러 개일 때 보여줄 바코드를 고른다.
    member_id 는 선택: 주면 토큰이 필요하고 내 구성원의 알레르겐으로 판정한다.
    남의 구성원이거나 없으면 404, 구성원의 코드가 비어 있으면 400 + {"action": "set_allergens"}."""
    bc = normalize_barcode(barcode) if barcode else None
    with get_engine().connect() as conn:
        member = None
        if member_id is None:
            selected = get_profile_codes(conn)
            if not selected:
                return JSONResponse(status_code=400, content={
                    "detail": "알레르겐 프로필을 먼저 설정하세요.", "action": "set_profile"})
        else:
            member = get_member(conn, user.id, member_id, get_dictionary().names)
            problem = member_problem(member)
            if problem is not None:
                return problem
            selected = member["codes"]
        try:
            result = build_result(conn, report_no, bc, selected, get_dictionary(), member)
        except ValueError:
            if member is None:
                raise
            return JSONResponse(status_code=400, content=NO_ALLERGENS_BODY)
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
