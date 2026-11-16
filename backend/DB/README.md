# 알레르기 체크 앱 — DB 안내 (팀원용)

> 이 폴더(`backend/DB`)에 DB 관련 파일이 모여 있다: `sql/`(스키마·시드·검증), `scripts/`(가공·적재·점검), `seed.json`, 원본/가공 데이터(`csvgz/`, `csv/`, git 제외).
> 명령은 모두 저장소 루트(`CapstoneProject`)에서 실행한다고 가정한다.

Supabase(PostgreSQL)에 식약처 공공데이터와 알레르겐 사전이 들어 있다. 설계 근거는 `3 데이터 모델.md`.

## 1. 접속 방법

| 역할 | 쓰는 것 | 계정 |
|---|---|---|
| API 서버 (BE-B) | `DATABASE_URL` | `app_backend` |
| 야간 배치 (BE-A) | `INGEST_DATABASE_URL` | `app_ingest` |
| 프론트 (FE-A, FE-B) | DB에 직접 접속하지 않고 **FastAPI를 호출**한다 | - |

1. `.env.example` 을 복사해 `.env` 로 이름을 바꾸고, 전달받은 접속 문자열을 넣는다. **`.env` 는 git에 올리지 않는다.**
2. 접속 문자열은 **Session pooler** 주소(포트 5432)다. Direct connection(IPv6 전용)은 쓰지 않는다.
3. 비밀번호에 `@ / : # ?` 같은 문자가 있으면 URL 인코딩이 필요하다 (Python: `urllib.parse.quote(pw, safe="")`).
4. SQLAlchemy는 드라이버를 지정한다: `postgresql+psycopg://...` (`pip install "psycopg[binary]"`).
5. 접속이 되는지: `python backend/DB/scripts/check_roles.py`

권한은 계정별로 제한되어 있다. `app_backend` 는 참조 데이터를 읽고 `user_profile`·`scan_history` 를 읽고 쓴다. `barcodes`·`product_reports` 는 쓸 수 없다. 스키마 변경과 시드 수정은 관리자(프로젝트 소유자)가 한다.

## 2. 테이블

| 테이블 | 행 수 | 설명 |
|---|---|---|
| `barcodes` | 297,374 | 바코드 -> 품목보고번호 색인 (C005 246,213 + I2570 51,161) |
| `product_reports` | 1,076,677 | 원재료 원문을 가진 마스터 (C002). PK `report_no` |
| `allergens` | 22 | 법정 19종 + 굴·전복·홍합 분리 (조개류도 별도 행) |
| `allergen_keywords` | 347 | 동의어 303 + 제외어 44. **알레르겐별** 제외어 |
| `term_rules` | 27 | 복합원재료 17 / 향료 5 / 모호표기 5. 알레르겐과 무관한 전역 규칙. `$` 로 시작하면 접미사 |
| `user_profile` | - | 단일 사용자. `allergen_ids` 는 jsonb |
| `scan_history` | - | 조회 이력. `matched` 는 판정 스냅샷(jsonb), 재계산하지 않는다. `owner_id` 는 `auth.users.id` (서버는 항상 값을 넣고 소유자 조건으로만 조회한다) |
| `member` | - | 로그인 사용자(`owner_id`)가 관리하는 알레르기 대상자. `notes`(200자 이하), `avatar_color`(40자 이하)는 `07_member_profile_fields.sql` 로 추가했고 NULL 허용 |
| `ingest_log` | - | 적재 이력 |

## 3. 꼭 지킬 규칙

- **바코드는 저장할 때와 조회할 때 같은 함수로 정규화한다.** 숫자만 남기고, 12자리면 앞에 `0` (UPC-A -> EAN-13).
  ```python
  import re
  def normalize_barcode(s: str) -> str:
      s = re.sub(r"\D", "", s)
      return "0" + s if len(s) == 12 else s
  ```
  ```ts
  export const normalizeBarcode = (s: string) => {
    const d = s.replace(/\D/g, "");
    return d.length === 12 ? "0" + d : d;
  };
  ```
