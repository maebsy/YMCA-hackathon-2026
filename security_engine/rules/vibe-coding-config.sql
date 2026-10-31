# Semgrep 규칙 테스트용 파일 ('semgrep --test'는 SQL의 -- 주석을 읽지 못해서 # 주석을 씀)
# ruleid: supabase-rls-disabled
alter table profiles disable row level security;
# ok: supabase-rls-disabled
alter table profiles enable row level security;
