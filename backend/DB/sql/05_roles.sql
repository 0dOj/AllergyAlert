-- 6단계: 팀원용 제한 계정 (postgres 관리자 계정 대신 이 계정의 접속 정보를 공유한다)
--   app_backend : API 서버용  - 참조 데이터 읽기, 프로필·이력 읽고 쓰기, 적재 이력 읽기
--   app_ingest  : 야간 배치용 - barcodes/product_reports 적재, 적재 이력 기록
-- 이 파일은 postgres 계정(SQL Editor)으로 실행한다. 비밀번호는 맨 아래에서 따로 설정한다.

-- 1) 계정 생성 (비밀번호가 없으면 로그인할 수 없음. 아래 3)에서 설정)
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'app_backend') then
    create role app_backend login;
  end if;
  if not exists (select 1 from pg_roles where rolname = 'app_ingest') then
    create role app_ingest login;
  end if;
end $$;

-- 2) 권한
grant usage on schema public to app_backend, app_ingest;

-- app_backend
grant select on public.barcodes, public.product_reports, public.allergens,
                public.allergen_keywords, public.term_rules, public.ingest_log to app_backend;
grant select, insert, update, delete on public.user_profile, public.scan_history to app_backend;
grant usage, select on all sequences in schema public to app_backend;

-- app_ingest
grant select, insert, update, delete, truncate on public.barcodes, public.product_reports to app_ingest;
grant select, insert, update on public.ingest_log to app_ingest;
grant select on public.allergens, public.allergen_keywords, public.term_rules to app_ingest;
grant usage, select on all sequences in schema public to app_ingest;

-- 3) RLS 정책 (RLS가 켜져 있어서 권한 + 정책이 모두 있어야 접근 가능)
--    참조 5개 테이블의 SELECT 는 01_schema.sql 의 "read ..." 정책이 이미 허용한다.
drop policy if exists backend_user_profile on public.user_profile;
create policy backend_user_profile on public.user_profile for all to app_backend using (true) with check (true);
drop policy if exists backend_scan_history on public.scan_history;
create policy backend_scan_history on public.scan_history for all to app_backend using (true) with check (true);
drop policy if exists backend_ingest_log_read on public.ingest_log;
create policy backend_ingest_log_read on public.ingest_log for select to app_backend using (true);

drop policy if exists ingest_barcodes on public.barcodes;
create policy ingest_barcodes on public.barcodes for all to app_ingest using (true) with check (true);
drop policy if exists ingest_reports on public.product_reports;
create policy ingest_reports on public.product_reports for all to app_ingest using (true) with check (true);
drop policy if exists ingest_log_rw on public.ingest_log;
create policy ingest_log_rw on public.ingest_log for all to app_ingest using (true) with check (true);

-- 4) 비밀번호 설정: 아래 두 줄에서 '...' 를 길고 무작위인 비밀번호로 바꾼 뒤 '--' 를 지우고 실행한다.
--    (영문+숫자 20자 이상 권장. 서로 다른 비밀번호를 쓰고, postgres 비밀번호와도 다르게.)
-- alter role app_backend with password '...';
-- alter role app_ingest  with password '...';
