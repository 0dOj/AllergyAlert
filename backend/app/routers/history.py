import json

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from ..barcode import normalize_barcode
from ..db import get_engine
from ..deps import get_dictionary
from ..services.check import build_result
from ..services.profile import get_profile_codes

router = APIRouter(prefix="/history", tags=["history"])


class HistoryIn(BaseModel):
    report_no: str
    barcode: str | None = None


@router.post("", status_code=201)
def create_history(body: HistoryIn):
    """판정을 서버에서 다시 계산해 스냅샷으로 저장한다 (클라이언트가 보낸 판정은 믿지 않는다)."""
    barcode = normalize_barcode(body.barcode) if body.barcode else None
    with get_engine().begin() as conn:
        selected = get_profile_codes(conn)
        if not selected:
            return JSONResponse(status_code=400, content={
                "detail": "알레르겐 프로필을 먼저 설정하세요.", "action": "set_profile"})
        result = build_result(conn, body.report_no, barcode, selected, get_dictionary())
        if result is None:
            return JSONResponse(status_code=404, content={"detail": "제품을 찾을 수 없습니다."})
        row = conn.execute(text(
            "insert into scan_history (barcode, report_no, product_name, verdict, matched) "
            "values (:bc, :rn, :nm, :v, cast(:snap as jsonb)) returning id, scanned_at"),
            {"bc": result["product"]["barcode"] or barcode, "rn": body.report_no,
             "nm": result["product"]["product_name"] or "", "v": result["verdict"],
             "snap": json.dumps(result, ensure_ascii=False)}).mappings().one()
    return {"id": row["id"], "scanned_at": row["scanned_at"], **result}


@router.get("")
def list_history():
    """최근순 최대 50건"""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            "select id, barcode, report_no, product_name, verdict, scanned_at "
            "from scan_history order by scanned_at desc, id desc limit 50")).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{history_id}")
def read_history(history_id: int):
    """저장된 판정 스냅샷을 그대로 돌려준다 (재계산하지 않는다)."""
    with get_engine().connect() as conn:
        row = conn.execute(text(
            "select id, scanned_at, matched from scan_history where id = :i"), {"i": history_id}).mappings().first()
    if row is None:
        return JSONResponse(status_code=404, content={"detail": "이력을 찾을 수 없습니다."})
    return {"id": row["id"], "scanned_at": row["scanned_at"], **row["matched"]}


@router.delete("/{history_id}", status_code=204)
def delete_history(history_id: int):
    with get_engine().begin() as conn:
        n = conn.execute(text("delete from scan_history where id = :i"), {"i": history_id}).rowcount
    if not n:
        return JSONResponse(status_code=404, content={"detail": "이력을 찾을 수 없습니다."})
    return Response(status_code=204)
