-- 사용자 계정 도입: 구성원(member) 테이블 추가, 조회 이력에 소유자 연결
-- 이 파일은 postgres 계정(SQL Editor)으로 실행한다. 추가형 변경이며 기존 테이블과 데이터는 지우지 않는다.
-- 여러 번 실행해도 에러가 나지 않는다.
--
-- 롤백(필요할 때만 SQL Editor에서 직접 실행. member 데이터와 owner_id/member_id 값이 사라진다):
--   drop index if exists public.scan_history_owner_scanned_idx;
--   alter table public.scan_history drop column if exists member_id;
--   alter table public.scan_history drop column if exists owner_id;
--   drop table if exists public.member;
--   -- anon, authenticated 권한은 원래 없었으므로 되돌리지 않는다.

-- 1) 구성원: 로그인한 사용자(auth.users)가 관리하는 알레르기 대상자
create table if not exists public.member (
  id             uuid primary key default gen_random_uuid(),
  owner_id       uuid not null references auth.users(id) on delete cascade,
  name           text not null check (char_length(name) between 1 and 30),
  relation       text check (char_length(relation) <= 20),    -- 본인, 자녀 등. 없으면 NULL
  allergen_codes text[] not null default '{}'
                 check (cardinality(allergen_codes) <= 30),   -- allergens.code 값
  created_at     timestamptz default now()
);

create index if not exists member_owner_id_idx on public.member (owner_id);

-- 2) 조회 이력에 소유자와 구성원 연결
--    배포된 서버가 아직 owner_id 없이 insert하므로 둘 다 NULL을 허용한다.
alter table public.scan_history
  add column if not exists owner_id  uuid references auth.users(id) on delete cascade,
  add column if not exists member_id uuid references public.member(id) on delete set null;

create index if not exists scan_history_owner_scanned_idx
  on public.scan_history (owner_id, scanned_at desc);

-- 3) member 접근 제어: RLS 켜기, 공개 키 권한 제거, 서버 계정만 허용
alter table public.member enable row level security;

revoke all on public.member from anon, authenticated;
grant select, insert, update, delete on public.member to app_backend;

drop policy if exists backend_member on public.member;
create policy backend_member on public.member for all to app_backend using (true) with check (true);

-- 4) 기존 사용자 테이블도 공개 키(anon, authenticated)로는 접근하지 못하게 한다.
revoke all on public.user_profile from anon, authenticated;
revoke all on public.scan_history from anon, authenticated;
