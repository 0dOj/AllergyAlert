-- 5단계: 검증 쿼리 모음. 블록(-- [N] ...)을 하나씩 복사해 SQL Editor에서 실행한다.
-- 각 블록 아래 "기대값"과 비교한다.

-- [1] 테이블별 크기와 DB 전체 크기
select c.relname as table_name,
       pg_size_pretty(pg_total_relation_size(c.oid)) as total_size,
       c.reltuples::bigint as approx_rows
from pg_class c join pg_namespace n on n.oid = c.relnamespace
where n.nspname = 'public' and c.relkind = 'r'
order by pg_total_relation_size(c.oid) desc;
-- 전체 크기:
select pg_size_pretty(pg_database_size(current_database())) as db_size;
-- 기대(제 시험 환경): product_reports 약 319MB / barcodes 약 101MB, 전체 약 428MB. Supabase는 시스템 데이터가 더 있어 +수십MB 가능(무료 한도 500MB)

-- [2] 인덱스 확인
select tablename, indexname from pg_indexes where schemaname = 'public' order by tablename, indexname;
-- 기대: idx_barcodes_barcode, idx_barcodes_report, idx_barcodes_uq, idx_kw_allergen, idx_termrules_type + PK/UNIQUE 인덱스들

-- [3] RLS(행 수준 보안) 확인
select tablename, rowsecurity from pg_tables where schemaname = 'public' order by tablename;
-- 기대: 8개 테이블 모두 rowsecurity = true

-- [4] 데이터 품질 (전부 0이어야 함)
select
  count(*) filter (where barcode !~ '^[0-9]+$')            as non_digit_barcode,
  count(*) filter (where length(barcode) = 12)              as len12_barcode,
  count(*) filter (where product_name = '' or maker_name = '' or report_no = '') as empty_strings,
  count(*) filter (where report_dt is not null and report_dt !~ '^[0-9]{8}$')    as bad_report_dt,
  count(*) filter (where end_dt is not null and end_dt !~ '^[0-9]{8}$')          as bad_end_dt
from barcodes;
select
  count(*) filter (where raw_material = '' or product_name = '') as empty_strings,
  count(*) filter (where raw_material is null)                    as null_raw_material
from product_reports;
-- 기대: 첫 쿼리 전부 0 / 둘째 쿼리 empty_strings 0, null_raw_material 130

-- [5] 소스별 건수와 조인율
select source, count(*) as rows,
       round(100.0 * count(*) filter (where exists (select 1 from product_reports p where p.report_no = b.report_no)) / count(*), 1) as pct_joined
from barcodes b group by source order by source;
-- 기대: C005 246,213 (약 39.5%) / I2570 51,161 (약 33.6%) ← 없는 쪽이 많은 것은 정상(포장육·수입식품·생산중단)

-- [6] F-03 바코드 조회 (C005 우선 -> I2570). 실제 앱이 쓸 쿼리 모양
select b.barcode, b.source, b.product_name, b.maker_name, b.food_type,
       (b.end_dt is not null or b.clsbiz_dt is not null) as discontinued,
       p.raw_material
from barcodes b
left join product_reports p on p.report_no = b.report_no
where b.barcode = '8801118001802'
order by case b.source when 'C005' then 0 else 1 end
limit 1;
-- 기대: 1행 (제품명 '스파게티면', 원재료 있음). 같은 바코드가 2건(다른 품목보고번호)이라 limit 1이 필요
-- 없는 바코드(404 분기)는 0행이어야 함:
select count(*) from barcodes where barcode = '0000000000000';

-- [7] 조회 속도 (EXPLAIN ANALYZE) -> "Execution Time"이 500ms 이내인지 확인
explain (analyze, buffers)
select b.barcode, b.product_name, p.raw_material
from barcodes b left join product_reports p on p.report_no = b.report_no
where b.barcode = '8801118001802'
order by case b.source when 'C005' then 0 else 1 end limit 1;
-- 기대: Index Scan/Index Only Scan(idx_barcodes_uq 또는 idx_barcodes_barcode) 사용, Execution Time 수 ms 이하

-- [8] F-04 제품명 검색 (2글자 이상, 부분 일치, 최대 20건)
explain (analyze) select report_no, product_name from product_reports where product_name like '%김치%' limit 20;
-- 흔한 단어는 빨리 끝나지만, 드문 단어는 전체를 훑는다(Seq Scan). 최악의 경우를 본다:
explain (analyze) select report_no, product_name from product_reports where product_name like '%zzqq%' limit 20;
-- 기대: Seq Scan 으로 나옴(인덱스 없음). Execution Time이 500ms를 넘으면 trigram 인덱스를 검토(용량 필요)

-- [9] 시드 점검
select (select count(*) from allergens) as allergens,
       (select count(*) from allergen_keywords where not is_exclusion) as synonyms,
       (select count(*) from allergen_keywords where is_exclusion) as exclusions,
       (select count(*) from term_rules) as term_rules;
-- 기대: 22 / 303 / 44 / 27
select a.code, count(*) filter (where not k.is_exclusion) as syn, count(*) filter (where k.is_exclusion) as exc
from allergens a left join allergen_keywords k on k.allergen_id = a.id group by a.code order by a.code;
-- 기대: 22행. 모든 알레르겐에 syn >= 1

-- [10] seed.json 샘플 10건이 DB에 있는지
select report_no, product_name from product_reports
where report_no in ('19730443003404','19960080359718','19810336006127','2016052807641','20110493072173',
                    '2000047506963','2012018838063','20110618121275','201603750775','19950306274362')
order by report_no;
-- 기대: 10행

-- [11] 적재 이력
select service_id, rows, status, finished_at from ingest_log order by id;
-- 기대: C002 1,076,677 / C005 246,213 / I2570 51,161 (status = success)
