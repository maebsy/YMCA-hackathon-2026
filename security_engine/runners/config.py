"""자체 설정 검사기: 바이브코딩 사이트에서 자주 나오는 '설정 실수'를 찾는다 (외부 프로그램 없이 파이썬만).

코드 한 줄의 문제가 아니라 '파일이 있으면 안 되는 곳에 있다', '켜야 할 설정을 안 켰다' 같은 문제라서
Opengrep 규칙으로는 잡기 어렵다. 그래서 우리가 직접 만든다 (팀 차트의 '자체 검사기').

| 규칙 ID | 찾는 것 | 위험도 |
|---|---|---|
| config/env-file-committed | .env 파일이 저장소에 올라감 | high |
| config/gitignore-missing-env | .env를 쓰는데 .gitignore에 .env가 없음 | medium |
| config/db-file-public | 공개 폴더에 DB·백업 파일 (.sql .sqlite .db .bak .dump) | high |
| config/db-file-committed | 공개 폴더 밖이라도 DB 파일(.sqlite .db)이 저장소에 올라감 | medium |
| config/sourcemap-public | 공개 폴더에 소스맵(.map) → 원본 코드 노출 | medium |
| config/nextjs-browser-sourcemaps | next.config에서 productionBrowserSourceMaps: true | medium |
| config/supabase-rls-not-enabled | Supabase 테이블을 만들고 RLS를 켜지 않음 | high |
| config/missing-security-headers | Next.js 사이트에 보안 헤더(CSP 등) 설정이 없음 | low |
| config/django-debug-true | Django settings에 DEBUG = True | medium |
| config/lockfile-missing | package.json은 있는데 lockfile이 없음 → 부품 검사·재현 불가 | low |

비밀값은 읽지 않는다: .env 파일은 '변수 이름'만 보고 값은 결과에 넣지 않는다.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

from .. import fingerprint as fp
from ..models import ENGINE_VERSION, FLAG_ROTATE_SECRET, TOOL_OK, ScanOptions
from ..normalize import SourceReader, rel_path
from .base import ToolRun

TOOL = "config"

SKIP_DIRS = {"node_modules", ".git", "vendor", ".venv", "venv", "__pycache__", ".next", ".nuxt",
             "bower_components", "coverage", ".turbo", ".vercel", ".cache"}
PUBLIC_DIRS = {"public", "static", "dist", "build", "out", "_site", "www", "htdocs", "wwwroot"}
ENV_TEMPLATE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".defaults", ".tpl", ".ex")
LOCKFILES = ("package-lock.json", "yarn.lock", "pnpm-lock.yaml", "bun.lockb", "bun.lock", "npm-shrinkwrap.json")
DB_PUBLIC_EXT = (".sql", ".sqlite", ".sqlite3", ".db", ".bak", ".dump", ".backup")
DB_COMMITTED_EXT = (".sqlite", ".sqlite3", ".db")

# 규칙별 위험도, 제목, CWE, 설명을 같은 곳에서 관리한다.
_RULES = {
    "env-file-committed": (
        "high", "환경 변수 파일(.env)이 저장소에 올라감", ["CWE-538"],
        "환경 변수 파일({file})이 저장소에 올라가 있습니다. 보통 DB 비밀번호·API 키가 들어 있어서, 저장소를 본 사람은 누구나 쓸 수 있습니다. "
        "① 안에 든 키를 모두 폐기·재발급 ② 파일을 저장소에서 지우고 .gitignore에 .env* 추가 ③ 배포 환경(Vercel 등) 설정 화면에 값을 넣으세요.",
    ),
    "gitignore-missing-env": (
        "medium", ".gitignore에 .env가 없음", ["CWE-538"],
        ".env 파일을 쓰는 프로젝트인데 .gitignore에 .env가 없습니다. 실수로 키가 든 .env를 올리기 쉽습니다. .gitignore에 '.env*'와 '!.env.example'을 추가하세요.",
    ),
    "db-file-public": (
        "high", "공개 폴더에 DB·백업 파일", ["CWE-530"],
        "누구나 내려받을 수 있는 공개 폴더({dir})에 DB·백업 파일({file})이 있습니다. 사이트 주소 뒤에 파일 이름만 붙이면 회원 정보 등을 통째로 가져갈 수 있습니다. "
        "파일을 지우고, 백업은 공개 폴더가 아닌 비공개 저장소에 두세요.",
    ),
    "db-file-committed": (
        "medium", "DB 파일이 저장소에 올라감", ["CWE-538"],
        "DB 파일({file})이 저장소에 올라가 있습니다. 실제 데이터가 들어 있다면 저장소를 본 사람에게 그대로 노출됩니다. 저장소에서 지우고 .gitignore에 추가하세요.",
    ),
    "sourcemap-public": (
        "medium", "공개 폴더에 소스맵 파일", ["CWE-540"],
        "공개 폴더({dir})에 소스맵(.map) 파일이 {count}개 있습니다. 소스맵이 있으면 방문자가 압축 전 원본 코드(주석·내부 API 주소 포함)를 그대로 볼 수 있습니다. "
        "배포 결과물에서 .map 파일을 빼세요.",
    ),
    "nextjs-browser-sourcemaps": (
        "medium", "운영 사이트에서 소스맵 공개 설정", ["CWE-540"],
        "next.config에서 productionBrowserSourceMaps가 켜져 있어 운영 사이트에서 원본 코드가 공개됩니다. 디버깅이 끝났다면 false로 바꾸세요.",
    ),
    "supabase-rls-not-enabled": (
        "high", "Supabase 테이블 RLS 미설정", ["CWE-284"],
        "Supabase 테이블 '{table}'을(를) 만들고 RLS(행 단위 보안)를 켜지 않았습니다. Supabase는 브라우저에서 바로 DB에 접근하므로, "
        "RLS가 꺼져 있으면 anon 키만으로 누구나 이 테이블을 읽고 고칠 수 있습니다. "
        "'alter table {table} enable row level security;'와 본인 데이터만 허용하는 policy를 추가하세요.",
    ),
    "missing-security-headers": (
        "low", "보안 헤더 설정 없음", ["CWE-693"],
        "Next.js 사이트에 보안 헤더(Content-Security-Policy, X-Frame-Options 등) 설정이 보이지 않습니다. 없으면 XSS·클릭재킹 피해가 커집니다. "
        "next.config의 headers() 또는 middleware에서 보안 헤더를 추가하세요.",
    ),
    "django-debug-true": (
        "medium", "Django DEBUG 모드 켜짐", ["CWE-489"],
        "Django settings에 DEBUG = True가 있습니다. 운영 서버에서 켜져 있으면 오류 화면에 설정값·코드·환경 변수가 그대로 보입니다. 환경 변수로 운영에서는 False가 되게 하세요.",
    ),
    "lockfile-missing": (
        "low", "lockfile 없음", ["CWE-1104"],
        "package.json은 있는데 lockfile(package-lock.json 등)이 없습니다. 설치할 때마다 부품 버전이 달라질 수 있고, 외부 부품 취약점 검사(OSV)도 할 수 없습니다. "
        "'npm install'로 lockfile을 만들어 함께 올리세요.",
    ),
}


def _walk(root: Path):
    """(상대 경로 posix, 파일 이름, 상위 폴더 이름 목록) — 건너뛸 폴더는 내려가지 않는다."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        rel_dir = Path(dirpath).relative_to(root)
        parts = [p.lower() for p in rel_dir.parts]
        for name in filenames:
            yield rel_path(Path(dirpath) / name, root), name, parts


