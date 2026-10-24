"""
3단계: 식약처 CSV(C005, I2570, C002) -> Supabase 적재용 CSV 변환

사용법 (CapstoneProject 폴더에서):
    pip install pandas
    python scripts/prepare_data.py   (어느 폴더에서 실행해도 됨)

입력: 같은 폴더의 C002.csv.gz, C005.csv.gz, I2570.csv.gz
출력: csv/barcodes.csv, csv/product_reports.csv, csv/report.txt
규칙: 3 데이터 모델.md  (빈 문자열 -> NULL, 바코드 정규화, 중복 제거)
"""
import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent  # CapstoneProject 폴더 (scripts의 상위)


def find_src():
    """gz 파일이 있는 폴더를 자동 탐색: CapstoneProject 또는 그 아래 csvgz"""
    for c in (ROOT, ROOT / "csvgz"):
        if (c / "C005.csv.gz").exists():
            return c
    return ROOT


ap = argparse.ArgumentParser()
ap.add_argument("--src", default=None, help="gz 파일이 있는 폴더 (기본: 자동 탐색)")
ap.add_argument("--out", default=None, help="출력 폴더 (기본: CapstoneProject/csv)")
args = ap.parse_args()
src = Path(args.src) if args.src else find_src()
out = Path(args.out) if args.out else ROOT / "csv"
out.mkdir(parents=True, exist_ok=True)
print(f"입력 폴더: {src}\n출력 폴더: {out}\n")
log = []


def say(msg):
    print(msg)
    log.append(msg)


def read(name):
    # dtype=str: 번호류가 숫자로 바뀌어 앞자리 0이 사라지는 것을 막는다
    return pd.read_csv(src / f"{name}.csv.gz", dtype=str, encoding="utf-8-sig",
                       keep_default_na=False)


def clean(s):
    """앞뒤 공백 제거. 빈 문자열은 NULL(None)"""
    s = s.str.strip()
    return s.where(s != "", None)


def norm_barcode(s):
    """숫자만 남기고, 12자리면 앞에 0 (UPC-A -> EAN-13)"""
    s = s.str.replace(r"\D", "", regex=True)
    return s.where(s.str.len() != 12, "0" + s)


def norm_date(s):
    """YYYYMMDD 8자리 숫자만 허용, 그 외는 NULL. '2015-01-22 11:12:12.0' 형태도 처리"""
    s = s.str.strip().str.replace(r"^(\d{4})-(\d{2})-(\d{2}).*$", r"\1\2\3", regex=True)
    ok = s.str.fullmatch(r"\d{8}") & (s != "00000000")
    return s.where(ok, None)


# ---------------- barcodes ----------------
cols = ["barcode", "report_no", "product_name", "maker_name", "food_type", "industry",
        "site_addr", "shelf_life_text", "report_dt", "end_dt", "clsbiz_dt", "source", "chng_dt"]

c5 = read("C005")
b1 = pd.DataFrame({
    "barcode": norm_barcode(c5["BAR_CD"]),
    "report_no": clean(c5["PRDLST_REPORT_NO"]),
    "product_name": clean(c5["PRDLST_NM"]),
    "maker_name": clean(c5["BSSH_NM"]),
    "food_type": clean(c5["PRDLST_DCNM"]),
    "industry": clean(c5["INDUTY_NM"]),
    "site_addr": clean(c5["SITE_ADDR"]),
    "shelf_life_text": clean(c5["POG_DAYCNT"]),
    "report_dt": norm_date(c5["PRMS_DT"]),
    "end_dt": norm_date(c5["END_DT"]),
    "clsbiz_dt": norm_date(c5["CLSBIZ_DT"]),
    "source": "C005",
    "chng_dt": None,  # C005에는 변경일자 컬럼이 없다
})

i2 = read("I2570")
b2 = pd.DataFrame({
    "barcode": norm_barcode(i2["BRCD_NO"]),
    "report_no": clean(i2["PRDLST_REPORT_NO"]),
    "product_name": clean(i2["PRDT_NM"]),
    "maker_name": clean(i2["CMPNY_NM"]),
    "food_type": clean(i2["PRDLST_NM"]),
    "industry": None, "site_addr": None, "shelf_life_text": None,
    "report_dt": None, "end_dt": None, "clsbiz_dt": None,
    "source": "I2570",
    "chng_dt": norm_date(i2["LAST_UPDT_DTM"]),
})

for name, raw, col in (("C005", c5, "BAR_CD"), ("I2570", i2, "BRCD_NO")):
    d = raw[col].str.replace(r"\D", "", regex=True)
    say(f"[{name}] 원본 {len(raw):,}행 / 12자리->13자리 변환 대상 {int((d.str.len() == 12).sum()):,}행")

bc = pd.concat([b1, b2], ignore_index=True)[cols]
n0 = len(bc)
bc = bc[bc["barcode"].notna() & (bc["barcode"] != "")]
say(f"바코드가 비어 제외: {n0 - len(bc):,}행")
n1 = len(bc)
bc = bc.drop_duplicates(["barcode", "report_no", "source"], keep="first")
say(f"(barcode, report_no, source) 중복 제거: {n1 - len(bc):,}행")
bc.to_csv(out / "barcodes.csv", index=False)
say(f"barcodes.csv: {len(bc):,}행 (C005 {int((bc.source=='C005').sum()):,} / I2570 {int((bc.source=='I2570').sum()):,})")
say("  바코드 길이 분포: " + str(bc.barcode.str.len().value_counts().head(6).to_dict()))

# ---------------- product_reports ----------------
c2 = read("C002")
pr = pd.DataFrame({
    "report_no": clean(c2["PRDLST_REPORT_NO"]),
    "product_name": clean(c2["PRDLST_NM"]),
    "maker_name": clean(c2["BSSH_NM"]),
    "food_type": clean(c2["PRDLST_DCNM"]),
    "lcns_no": clean(c2["LCNS_NO"]),
    "report_dt": norm_date(c2["PRMS_DT"]),
    "raw_material": clean(c2["RAWMTRL_NM"]),   # 원문 그대로 (공백 trim만)
    "etqty_yn": clean(c2["ETQTY_XPORT_PRDLST_YN"]),
    "chng_dt": norm_date(c2["CHNG_DT"]),
})
n0 = len(pr)
pr = pr[pr["report_no"].notna()].drop_duplicates("report_no", keep="last")
say(f"product_reports.csv: {len(pr):,}행 (원본 {n0:,}, 제외/중복 {n0-len(pr):,})")
say(f"  원재료 비어있음(NULL): {int(pr.raw_material.isna().sum()):,}행")
pr.to_csv(out / "product_reports.csv", index=False)

# ---------------- 조인율 ----------------
rep = set(pr["report_no"])
has = bc["report_no"].isin(rep)
say(f"barcodes 중 product_reports에 있는 비율: {has.mean():.1%} (없는 쪽도 정상)")
say(f"I2570 단독(바코드가 C005에 없는) 행: "
    f"{int((~bc[bc.source=='I2570'].barcode.isin(set(bc[bc.source=='C005'].barcode))).sum()):,}")

(out / "report.txt").write_text("\n".join(log), encoding="utf-8")
print(f"\n완료. {out} 폴더를 확인하세요.")
