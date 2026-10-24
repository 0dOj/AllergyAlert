"""
시드 생성: seed.json + sql/03_seed.sql

사용법 (CapstoneProject 폴더에서):
    python scripts/build_seed.py
(prepare_data.py 실행 후라면 csv/ 의 실데이터에서 개발용 샘플도 함께 뽑는다)

※ 동의어·제외어는 '초안'이다. 107만 행 원재료에서 표기 빈도를 확인해 PM과 보완할 것.
※ 제외어는 반드시 알레르겐별로 둔다. 메밀은 WHEAT의 제외어이고 BUCKWHEAT의 동의어다.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent  # CapstoneProject 폴더

# code, 한글명, 법정여부, [동의어], [제외어]
A = [
 ("EGG", "알류(가금류)", True,
  "계란 달걀 난백 난황 전란 난각 알류 계란분말 난분말 건조란 액란 난백분말 난황분말 전란분말 오리알 메추리알 마요네즈",
  ""),
 ("MILK", "우유", True,
  "우유 유청 유청분말 유청단백 유청단백분말 탈지분유 전지분유 분유 혼합분유 조제분유 혼합탈지분유 유당 락토오스 버터 카제인 카제인나트륨 유크림 생크림 크림치즈 연유 우유단백 우유분말 농축우유 탈지우유 유단백 유지방 락토페린 요구르트 요거트 발효유 가공유 탈지농축유 치즈 밀크 밀크파우더 가공유크림 밀크칼슘",
  "코코넛밀크 아몬드밀크 귀리밀크 오트밀크 쌀밀크 코코아버터 카카오버터 시어버터 코코넛버터 땅콩버터 아몬드버터"),
 ("BUCKWHEAT", "메밀", True,
  "메밀 메밀가루 메밀분말 메밀면 메밀전분 메밀껍질 메밀차 쓴메밀 타타리메밀", ""),
 ("PEANUT", "땅콩", True,
  "땅콩 땅콩버터 땅콩분말 땅콩가루 땅콩기름 땅콩유 땅콩분태 낙화생",
  "땅콩호박"),
 ("SOYBEAN", "대두", True,
  "대두 콩 대두유 대두단백 분리대두단백 농축대두단백 대두레시틴 된장 간장 양조간장 진간장 국간장 두부 청국장 고추장 메주 두유 콩가루 콩기름 대두분말 탈지대두 대두박 콩단백 쌈장 춘장 템페 낫토 두반장 대두이소플라본 비지 검은콩 서리태 쥐눈이콩 콩나물",
  "땅콩 완두콩 강낭콩 병아리콩 렌틸콩 작두콩 커피콩 코코아콩 카카오콩"),
 ("WHEAT", "밀", True,
  "밀 밀가루 소맥 소맥분 소맥분말 소맥전분 밀전분 글루텐 밀글루텐 강력분 중력분 박력분 통밀 밀단백 밀배아 밀기울 듀럼밀 세몰리나 카무트",
  "메밀 호밀 밀크 밀랍 밀감 아밀라아제 아밀로오스 아밀로펙틴 아밀"),
 ("MACKEREL", "고등어", True,
  "고등어 고등어살 고등어추출물 고등어분말 고등어엑기스", ""),
 ("CRAB", "게", True,
  "게 꽃게 대게 홍게 킹크랩 게살 게맛살 게추출물 게분말 게엑기스",
  "게르마늄 게르마 지게미 당게"),
 ("SHRIMP", "새우", True,
  "새우 대하 보리새우 꽃새우 건새우 새우살 새우분말 새우추출물 새우엑기스 새우젓 칵테일새우 흰다리새우", ""),
 ("PORK", "돼지고기", True,
  "돼지고기 돼지 돈육 돈지 돈피 돈골 돼지껍질 돼지껍데기 돼지기름 돈지방 라드 포크 베이컨 족발 돼지사골 돈사골",
  "돼지감자"),
 ("PEACH", "복숭아", True,
  "복숭아 복숭아농축액 복숭아퓨레 복숭아과즙 복숭아과육 복숭아분말 황도 백도 천도복숭아", ""),
 ("TOMATO", "토마토", True,
  "토마토 토마토페이스트 토마토퓨레 토마토케첩 케첩 토마토분말 토마토농축액 방울토마토 건조토마토 토마토과즙 토마토엑기스", ""),
 ("SULFITES", "아황산류", True,
  "아황산 이산화황 무수아황산 메타중아황산 피로아황산 차아황산 중아황산 아황산염", ""),
 ("WALNUT", "호두", True,
  "호두 호두분태 호두분말 호두유 호두기름 호두가루 호두과자 미국호두", ""),
 ("CHICKEN", "닭고기", True,
  "닭고기 계육 닭 치킨 닭가슴살 닭다리살 닭껍질 닭뼈 닭발 육계 닭고기분말 계육분말 닭추출물 닭엑기스 닭뼈추출물 치킨엑기스 치킨파우더 치킨분말 계골",
  "닭의장풀"),
 ("BEEF", "쇠고기", True,
  "쇠고기 소고기 우육 비프 우지 쇠기름 소기름 한우 육우 우골 우족 소뼈 쇠뼈 쇠사골 소사골 우사골 쇠고기분말 소고기분말 쇠고기추출물 소고기엑기스 비프엑기스 비프분말 쇠고기엑기스",
  ""),
 ("SQUID", "오징어", True,
  "오징어 오징어살 오징어먹물 오징어분말 오징어추출물 오징어엑기스 오징어채 오징어다리 갑오징어 한치 마른오징어", ""),
 ("SHELLFISH", "조개류", True,
  "조개 조개류 바지락 가리비 꼬막 백합 재첩 모시조개 대합 키조개 맛조개 피조개 개량조개 조개살 조개추출물 바지락분말 바지락엑기스 조개엑기스 조개육수",
  "백합뿌리"),
 ("OYSTER", "굴", True,
  "굴 굴소스 굴추출물 굴엑기스 굴분말 굴농축액 굴농축엑기스 석화 참굴 굴젓 굴즙",
  "굴비 토굴 동굴 석굴 굴곡 굴뚝"),
 ("ABALONE", "전복", True,
  "전복 전복내장 전복추출물 전복엑기스 전복분말", ""),
 ("MUSSEL", "홍합", True,
  "홍합 홍합추출물 홍합분말 홍합엑기스 담치 진주담치 지중해담치", ""),
 ("PINENUT", "잣", True,
  "잣 잣가루 잣분말 잣기름 잣죽",
  "잣나무"),
]

# pattern, rule_type, note   ($로 시작 = 접미사)
T = [
 ("$가공품", "compound", "서류가공품·곡류가공품 등. 실측 6,214회(모델 문서)"),
 ("복합조미식품", "compound", "실측 3,196회"),
 ("복합조미료", "compound", "하위 성분 미표기"),
 ("혼합제제", "compound", "제제 계열. 실측 2,790회"),
 ("식품첨가물혼합제제", "compound", "하위 성분 미표기"),
 ("$제제", "compound", "접미사 제제"),
 ("$소스", "compound", "실측 2,680회"),
 ("혼합분유", "compound", "복합원재료이면서 우유. 알레르겐 매칭도 함께 적용(danger 우선). 실측 96회"),
 ("$시즈닝", "compound", "○○시즈닝"),
 ("혼합조미료", "compound", "하위 성분 미표기"),
 ("조미식품", "compound", "하위 성분 미표기"),
 ("$양념", "compound", "양념류"),
 ("혼합양념", "compound", "하위 성분 미표기"),
 ("혼합분말", "compound", "하위 성분 미표기"),
 ("$베이스", "compound", "혼합조미베이스 등"),
 ("$드레싱", "compound", "하위 성분 미표기"),
 ("$조미액", "compound", "하위 성분 미표기"),
 ("$향", "flavor", "향료. 해당 식품 단백질이 없을 수 있어 danger를 caution으로 낮춤"),
 ("$향료", "flavor", "합성향료·천연향료"),
 ("합성향료", "flavor", "향료"),
 ("천연향료", "flavor", "향료"),
 ("$플레이버", "flavor", "향료"),
 ("또는", "ambiguous", "땅콩 또는 견과류가공품 등. 실측 434회"),
 ("두류", "ambiguous", "대두 여부 특정 불가. 실측 294회"),
 ("식물성크림", "ambiguous", "원료 특정 불가. 실측 530회"),
 ("견과류", "ambiguous", "어떤 견과인지 특정 불가"),
 ("레시틴", "ambiguous", "대두/해바라기 등 원료 불명"),
]

allergens, keywords = [], []
for i, (code, name, stat, syn, exc) in enumerate(A, 1):
    allergens.append({"id": i, "code": code, "name_ko": name, "is_statutory": stat})
    for k in dict.fromkeys(syn.split()):
        keywords.append({"allergen_code": code, "keyword": k, "is_exclusion": False})
    for k in dict.fromkeys(exc.split()):
        keywords.append({"allergen_code": code, "keyword": k, "is_exclusion": True})
rules = [{"pattern": p, "rule_type": r, "note": n} for p, r, n in T]

# ---- 개발용 샘플 (실제 C002/C005 데이터에서 추출. 없으면 건너뜀) ----
samples = []
try:
    import pandas as pd
    d = ROOT / "csv"
    pr = pd.read_csv(d / "product_reports.csv", dtype=str, keep_default_na=False)
    bc = pd.read_csv(d / "barcodes.csv", dtype=str, keep_default_na=False)
    want = {
     "19493": None,
     "99144": "밀크 계열(혼합탈지분유·유당) → 우유 danger 기대",
    }
    picks = [
     ("19730443003404", "공룡초콜릿: 우유 다수, 혼합분유(복합)"),
     ("19960080359718", "메밀부침가루: 밀 vs 메밀 구분"),
     ("19810336006127", "불닭오징어땅콩: 오징어·새우·모호(또는)·복합"),
     ("2016052807641",  "복숭아+복숭아향: 직접 매칭 + 향료"),
     ("20110493072173", "복숭아에이드: 복숭아향만 → caution(향료)"),
     ("2000047506963",  "동치미: 정제수·채소 → safe 기대"),
     ("2012018838063",  "21곡 한입 크리스피: 우유·밀·대두·혼합분유 다수"),
     ("20110618121275", "땅콩호박: 제품명 오탐(땅콩 제외어) 확인용"),
     ("201603750775",   "게르마늄 포함: 게 오탐 확인용"),
     ("19950306274362", "스파게티면: 복합원재료(혼합제제)만 → caution 기대"),
    ]
    for rn, why in picks:
        r = pr[pr.report_no == rn]
        if r.empty:
            continue
        r = r.iloc[0]
        b = bc[bc.report_no == rn].barcode.tolist()[:2]
        samples.append({"report_no": rn, "product_name": r.product_name,
                        "raw_material": r.raw_material, "barcodes": b, "purpose": why})
except Exception as e:
    print("샘플 생략:", e)

seed = {"allergens": allergens, "allergen_keywords": keywords,
        "term_rules": rules, "samples": samples}
(ROOT / "seed.json").write_text(json.dumps(seed, ensure_ascii=False, indent=2), encoding="utf-8")


def q(s):
    return "'" + s.replace("'", "''") + "'"


sql = ["-- 시드 데이터 (build_seed.py 로 생성). 재실행 안전: 먼저 비우고 다시 넣는다.",
       "begin;",
       "truncate public.allergen_keywords, public.term_rules, public.allergens restart identity cascade;",
       "insert into public.allergens (code, name_ko, is_statutory) values"]
sql.append(",\n".join(f"  ({q(a['code'])}, {q(a['name_ko'])}, {str(a['is_statutory']).lower()})" for a in allergens) + ";")
sql.append("insert into public.allergen_keywords (allergen_id, keyword, is_exclusion)\nselect a.id, v.keyword, v.is_exclusion\nfrom (values")
sql.append(",\n".join(f"  ({q(k['allergen_code'])}, {q(k['keyword'])}, {str(k['is_exclusion']).lower()})" for k in keywords))
sql.append(") as v(code, keyword, is_exclusion)\njoin public.allergens a on a.code = v.code;")
sql.append("insert into public.term_rules (pattern, rule_type, note) values")
sql.append(",\n".join(f"  ({q(t['pattern'])}, {q(t['rule_type'])}, {q(t['note'])})" for t in rules) + ";")
sql.append("commit;")
(ROOT / "sql").mkdir(exist_ok=True)
(ROOT / "sql" / "03_seed.sql").write_text("\n".join(sql) + "\n", encoding="utf-8")

ex = sum(k["is_exclusion"] for k in keywords)
print(f"allergens {len(allergens)} / keywords {len(keywords)-ex} (+제외어 {ex}) / term_rules {len(rules)} / samples {len(samples)}")
