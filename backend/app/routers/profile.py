from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..db import get_engine
from ..deps import get_dictionary
from ..services.profile import get_profile_codes, save_profile_codes

router = APIRouter(tags=["profile"])


class ProfileIn(BaseModel):
    allergens: list[str]


@router.get("/allergens")
def list_allergens():
    """프로필 화면용 알레르겐 목록 (법정 항목 22개: 조개류 + 굴·전복·홍합)"""
    from sqlalchemy import text
    with get_engine().connect() as conn:
        rows = conn.execute(text("select code, name_ko, is_statutory from allergens order by id")).mappings().all()
    return [dict(r) for r in rows]


@router.get("/profile")
def read_profile():
    codes = get_profile_codes_safe()
    names = get_dictionary().names
    return {"allergens": codes, "items": [{"code": c, "name_ko": names.get(c, c)} for c in codes]}


def get_profile_codes_safe() -> list[str]:
    with get_engine().connect() as conn:
        return get_profile_codes(conn)


@router.put("/profile")
def update_profile(body: ProfileIn):
    known = get_dictionary().names
    codes = list(dict.fromkeys(body.allergens))
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"알 수 없는 알레르겐 코드: {unknown}")
    with get_engine().begin() as conn:
        save_profile_codes(conn, codes)
    return {"allergens": codes, "items": [{"code": c, "name_ko": known[c]} for c in codes]}
