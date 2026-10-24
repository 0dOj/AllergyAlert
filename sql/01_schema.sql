-- 알레르기 체크 앱: 스키마 (Supabase / PostgreSQL)
-- 기준: 3 데이터 모델.md
-- 인덱스는 데이터 적재 후 02_indexes.sql 로 따로 만든다 (적재 속도 때문).

-- 1) 바코드 -> 품목보고번호 색인 (C005 + I2570)
create table if not exists public.barcodes (
  id              bigint generated always as identity primary key,
  barcode         text not null,          -- 정규화된 바코드 (UNIQUE 아님)
  report_no       text,                   -- 품목보고번호
  product_name    text,
  maker_name      text,
  food_type       text,
  industry        text,
  site_addr       text,
  shelf_life_text text,                   -- 소비기한 원문
  report_dt       text,                   -- YYYYMMDD
  end_dt          text,                   -- YYYYMMDD
  clsbiz_dt       text,                   -- YYYYMMDD
  source          text not null check (source in ('C005','I2570')),
  chng_dt         text                    -- YYYYMMDD
);

-- 2) 원재료 마스터 (C002)
create table if not exists public.product_reports (
  report_no    text primary key,
  product_name text,
  maker_name   text,
  food_type    text,
  lcns_no      text,
  report_dt    text,
  raw_material text,                      -- 원재료 원문
  etqty_yn     text,
  chng_dt      text
);

-- 3) 알레르겐 사전
create table if not exists public.allergens (
  id           bigint generated always as identity primary key,
  code         text not null unique,      -- MILK, PEANUT ...
  name_ko      text not null,
  is_statutory boolean not null default true
);

create table if not exists public.allergen_keywords (
  id           bigint generated always as identity primary key,
  allergen_id  bigint not null references public.allergens(id) on delete cascade,
  keyword      text not null,
  is_exclusion boolean not null default false
);

-- 4) 전역 규칙 (다른 테이블과 관계 없음)
create table if not exists public.term_rules (
  id        bigint generated always as identity primary key,
  pattern   text not null,
  rule_type text not null check (rule_type in ('compound','flavor','ambiguous')),
  note      text
);

-- 5) 사용자 데이터
create table if not exists public.user_profile (
  id           bigint generated always as identity primary key,
  allergen_ids jsonb not null default '[]'::jsonb
);

create table if not exists public.scan_history (
  id           bigint generated always as identity primary key,
  barcode      text,
  report_no    text,
  product_name text,
  verdict      text not null check (verdict in ('danger','caution','safe')),
  matched      jsonb,
  scanned_at   timestamptz not null default now()
);

-- 6) 적재 이력
create table if not exists public.ingest_log (
  id          bigint generated always as identity primary key,
  service_id  text not null check (service_id in ('C002','C005','I2570')),
  started_at  timestamptz not null default now(),
  finished_at timestamptz,
  rows        integer not null default 0,
  status      text not null default 'running' check (status in ('running','success','failed')),
  message     text
);

-- 7) RLS: 켜두기 (끄면 공개 키로 누구나 읽고 쓸 수 있음)
alter table public.barcodes          enable row level security;
alter table public.product_reports   enable row level security;
alter table public.allergens         enable row level security;
alter table public.allergen_keywords enable row level security;
alter table public.term_rules        enable row level security;
alter table public.user_profile      enable row level security;
alter table public.scan_history      enable row level security;
alter table public.ingest_log        enable row level security;

-- 참조 테이블은 누구나 읽기만 가능
create policy "read barcodes"          on public.barcodes          for select using (true);
create policy "read product_reports"   on public.product_reports   for select using (true);
create policy "read allergens"         on public.allergens         for select using (true);
create policy "read allergen_keywords" on public.allergen_keywords for select using (true);
create policy "read term_rules"        on public.term_rules        for select using (true);
-- user_profile / scan_history / ingest_log 는 정책 없음 = 서버(백엔드)만 접근
