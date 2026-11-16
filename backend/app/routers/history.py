import json
import uuid

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import text

from ..auth import CurrentUser, current_user
from ..barcode import normalize_barcode
from ..db import get_engine
from ..deps import get_dictionary
from ..services.check import build_result
from ..services.members import NO_ALLERGENS_BODY, get_member, member_problem
from ..services.profile import get_profile_codes

router = APIRouter(prefix="/history", tags=["history"])


class HistoryIn(BaseModel):
    report_no: str = Field(max_length=30)
    barcode: str | None = Field(default=None, max_length=20)
    member_id: uuid.UUID | None = None


@router.post("", status_code=201)
def create_history(body: HistoryIn, user: CurrentUser = Depends(current_user)):
    """판정을 서버에서 다시 계산해 스냅샷으로 저장한다 (클라이언트가 보낸 판정은 믿지 않는다).
    member_id 가 있으면 내 구성원의 코드로 판정하고 scan_history.member_id 에 저장한다
    (남의 구성원이거나 없으면 404, 코드가 비어 있으면 400 set_allergens). 없으면 공유 프로필, member_id 는 NULL."""
    barcode = normalize_barcode(body.barcode) if body.barcode else None
    with get_engine().begin() as conn:
        member = None
        if body.member_id is None:
            selected = get_profile_codes(conn)
            if not selected:
                return JSONResponse(status_code=400, content={
                    "detail": "알레르겐 프로필을 먼저 설정하세요.", "action": "set_profile"})
        else:
            member = get_member(conn, user.id, body.member_id, get_dictionary().names)
            problem = member_problem(member)
            if problem is not None:
                return problem
            selected = member["codes"]
        try:
            result = build_result(conn, body.report_no, barcode, selected, get_dictionary(), member)
        except ValueError:
            if member is None:
                raise
            return JSONResponse(status_code=400, content=NO_ALLERGENS_BODY)
        if result is None:
            return JSONResponse(status_code=404, content={"detail": "제품을 찾을 수 없습니다."})
        row = conn.execute(text(
            "insert into scan_history "
            "(owner_id, member_id, barcode, report_no, product_name, verdict, matched) "
            "values (:owner, cast(:mid as uuid), :bc, :rn, :nm, :v, cast(:snap as jsonb)) "
            "returning id, scanned_at"),
            {"owner": user.id, "mid": member["id"] if member else None,
             "bc": result["product"]["barcode"] or barcode, "rn": body.report_no,
             "nm": result["product"]["product_name"] or "", "v": result["verdict"],
             "snap": json.dumps(result, ensure_ascii=False)}).mappings().one()
    return {"id": row["id"], "scanned_at": row["scanned_at"], **result}


@router.get("")
def list_history(member_id: uuid.UUID | None = None, user: CurrentUser = Depends(current_user)):
    """내 이력만 최근순 최대 50건. 각 항목에 구성원(member_id, member_name)이 붙고 삭제된 구성원이면 null.
    member_id 를 주면 그 구성원의 이력만 (남의 id 는 owner_id 조건 때문에 빈 목록)."""
    sql = ("select h.id, h.barcode, h.report_no, h.product_name, h.verdict, h.scanned_at, "
           "h.member_id, m.name as member_name "
           "from scan_history h left join member m on m.id = h.member_id and m.owner_id = h.owner_id "
           "where h.owner_id = :owner")
    params = {"owner": user.id}
    if member_id is not None:
        sql += " and h.member_id = :mid"
        params["mid"] = member_id
    with get_engine().connect() as conn:
        rows = conn.execute(text(sql + " order by h.scanned_at desc, h.id desc limit 50"),
                            params).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{history_id}")
def read_history(history_id: int, user: CurrentUser = Depends(current_user)):
    """저장된 판정 스냅샷을 그대로 돌려준다 (재계산하지 않는다). 남의 이력은 없는 것처럼 404."""
    with get_engine().connect() as conn:
        row = conn.execute(text(
            "select id, scanned_at, matched from scan_history where id = :i and owner_id = :owner"),
            {"i": history_id, "owner": user.id}).mappings().first()
    if row is None:
        return JSONResponse(status_code=404, content={"detail": "이력을 찾을 수 없습니다."})
    return {"id": row["id"], "scanned_at": row["scanned_at"], **row["matched"]}


@router.delete("/{history_id}", status_code=204)
def delete_history(history_id: int, user: CurrentUser = Depends(current_user)):
    with get_engine().begin() as conn:
        n = conn.execute(text(
            "delete from scan_history where id = :i and owner_id = :owner"),
            {"i": history_id, "owner": user.id}).rowcount
    if not n:
        return JSONResponse(status_code=404, content={"detail": "이력을 찾을 수 없습니다."})
    return Response(status_code=204)
