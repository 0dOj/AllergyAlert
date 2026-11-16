"""제품 조회 + 알레르기 판정을 합친 결과를 만든다 (판정 엔드포인트와 이력 저장이 공유)."""
from sqlalchemy import text

from .matcher import Dictionary, judge

DISCLAIMER = "본 결과는 공공데이터 기반 참고용이며 실제 제품 포장의 알레르기 표시를 반드시 확인하세요."

_PRODUCT_SQL = text("""
    select p.report_no is not null as in_reports, p.raw_material,
           p.product_name as p_name, p.maker_name as p_maker, p.food_type as p_type,
           b.barcode, b.source, b.product_name as b_name, b.maker_name as b_maker,
           b.food_type as b_type, b.shelf_life_text,
           (b.end_dt is not null or b.clsbiz_dt is not null) as discontinued,
           b.report_no is not null as in_barcodes
    from (select cast(:r as text) as report_no, cast(:bc as text) as bc) x
    left join product_reports p on p.report_no = x.report_no
    left join lateral (
        select * from barcodes where report_no = x.report_no
        order by (barcode = x.bc) desc nulls last, case source when 'C005' then 0 else 1 end
        limit 1) b on true
""")


def fetch_product(conn, report_no: str, barcode: str | None = None) -> dict | None:
    r = conn.execute(_PRODUCT_SQL, {"r": report_no, "bc": barcode}).mappings().first()
    if r is None or not (r["in_reports"] or r["in_barcodes"]):
        return None
    return {
        "report_no": report_no,
        "barcode": r["barcode"],
        "source": r["source"],
        "product_name": r["b_name"] or r["p_name"],
        "maker_name": r["b_maker"] or r["p_maker"],
        "food_type": r["b_type"] or r["p_type"],
        "shelf_life_text": r["shelf_life_text"],
        "discontinued": r["discontinued"],      # barcodes 에 없는 제품은 None(알 수 없음)
        "raw_material": r["raw_material"],
    }


def build_result(conn, report_no: str, barcode: str | None, selected: list[str], d: Dictionary,
                 member: dict | None = None) -> dict | None:
    """member 는 {id, name} 을 가진 사전(구성원 판정일 때만). profile 에는 판정에 쓴 코드가 들어간다."""
    product = fetch_product(conn, report_no, barcode)
    if product is None:
        return None
    v = judge(product["raw_material"], selected, d)
    return {"product": product, **v.to_dict(), "profile": selected, "disclaimer": DISCLAIMER,
            "member": {"id": member["id"], "name": member["name"]} if member else None}
