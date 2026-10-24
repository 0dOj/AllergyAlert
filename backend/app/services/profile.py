import json

from sqlalchemy import text


def get_profile_codes(conn) -> list[str]:
    """단일 사용자: user_profile 의 첫 행. 없으면 빈 목록.
    allergen_ids 컬럼에는 알레르겐 '코드'(MILK 등)를 저장한다 (id 는 시드 재적재 시 바뀔 수 있어서)."""
    row = conn.execute(text("select allergen_ids from user_profile order by id limit 1")).first()
    return list(row[0]) if row and row[0] else []


def save_profile_codes(conn, codes: list[str]) -> None:
    payload = json.dumps(codes, ensure_ascii=False)
    updated = conn.execute(text(
        "update user_profile set allergen_ids = cast(:p as jsonb) "
        "where id = (select min(id) from user_profile)"), {"p": payload}).rowcount
    if not updated:
        conn.execute(text("insert into user_profile (allergen_ids) values (cast(:p as jsonb))"), {"p": payload})
