import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import text

from ..auth import CurrentUser, current_user
from ..db import get_engine
from ..deps import get_dictionary

router = APIRouter(prefix="/members", tags=["members"])

MAX_MEMBERS = 10

_COLUMNS = "id, name, relation, allergen_codes, notes, avatar_color, created_at"


class MemberIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=30)
    relation: str | None = Field(default=None, max_length=20)
    allergen_codes: list[str] = Field(max_length=30)
    notes: str | None = Field(default=None, max_length=200)
    avatar_color: str | None = Field(default=None, max_length=40)

    @field_validator("relation", "notes", "avatar_color")
    @classmethod
    def blank_is_none(cls, v: str | None) -> str | None:
        """공백만 보낸 관계, 메모, 아바타 색은 값이 없는 것으로 본다."""
        return v or None


class MemberOut(BaseModel):
    id: uuid.UUID
    name: str
    relation: str | None
    allergen_codes: list[str]
    notes: str | None = None
    avatar_color: str | None = None
    created_at: datetime | None


def _clean_codes(codes: list[str]) -> list[str]:
    """중복 제거(입력 순서 유지) 후 사전에 없는 코드가 있으면 422."""
    known = get_dictionary().names
    unique = list(dict.fromkeys(codes))
    unknown = [c for c in unique if c not in known]
    if unknown:
        raise HTTPException(status_code=422, detail=f"알 수 없는 알레르겐 코드: {unknown}")
    return unique


def _not_found() -> JSONResponse:
    return JSONResponse(status_code=404, content={"detail": "구성원을 찾을 수 없습니다."})


@router.get("", response_model=list[MemberOut])
def list_members(user: CurrentUser = Depends(current_user)):
    """내 구성원만 만든 순서대로"""
    with get_engine().connect() as conn:
        rows = conn.execute(text(
            f"select {_COLUMNS} from member where owner_id = :owner "
            "order by created_at asc, id asc"), {"owner": user.id}).mappings().all()
    return [dict(r) for r in rows]


@router.post("", status_code=201, response_model=MemberOut)
def create_member(body: MemberIn, user: CurrentUser = Depends(current_user)):
    """구성원 생성. 사용자당 최대 10명이며, 같은 사용자의 동시 요청은 advisory lock 으로 순서를 맞춘다."""
    codes = _clean_codes(body.allergen_codes)
    with get_engine().begin() as conn:
        # auth.users 행은 app_backend 가 잠글 수 없고, member 행 잠금은 아직 없는 행을 막지 못한다.
        # 트랜잭션이 끝나면 락도 풀린다.
        conn.execute(text("select pg_advisory_xact_lock(hashtextextended(cast(:owner as text), 0))"),
                     {"owner": user.id})
        row = conn.execute(text(
            "insert into member (owner_id, name, relation, allergen_codes, notes, avatar_color) "
            "select cast(:owner as uuid), cast(:name as text), cast(:rel as text), cast(:codes as text[]), "
            "cast(:notes as text), cast(:color as text) "
            "where (select count(*) from member where owner_id = cast(:owner as uuid)) < :max "
            f"returning {_COLUMNS}"),
            {"owner": user.id, "name": body.name, "rel": body.relation,
             "codes": codes, "notes": body.notes, "color": body.avatar_color,
             "max": MAX_MEMBERS}).mappings().first()
    if row is None:
        return JSONResponse(status_code=409, content={
            "detail": f"구성원은 최대 {MAX_MEMBERS}명까지 만들 수 있습니다."})
    return dict(row)


@router.put("/{member_id}", response_model=MemberOut)
def replace_member(member_id: uuid.UUID, body: MemberIn, user: CurrentUser = Depends(current_user)):
    """이름, 관계, 알레르겐 코드, 메모, 아바타 색을 통째로 교체한다(빠진 선택 필드는 null). 남의 구성원은 없는 것처럼 404."""
    codes = _clean_codes(body.allergen_codes)
    with get_engine().begin() as conn:
        row = conn.execute(text(
            "update member set name = :name, relation = :rel, allergen_codes = cast(:codes as text[]), "
            "notes = :notes, avatar_color = :color "
            f"where id = :i and owner_id = :owner returning {_COLUMNS}"),
            {"name": body.name, "rel": body.relation, "codes": codes,
             "notes": body.notes, "color": body.avatar_color,
             "i": member_id, "owner": user.id}).mappings().first()
    if row is None:
        return _not_found()
    return dict(row)


@router.delete("/{member_id}", status_code=204)
def delete_member(member_id: uuid.UUID, user: CurrentUser = Depends(current_user)):
    with get_engine().begin() as conn:
        n = conn.execute(text(
            "delete from member where id = :i and owner_id = :owner"),
            {"i": member_id, "owner": user.id}).rowcount
    if not n:
        return _not_found()
    return Response(status_code=204)