- 바코드·품목보고번호는 항상 **문자열**이다. 숫자로 바꾸면 앞자리 0이 사라진다.
- `barcodes.barcode` 는 UNIQUE가 아니다. 같은 바코드에 다른 품목보고번호가 붙을 수 있다 -> 조회는 `limit 1`.
- `barcodes` 의 약 60%는 `product_reports` 에 대응 행이 없다(포장육·수입식품·생산중단 등). **정상**이다. 이 경우 제품명·제조사만 보여주고 원재료는 비어 있다(`caution`).
- 날짜는 `YYYYMMDD` 문자열이고, 값이 없으면 NULL이다.
- 원재료 원문을 파싱해서 저장하지 않는다. 매칭은 앱 코드에서 한다.
- 제외어는 알레르겐별이다. `메밀` 은 WHEAT의 제외어이고 BUCKWHEAT의 동의어다. 전역 제외어를 만들지 않는다.
- 복합원재료라고 알레르겐 검사를 건너뛰지 않는다. `혼합분유` 는 복합원재료이면서 우유다. 두 판정을 모두 적용하고 `danger` 를 우선한다.

## 4. 자주 쓰는 쿼리

**F-03 바코드 조회 (C005 우선 -> I2570)**
```sql
select b.barcode, b.source, b.report_no, b.product_name, b.maker_name, b.food_type,
       (b.end_dt is not null or b.clsbiz_dt is not null) as discontinued,
       p.raw_material
from barcodes b
left join product_reports p on p.report_no = b.report_no
where b.barcode = :barcode
order by case b.source when 'C005' then 0 else 1 end
limit 1;
```
0행이면 404 + `fallback: search_by_name`.

**F-04 제품명 검색** (2글자 이상, 최대 20건, 결과 0건도 200)
검색어의 `\`, `%`, `_` 는 이스케이프한다.
```sql
select report_no, product_name, maker_name, food_type
from product_reports
where product_name like '%' || :q_escaped || '%' escape '\'
order by product_name
limit 20;
```
```python
q_escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
```
인덱스가 없어서 드문 검색어는 전체를 훑는다. 최악의 경우 약 1.2초이므로 프론트에서 로딩 표시를 한다.

**F-05 원재료 조회**
```sql
select raw_material from product_reports where report_no = :report_no;
```
`product_reports` 는 품목보고번호당 1행이다. 값이 NULL이면 빈 문자열 + `caution`.

**알레르겐 사전**
```sql
select a.code, a.name_ko, k.keyword, k.is_exclusion
from allergens a join allergen_keywords k on k.allergen_id = a.id;
select pattern, rule_type from term_rules;
```
앱 시작 시 한 번 읽어 메모리에 둔다.

**프로필 (단일 사용자)**
```sql
select id, allergen_ids from user_profile order by id limit 1;
insert into user_profile (allergen_ids) select :ids::jsonb where not exists (select 1 from user_profile);
update user_profile set allergen_ids = :ids::jsonb where id = :id;
```

**F-10 이력**
```sql
insert into scan_history (owner_id, barcode, report_no, product_name, verdict, matched)
values (:owner, :barcode, :report_no, :name, :verdict, :matched::jsonb);
select id, product_name, verdict, scanned_at from scan_history where owner_id = :owner order by scanned_at desc limit 50;
select id, scanned_at, matched from scan_history where id = :id and owner_id = :owner;
delete from scan_history where id = :id and owner_id = :owner;
```

## 5. 알려진 한계

- 무료 플랜 DB 한도 500MB. 현재 약 431MB다. 인덱스·데이터를 추가하기 전에 크기를 확인한다.
- 7일 동안 활동이 없으면 무료 프로젝트는 일시정지된다. 시연 전에 접속해 깨어 있는지 확인한다.
- 바코드 데이터는 2018년 이후 갱신이 중단되어 최신 제품은 없다. 전체 조인율은 약 40%다.
- 동의어·제외어 사전은 초안이다. 실데이터 빈도로 검증해 보완한다 (`backend/DB/scripts/build_seed.py` 수정 후 `backend/DB/sql/03_seed.sql` 재실행, 또는 대시보드 Table Editor).

## 6. DB를 처음부터 다시 만들기

복구용 절차다 (원본 데이터: `backend/DB/csvgz/*.csv.gz`).
1. SQL Editor: `backend/DB/sql/01_schema.sql` -> `03_seed.sql` -> `05_roles.sql` (비밀번호 설정 포함)
2. `python backend/DB/scripts/prepare_data.py`
3. `python backend/DB/scripts/load_data.py --indexes`
4. `backend/DB/sql/04_verify.sql` 로 검증

## 7. 변경 규칙

- 스키마 변경은 `backend/DB/sql/` 폴더에 번호를 붙인 SQL 파일로 남기고(예: `06_xxx.sql`), 대시보드에서 직접 고치지 않는다.
- 데이터를 `backend/DB/scripts/` 외의 방법으로 수정했다면 팀에 알린다.
