"""판정과 이력에서 쓰는 구성원 조회. 소유자 확인과 코드 로드를 한 곳에서 한다."""
import uuid

from fastapi.responses import JSONResponse
from sqlalchemy import text

_MEMBER_SQL = text("select id, name, allergen_codes from member where id = :i and owner_id = :owner")

NO_ALLERGENS_BODY = {"detail": "구성원의 알레르겐을 먼저 설정하세요.", "action": "set_allergens"}


def get_member(conn, owner_id: str, member_id: uuid.UUID, known=None) -> dict | None:
    """owner_id 가 소유한 구성원의 {id, name, codes} 를 돌려준다. 없거나 남의 것이면 None.

    known(사전의 코드 모음)을 주면 중복과 사전에 없는 코드를 걸러 codes 에 판정에 쓸 코드만 남긴다.
    사전을 고친 뒤 서버가 재시작되면 이전에 저장한 코드가 사전에서 사라질 수 있기 때문이다."""
    row = conn.execute(_MEMBER_SQL, {"i": member_id, "owner": owner_id}).mappings().first()
    if row is None:
        return None
    codes = list(dict.fromkeys(row["allergen_codes"] or []))
    if known is not None:
        codes = [c for c in codes if c in known]
    return {"id": str(row["id"]), "name": row["name"], "codes": codes}


def get_member_codes(conn, owner_id: str, member_id: uuid.UUID, known=None) -> list[str] | None:
    """get_member 의 코드만 돌려준다. 구성원이 없거나 남의 것이면 None, 코드가 비면 빈 목록."""
    member = get_member(conn, owner_id, member_id, known)
    return None if member is None else member["codes"]


def member_problem(member: dict | None) -> JSONResponse | None:
    """판정에 쓸 수 없는 구성원이면 응답을 돌려준다: 없거나 남의 것 404, 코드가 비면 400 set_allergens."""
    if member is None:
        return JSONResponse(status_code=404, content={"detail": "구성원을 찾을 수 없습니다."})
    if not member["codes"]:
        return JSONResponse(status_code=400, content=NO_ALLERGENS_BODY)
    return None
