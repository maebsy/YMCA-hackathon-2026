"""자체 설정 검사기(config) — 외부 프로그램 없이 돈다."""
from pathlib import Path

from security_engine.runners.config import check


def rules(findings):
    return {f["rule_id"].split("/", 1)[1]: f for f in findings}


def write(root: Path, rel: str, text: str = "") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_vibe_site_config_mistakes(tmp_path):
    secret_value = "x" * 12  # 값은 결과에 나오면 안 된다
    write(tmp_path, ".env.local", f"NEXT_PUBLIC_SUPABASE_URL=http://x\nSTRIPE_SECRET_KEY={secret_value}\n")
    write(tmp_path, ".env.example", "STRIPE_SECRET_KEY=\n")
    write(tmp_path, ".gitignore", "node_modules\n")
    write(tmp_path, "public/backup.sql", "insert into users values (1);")
    write(tmp_path, "public/_next/app.js.map", "{}")
    write(tmp_path, "public/_next/vendor.js.map", "{}")
    write(tmp_path, "data/app.sqlite", "")
    write(tmp_path, "next.config.js", "module.exports = { productionBrowserSourceMaps: true };\n")
    write(tmp_path, "package.json", "{}")
    write(tmp_path, "supabase/migrations/001.sql",
          "create table public.profiles (id uuid);\n"
          "create table posts (id int);\n"
          "alter table posts enable row level security;\n"
          "create table auth.audit (id int);\n")
    write(tmp_path, "mysite/settings.py", "DEBUG = True\n")

    found = rules(check(tmp_path))
    assert {"env-file-committed", "gitignore-missing-env", "db-file-public", "db-file-committed",
            "sourcemap-public", "nextjs-browser-sourcemaps", "missing-security-headers",
            "supabase-rls-not-enabled", "django-debug-true", "lockfile-missing"} <= set(found)

    env = found["env-file-committed"]
    assert env["location"]["file"] == ".env.local" and env["severity"] == "high"
    assert "STRIPE_SECRET_KEY" in env["evidence"]["snippet"]
    assert secret_value not in repr(env)                     # 값은 절대 안 나옴
    assert "rotate_secret" in env["flags"]
    assert "2개" in found["sourcemap-public"]["message"]       # 소스맵은 폴더별로 한 건
    rls = [f for f in check(tmp_path) if f["rule_id"].endswith("supabase-rls-not-enabled")]
    assert [f["message"].count("profiles") > 0 for f in rls] == [True]   # profiles만 (posts는 켬, auth는 제외)


def test_clean_site_has_no_findings(tmp_path):
    write(tmp_path, ".gitignore", ".env*\n!.env.example\n")
    write(tmp_path, ".env.example", "STRIPE_SECRET_KEY=\n")
    write(tmp_path, "package.json", "{}")
    write(tmp_path, "package-lock.json", "{}")
    write(tmp_path, "next.config.js", "module.exports = { async headers() { return [] } };\n")
    write(tmp_path, "supabase/migrations/001.sql",
          "create table profiles (id uuid);\nalter table profiles enable row level security;\n")
    write(tmp_path, "tests/fixtures/sample.db", "")
    write(tmp_path, "node_modules/x/.env", "A=1")          # node_modules는 안 봄
    assert check(tmp_path) == []


def test_nextjs_detected_from_package_json(tmp_path):
    """next.config가 없어도 package.json에 next가 있으면 Next.js로 보고 보안 헤더를 확인한다."""
    write(tmp_path, "package.json", '{"dependencies": {"next": "14.2.3"}}')
    write(tmp_path, "pnpm-lock.yaml", "")
    write(tmp_path, "middleware.ts", "export function middleware() {}")
    assert set(rules(check(tmp_path))) == {"missing-security-headers"}
    write(tmp_path, "middleware.ts", "res.headers.set('Content-Security-Policy', \"default-src 'self'\")")
    assert check(tmp_path) == []
