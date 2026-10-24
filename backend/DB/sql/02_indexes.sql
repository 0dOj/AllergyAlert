-- 데이터 적재(4단계) 완료 후 실행. 시간이 걸릴 수 있음.
create index if not exists idx_barcodes_barcode   on public.barcodes(barcode);
create index if not exists idx_barcodes_report    on public.barcodes(report_no);
create unique index if not exists idx_barcodes_uq on public.barcodes(barcode, report_no, source);
create index if not exists idx_kw_allergen        on public.allergen_keywords(allergen_id);
create index if not exists idx_termrules_type     on public.term_rules(rule_type);

-- 제품명 인덱스는 용량이 큼. 용량(pg_database_size)을 확인한 뒤 필요할 때만 실행.
-- create index if not exists idx_barcodes_name on public.barcodes(product_name);
-- create index if not exists idx_reports_name  on public.product_reports(product_name);

analyze;
