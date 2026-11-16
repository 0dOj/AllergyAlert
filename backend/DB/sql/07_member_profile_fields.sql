-- 구성원(member)에 메모와 아바타 색 컬럼 추가
-- 이미 SQL Editor에서 실행한 내용을 기록용으로 남긴 파일이다. postgres 계정으로 실행하며 추가형 변경이다.
-- 여러 번 실행해도 에러가 나지 않는다.
--
-- 롤백(필요할 때만 SQL Editor에서 직접 실행. notes, avatar_color 값이 사라진다):
--   alter table public.member drop column if exists avatar_color;
--   alter table public.member drop column if exists notes;

begin;

alter table public.member
  add column if not exists notes        text check (char_length(notes) <= 200),        -- 메모. 없으면 NULL
  add column if not exists avatar_color text check (char_length(avatar_color) <= 40);  -- 아바타 색. 없으면 NULL

commit;
