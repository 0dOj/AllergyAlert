"""
4단계: 가공된 CSV를 Supabase(Postgres)에 대량 적재

사전 준비
    pip install "psycopg[binary]"
    (3단계 완료: CapstoneProject\\csv 에 barcodes.csv, product_reports.csv 존재)
    (2단계 완료: 01_schema.sql 실행됨)

실행 (어느 폴더에서든)
    python scripts/load_data.py

실행하면 접속 주소와 비밀번호를 물어본다. 비밀번호는 화면에 안 보이고 파일에도 저장되지 않는다.
옵션
    --indexes   적재 후 sql/02_indexes.sql 도 실행
    --only product_reports | barcodes    한 테이블만 적재
    --yes       확인 질문 생략
"""
import argparse
import getpass
import os
import sys
import time
from pathlib import Path
from urllib.parse import quote

import psycopg

ROOT = Path(__file__).resolve().parent.parent
CSV = ROOT / "csv"

TABLES = {
    "product_reports": ("report_no, product_name, maker_name, food_type, lcns_no, "
                        "report_dt, raw_material, etqty_yn, chng_dt"),
    "barcodes": ("barcode, report_no, product_name, maker_name, food_type, industry, "
                 "site_addr, shelf_life_text, report_dt, end_dt, clsbiz_dt, source, chng_dt"),
}

ap = argparse.ArgumentParser()
ap.add_argument("--indexes", action="store_true")
ap.add_argument("--only", choices=list(TABLES))
ap.add_argument("--yes", action="store_true")
args = ap.parse_args()


def get_conninfo():
    uri = os.environ.get("DATABASE_URL")
    if not uri:
        print("Supabase 대시보드 > 위쪽 Connect > 'Session pooler' 의 URI를 그대로 붙여넣으세요.")
        print("(postgresql://postgres.xxxx:[YOUR-PASSWORD]@aws-...pooler.supabase.com:5432/postgres)")
        uri = input("URI: ").strip()
    if "[YOUR-PASSWORD]" in uri:
        pw = getpass.getpass("DB 비밀번호(입력해도 안 보임): ")
        uri = uri.replace("[YOUR-PASSWORD]", quote(pw, safe=""))
    return uri


def size(cur):
    cur.execute("select pg_size_pretty(pg_database_size(current_database())), "
                "pg_database_size(current_database())")
    return cur.fetchone()


def copy_file(conn, table, cols):
    path = CSV / f"{table}.csv"
    if not path.exists():
        sys.exit(f"파일이 없습니다: {path}  (3단계를 먼저 실행하세요)")
    total = path.stat().st_size
    sent = 0
    t0 = time.time()
    with conn.cursor() as cur:
        cur.execute("set statement_timeout = 0")
        cur.execute(f"truncate public.{table} restart identity")
        sql = f"copy public.{table} ({cols}) from stdin with (format csv, header true)"
        with cur.copy(sql) as cp, open(path, "rb") as f:
            while chunk := f.read(1 << 20):
                cp.write(chunk)
                sent += len(chunk)
                print(f"\r  {table}: {sent / total:6.1%} 전송 ({time.time() - t0:5.0f}초)", end="", flush=True)
        print()
        cur.execute(f"select count(*) from public.{table}")
        n = cur.fetchone()[0]
    return n


def main():
    conninfo = get_conninfo()
    with psycopg.connect(conninfo, autocommit=False, connect_timeout=15) as conn:
        with conn.cursor() as cur:
            cur.execute("select current_user, inet_server_addr()")
            print("접속 성공:", cur.fetchone())
            for t in TABLES:
                cur.execute("select to_regclass(%s)", (f"public.{t}",))
                if cur.fetchone()[0] is None:
                    sys.exit(f"테이블 {t} 가 없습니다. 2단계(01_schema.sql)를 먼저 실행하세요.")
            print("현재 DB 크기:", size(cur)[0])
        conn.rollback()

        targets = [args.only] if args.only else list(TABLES)
        if not args.yes:
            print(f"\n다음 테이블의 기존 데이터를 지우고 다시 적재합니다: {', '.join(targets)}")
            if input("계속할까요? (y/N): ").strip().lower() != "y":
                sys.exit("취소했습니다.")

        counts = {}
        for t in targets:
            started = time.time()
            try:
                counts[t] = copy_file(conn, t, TABLES[t])
                conn.commit()
            except Exception as e:
                conn.rollback()
                with conn.cursor() as cur:
                    cur.execute("insert into public.ingest_log (service_id, finished_at, status, message) "
                                "values (%s, now(), 'failed', %s)",
                                ("C002" if t == "product_reports" else "C005", str(e)[:500]))
                conn.commit()
                print(f"\n실패: {e}")
                sys.exit(1)
            print(f"  {t}: {counts[t]:,}행 적재 완료 ({time.time() - started:.0f}초)")
            with conn.cursor() as cur:
                cur.execute("select pg_size_pretty(pg_database_size(current_database())), "
                            "pg_database_size(current_database())")
                pretty, raw = cur.fetchone()
                print("  현재 DB 크기:", pretty)
                if raw > 450 * 1024 * 1024:
                    print("  ⚠ 무료 플랜 한도(500MB)에 가깝습니다. 인덱스를 더 만들면 초과할 수 있습니다.")
                # 적재 이력 기록 (서비스별 행 수)
                if t == "product_reports":
                    logs = [("C002", counts[t])]
                else:
                    cur.execute("select source, count(*) from public.barcodes group by source")
                    logs = cur.fetchall()
                for sid, n in logs:
                    cur.execute("insert into public.ingest_log (service_id, finished_at, rows, status, message) "
                                "values (%s, now(), %s, 'success', %s)", (sid, n, f"전체 덤프 일괄 적재({t})"))
            conn.commit()

        if args.indexes:
            sqlfile = ROOT / "sql" / "02_indexes.sql"
            print("\n인덱스 생성 중... (몇 분 걸릴 수 있음)")
            with conn.cursor() as cur:
                cur.execute("set statement_timeout = 0")
                t0 = time.time()
                cur.execute(sqlfile.read_text(encoding="utf-8"))
            conn.commit()
            print(f"  완료 ({time.time() - t0:.0f}초)")
            with conn.cursor() as cur:
                print("  최종 DB 크기:", size(cur)[0])

        print("\n=== 검증 ===")
        with conn.cursor() as cur:
            for t in TABLES:
                cur.execute(f"select count(*) from public.{t}")
                print(f"  {t}: {cur.fetchone()[0]:,}행")
        print("완료.")


main()