def _finding(check: str, file: str, line: int | None, snippet: str, key: str = "", **fmt) -> dict:
    severity, title, cwe, msg = _RULES[check]
    message = msg.format(file=file, **fmt)
    rule_id = f"{TOOL}/{check}"
    return {
        "fingerprint": fp.make(TOOL, rule_id, file, key),
        "tool": TOOL,
        "category": "config",
        "rule_id": rule_id,
        "title": title,
        "message": message,
        "severity": severity,
        "location": {"file": file, "start_line": line, "end_line": line},
        "package": None,
        "evidence": {"snippet": snippet, "context": None},
        "cwe": cwe,
        "aliases": [],
        "references": [],
        "published": None,
        "flags": [FLAG_ROTATE_SECRET] if check == "env-file-committed" else [],
        "remediation": {"kind": "config_change", "target_version": None, "autofix": None},
    }


def _env_var_names(text: str) -> list[str]:
    names = []
    for line in text.splitlines():
        m = re.match(r"\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m:
            names.append(m.group(1))
    return names


_CREATE_TABLE = re.compile(
    r'create\s+table\s+(?:if\s+not\s+exists\s+)?((?:"?\w+"?\.)?"?\w+"?)', re.I)
_ENABLE_RLS = re.compile(
    r'alter\s+table\s+(?:only\s+)?(?:if\s+exists\s+)?((?:"?\w+"?\.)?"?\w+"?)\s+enable\s+row\s+level\s+security', re.I)


def _table_key(name: str) -> tuple[str | None, str]:
    name = name.replace('"', "").lower()
    if "." in name:
        schema, table = name.split(".", 1)
        return schema, table
    return None, name


def check(target: Path) -> list[dict]:
    root = target.resolve()
    reader = SourceReader(root)
    files = list(_walk(root))
    names = {f for f, _, _ in files}
    out: list[dict] = []

    uses_env = False
    sourcemaps: dict[str, list[str]] = {}
    sql_files: list[str] = []
    next_configs: list[str] = []
    is_supabase = any(f.startswith("supabase/") for f in names)

    for f, name, parts in files:
        lname = name.lower()
        in_public = bool(set(parts) & PUBLIC_DIRS)
        public_dir = next((p for p in parts if p in PUBLIC_DIRS), "")

        # .env 파일 (값은 읽어서 이름만 뽑고 버린다)
        if lname == ".env" or lname.startswith(".env."):
            uses_env = True
            if not lname.endswith(ENV_TEMPLATE_SUFFIXES):
                raw = reader.raw(f)
                var_names = _env_var_names(raw.decode("utf-8", "replace")) if raw else []
                shown = ", ".join(var_names[:8]) + (" …" if len(var_names) > 8 else "")
                snippet = f"변수 {len(var_names)}개: {shown}" if var_names else "(내용 없음 또는 읽을 수 없음)"
                out.append(_finding("env-file-committed", f, None, snippet, key=f))

        # DB·백업 파일
        if lname.endswith(DB_PUBLIC_EXT) and in_public:
            out.append(_finding("db-file-public", f, None, f, key=f, dir=public_dir))
        elif lname.endswith(DB_COMMITTED_EXT) and not ({"test", "tests", "fixtures", "__tests__"} & set(parts)):
            out.append(_finding("db-file-committed", f, None, f, key=f))

        # 소스맵 (공개 폴더별로 한 건으로 묶음)
        if lname.endswith((".js.map", ".css.map", ".mjs.map")) and in_public:
            top = "/".join(f.split("/")[: parts.index(public_dir) + 1]) if public_dir in parts else public_dir
            sourcemaps.setdefault(top, []).append(f)

        if lname.endswith(".sql"):
            sql_files.append(f)
        if re.match(r"next\.config\.(js|mjs|cjs|ts)$", lname):
            next_configs.append(f)

        # Django DEBUG
        if re.match(r"settings(_\w+)?\.py$", lname) or (lname.endswith(".py") and "settings" in parts):
            for i, line in enumerate(reader.lines(f) or [], 1):
                if re.match(r"\s*DEBUG\s*=\s*True\b", line):
                    out.append(_finding("django-debug-true", f, i, line.strip(), key=line.strip()))
                    break

        # package.json 옆 lockfile
        if lname == "package.json":
            folder = f.rsplit("/", 1)[0] if "/" in f else ""
            prefix = f"{folder}/" if folder else ""
            if not any(f"{prefix}{lock}" in names for lock in LOCKFILES) and not in_public:
                out.append(_finding("lockfile-missing", f, None, f, key=f))

    for top, maps in sourcemaps.items():
        out.append(_finding("sourcemap-public", maps[0], None, "\n".join(maps[:5]), key=top,
                            dir=top, count=len(maps)))

    # .gitignore에 .env
    if uses_env:
        gi = reader.lines(".gitignore")
        has_env_rule = bool(gi) and any(re.match(r"^\s*/?\*?\.env", ln) for ln in gi)
        if not has_env_rule:
            out.append(_finding("gitignore-missing-env", ".gitignore" if gi is not None else ".gitignore (없음)",
                                None, "(.env 규칙 없음)", key="gitignore"))

    # Next.js: 소스맵 공개 설정, 보안 헤더 (next.config가 없어도 package.json에 next가 있으면 Next.js 사이트)
    is_next = bool(next_configs) or any(
        re.search(r'"next"\s*:', "\n".join(reader.lines(f) or []))
        for f in names if f.endswith("package.json") and "/" not in f.strip("/"))
    if is_next:
        has_headers = False
        for cfg in next_configs:
            text = "\n".join(reader.lines(cfg) or [])
            m = re.search(r"productionBrowserSourceMaps\s*:\s*true", text)
            if m:
                line = text[: m.start()].count("\n") + 1
                out.append(_finding("nextjs-browser-sourcemaps", cfg, line, m.group(0), key=cfg))
            if re.search(r"\bheaders\s*(\(|:)", text) or "Content-Security-Policy" in text:
                has_headers = True
        for extra in ("middleware.ts", "middleware.js", "src/middleware.ts", "src/middleware.js", "vercel.json",
                      "netlify.toml", "public/_headers", "_headers"):
            if extra in names:
                text = "\n".join(reader.lines(extra) or [])
                if re.search(r"Content-Security-Policy|X-Frame-Options|\"headers\"|\[\[headers\]\]", text) \
                        or extra.endswith("_headers"):
                    has_headers = True
        if not has_headers:
            where = next_configs[0] if next_configs else "package.json"
            out.append(_finding("missing-security-headers", where, None, where, key="headers"))

    # Supabase: 만든 테이블 중 RLS를 켜지 않은 것
    if is_supabase and sql_files:
        created: dict[tuple, tuple[str, int, str]] = {}
        enabled: set[tuple] = set()
        for f in sorted(sql_files):
            text = "\n".join(reader.lines(f) or [])
            for m in _CREATE_TABLE.finditer(text):
                schema, table = _table_key(m.group(1))
                if schema not in (None, "public"):
                    continue  # auth., storage. 등 Supabase 내부 스키마는 제외
                line = text[: m.start()].count("\n") + 1
                created.setdefault(("public", table), (f, line, m.group(0)))
            for m in _ENABLE_RLS.finditer(text):
                schema, table = _table_key(m.group(1))
                enabled.add((schema or "public", table))
        for key, (f, line, snippet) in sorted(created.items()):
            if key not in enabled:
                out.append(_finding("supabase-rls-not-enabled", f, line, snippet, key=key[1], table=key[1]))

    return out


def run(target: Path, opts: ScanOptions) -> ToolRun:
    started = time.monotonic()
    findings = check(target)
    if opts.include_raw:
        for f in findings:
            f["raw"] = None
    return ToolRun(TOOL, TOOL_OK, "", ENGINE_VERSION, findings, round(time.monotonic() - started, 2), engine="builtin")
