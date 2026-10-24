"""
6-3 점검: app_backend / app_ingest 계정으로 접속해 권한이 의도대로인지 확인한다.

    python scripts/check_roles.py

접속 주소와 비밀번호를 물어본다(비밀번호는 화면에 안 보이고 저장되지 않는다).
확인할 계정마다 한 번씩 실행한다.
"""
import getpass
import os
from urllib.parse import quote

import psycopg

uri = os.environ.get("DATABASE_URL") or input(
    "접속 문자열(예: postgresql://app_backend.프로젝트ref:[YOUR-PASSWORD]@aws-...pooler.supabase.com:5432/postgres): ").strip()
if "[YOUR-PASSWORD]" in uri:
    uri = uri.replace("[YOUR-PASSWORD]", quote(getpass.getpass("해당 계정 비밀번호: "), safe=""))

# 기대 결과: (설명, SQL, 성공해야 하는가)
COMMON = [("참조 데이터 읽기 (barcodes)", "select count(*) from public.barcodes", True),
          ("참조 데이터 읽기 (allergens)", "select count(*) from public.allergens", True)]
CASES = {
    "app_backend": COMMON + [
        ("이력 쓰기 (scan_history INSERT)",
         "insert into public.scan_history (product_name, verdict) values ('점검','safe')", True),
        ("프로필 읽기 (user_profile)", "select count(*) from public.user_profile", True),
        ("적재 이력 읽기 (ingest_log)", "select count(*) from public.ingest_log", True),
        ("[차단돼야 함] barcodes INSERT",
         "insert into public.barcodes (barcode, source) values ('0','C005')", False),
        ("[차단돼야 함] product_reports DELETE", "delete from public.product_reports", False),
        ("[차단돼야 함] 테이블 삭제", "drop table public.barcodes", False),
    ],
    "app_ingest": COMMON + [
        ("적재 쓰기 (barcodes INSERT)",
         "insert into public.barcodes (barcode, source) values ('0','C005')", True),
        ("적재 이력 쓰기 (ingest_log INSERT)",
         "insert into public.ingest_log (service_id, status) values ('C005','running')", True),
        ("[차단돼야 함] scan_history 읽기", "select count(*) from public.scan_history", False),
        ("[차단돼야 함] user_profile 읽기", "select count(*) from public.user_profile", False),
        ("[차단돼야 함] 테이블 삭제", "drop table public.barcodes", False),
    ],
}

try:
    conn = psycopg.connect(uri, connect_timeout=15)
except Exception as e:
    print("\n접속 실패:", str(e).strip().splitlines()[0])
    print("확인: 사용자명이 '계정.프로젝트ref' 형식인지 / Session pooler 주소(포트 5432)인지 / 비밀번호 설정(alter role)을 했는지")
    raise SystemExit(1)

with conn:
    role = conn.execute("select current_user").fetchone()[0]
    print(f"\n접속 성공. 현재 계정: {role}\n")
    cases = CASES.get(role)
    if cases is None:
        print("app_backend 또는 app_ingest 계정이 아닙니다. 팀에 공유할 계정으로 접속하세요.")
        raise SystemExit(1)
    bad = 0
    for desc, sql, should_pass in cases:
        try:
            conn.execute(sql)
            ok = True
        except Exception:
            ok = False
        finally:
            conn.rollback()   # 점검 때문에 데이터가 바뀌지 않도록 항상 되돌린다
        good = (ok == should_pass)
        bad += not good
        print(f"  [{'OK  ' if good else 'FAIL'}] {desc}  ->  {'성공' if ok else '거부됨'}")
    print("\n결과:", "모두 정상" if bad == 0 else f"{bad}건 이상 있음 (위 FAIL 확인)")
