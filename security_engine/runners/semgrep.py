"""Semgrep: 코드 자체의 위험한 작성 방식.

- 실행 프로그램: Opengrep(LGPL-2.1, Semgrep 호환 오픈소스)을 먼저 쓰고, 없으면 Semgrep CE를 쓴다.
  결과 JSON의 도구 이름은 호환을 위해 그대로 "semgrep"(=코드 검사기)이고, 실제 프로그램은 coverage.semgrep.engine에 적는다.
- 규칙: 우리 규칙(security_engine/rules/*.yml)만 기본으로 쓴다 → 유료 서비스에 써도 되는 구성.
  Semgrep 레지스트리 룰셋(p/default 등)은 'Semgrep Rules License'(SaaS 제공 불가)라 내부 비교용으로만 --with-registry로 켠다.
- 레지스트리(semgrep.dev)에 접속하지 못하면 우리 규칙만으로 다시 돌리고 coverage.message에 남긴다.
- --disable-nosem: 'nosemgrep' 주석으로 숨긴 것도 찾아낸다 (숨김 = 해결 아님). 숨김 주석은 flags로 표시.
- 비밀값 규칙(CWE-798 또는 category: secret-exposure)이 잡은 코드의 따옴표 문자열(8자 이상)은 비밀값으로 보고
  엔진이 결과 전체(증거·메시지·LLM 입력)에서 가린다. Gitleaks가 못 잡은 하드코딩 키도 원문이 남지 않게.
  coverage.semgrep.registry_used: 이번에 레지스트리 규칙을 실제로 썼는지 (재검사 비교에서 '해결' 판단에 사용).
- Semgrep CE는 로그인하지 않으면 코드 줄을 'requires login'으로 가리므로, 증거 코드는 엔진이 파일에서 직접 읽는다.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from .. import fingerprint as fp
from ..models import (
    BUILTIN_RULES_DIR,
    FLAG_ROTATE_SECRET,
    FLAG_SUPPRESSED_COMMENT,
    SEMGREP_EXCLUDES,
    TOOL_NOT_INSTALLED,
    TOOL_OK,
    ScanOptions,
)
from ..normalize import (
    SourceReader,
    first_sentence,
    normalize_code,
    normalize_cwe,
    rel_path,
    scrub,
    severity_from_semgrep,
)
from .base import (
    ToolRun,
    engine_name,
    error_run,
    find_binary,
    run_cmd,
    tail,
    tool_version,
)

TOOL = "semgrep"
LOCAL_PREFIX = "vibe-coding"
# 따옴표로 감싼 8자 이상 문자열 ("…", '…', `…`)
_QUOTED = re.compile(r"""(["'`])((?:\\.|(?!\1).){8,}?)\1""")


def is_secret_rule(cwe: list[str], meta: dict) -> bool:
    return "CWE-798" in cwe or str(meta.get("category", "")).lower() == "secret-exposure"


def quoted_literals(code: str) -> list[str]:
    """코드 조각에서 따옴표 문자열(8자 이상) 값만 뽑는다. 줄바꿈이 낀 것은 제외."""
    return [m.group(2) for m in _QUOTED.finditer(code or "") if "\n" not in m.group(2)]


def builtin_rule_ids() -> set[str]:
    ids = set()
    for f in BUILTIN_RULES_DIR.glob("*.y*ml"):
        ids.update(re.findall(r"^\s*-\s*id:\s*([\w.\-]+)", f.read_text(encoding="utf-8"), re.M))
    return ids


def _cmd(binary: str, configs: list[str], opts: ScanOptions) -> list[str]:
    cmd = [binary, "scan", "--json", "--quiet", "--disable-nosem",
           "--timeout", "30", "--max-target-bytes", "1000000"]
    if engine_name(binary) == "semgrep":
        cmd.append("--metrics=off")  # Opengrep에는 이 옵션이 없다 (사용 통계를 보내지 않음)
    for c in configs:
        cmd += ["--config", c]
    for ex in SEMGREP_EXCLUDES:
        cmd += ["--exclude", ex]
    cmd.append(".")
    return cmd


def _execute(binary, configs, target, opts):
    proc = run_cmd(_cmd(binary, configs, opts), timeout=opts.timeout_sec, cwd=str(target),
                   extra_env=opts.extra_env)
    data = None
    if (proc.stdout or "").strip():
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = None
    fatal = [e for e in (data or {}).get("errors", []) if e.get("level") == "error"]
    ok = data is not None and proc.returncode in (0, 1) and not fatal
    return ok, data, proc, fatal


def run(target: Path, opts: ScanOptions) -> ToolRun:
    binary = find_binary(TOOL)
    if not binary:
        return ToolRun(TOOL, TOOL_NOT_INSTALLED,
                       "코드 검사기(Opengrep 또는 Semgrep)가 설치되어 있지 않습니다. README의 설치 방법을 보세요.")
    version = tool_version(binary, ["--version"])
    engine = engine_name(binary)
    local = [str(BUILTIN_RULES_DIR), *opts.semgrep_extra_configs]
    registry = list(opts.semgrep_registry)
    started = time.monotonic()
    notes = []
    registry_used = bool(registry)
    try:
        ok, data, proc, fatal = _execute(binary, local + registry, target, opts)
        if not ok and registry:
            registry_used = False
            # 레지스트리 접속 실패 등: 우리 규칙만으로 한 번 더
            notes.append(f"레지스트리 규칙({', '.join(registry)})을 쓰지 못해 우리 규칙만 사용했습니다.")
            ok, data, proc, fatal = _execute(binary, local, target, opts)
    except subprocess.TimeoutExpired:
        return error_run(TOOL, f"{opts.timeout_sec}초 안에 끝나지 않았습니다.", version)
    except OSError as exc:
        return error_run(TOOL, f"실행 실패: {exc}", version)
    duration = round(time.monotonic() - started, 2)

    if not ok:
        detail = "; ".join(e.get("message", "")[:200] for e in fatal) or tail(proc.stderr)
        r = error_run(TOOL, f"종료 코드 {proc.returncode}: {detail}", version)
        r.engine = engine
        r.duration_sec = duration
        return r

    warn = [e for e in data.get("errors", []) if e.get("level") != "error"]
    if warn:
        notes.append(f"일부 파일({len(warn)}건)은 문법을 읽지 못해 건너뛰었습니다.")
    secrets: list[str] = []
    findings = parse(data, target, opts, secrets_out=secrets)
    return ToolRun(TOOL, TOOL_OK, " ".join(notes), version, findings, duration, engine=engine,
                   registry_used=registry_used, secrets=secrets)


def normalize_rule_id(check_id: str, local_ids: set[str]) -> str:
    last = check_id.rsplit(".", 1)[-1]
    if last in local_ids:
        return f"{LOCAL_PREFIX}/{last}"
    return check_id


def parse(data: dict, target: Path, opts: ScanOptions | None = None,
          reader: SourceReader | None = None, secrets_out: list[str] | None = None) -> list[dict]:
    """secrets_out: 비밀값 규칙이 잡은 문자열을 여기에 모은다 (엔진이 결과 전체에서 가리는 데 사용).

    parse 자체도 그 finding의 증거 코드·메시지는 바로 가려서 돌려준다 (단독 호출해도 원문이 안 남게).
    """
    opts = opts or ScanOptions()
    reader = reader or SourceReader(target)
    local_ids = builtin_rule_ids()
    findings = []
    for r in data.get("results") or []:
        extra = r.get("extra") or {}
        meta = extra.get("metadata") or {}
        file = rel_path(r.get("path", ""), target)
        start = (r.get("start") or {}).get("line")
        end = (r.get("end") or {}).get("line") or start
        rule_id = normalize_rule_id(r.get("check_id", ""), local_ids)

        # 걸린 코드: offset으로 정확히 자르고, 안 되면 줄 단위로
        matched = ""
        raw = reader.raw(file)
        s_off, e_off = (r.get("start") or {}).get("offset"), (r.get("end") or {}).get("offset")
        if raw is not None and isinstance(s_off, int) and isinstance(e_off, int) and e_off >= s_off:
            matched = raw[s_off:e_off].decode("utf-8", errors="replace")
        snippet = reader.span(file, start, end)
        if not matched:
            matched = snippet

        cwe = normalize_cwe(meta.get("cwe"))
        secret_rule = is_secret_rule(cwe, meta)
        found: list[str] = []
        if secret_rule:
            found = sorted({*quoted_literals(matched), *quoted_literals(snippet)}, key=len, reverse=True)
            if secrets_out is not None:
                secrets_out.extend(x for x in found if x not in secrets_out)

        flags = []
        if secret_rule and found:
            flags.append(FLAG_ROTATE_SECRET)  # 코드에서 지워도 이미 노출된 키는 폐기·재발급 필요
        here, above = reader.line(file, start), reader.line(file, (start or 1) - 1)
        if "nosemgrep" in here or "nosemgrep" in above:
            flags.append(FLAG_SUPPRESSED_COMMENT)

        message = (extra.get("message") or "").strip()
        refs = meta.get("references") or []
        if isinstance(refs, str):
            refs = [refs]
        autofix = extra.get("fix")
        if found:
            # 지문도 비밀값 원문 대신 가린 코드로 만든다 (지문에서 비밀값을 거꾸로 맞혀 보지 못하게)
            matched = scrub(matched, found)
        finding = {
            "fingerprint": fp.make(TOOL, rule_id, file, normalize_code(matched)),
            "tool": TOOL,
            "category": "code",
            "rule_id": rule_id,
            "title": first_sentence(message) or rule_id,
            "message": message,
            "severity": severity_from_semgrep(extra.get("severity"), meta),
            "location": {"file": file, "start_line": start, "end_line": end},
            "package": None,
            "evidence": {
                "snippet": snippet,
                "context": reader.context(file, start, end, opts.context_lines),
            },
            "cwe": cwe,
            "aliases": [],
            "references": [str(x) for x in refs][:8],
            "published": None,
            "flags": flags,
            "remediation": {"kind": "code_change", "target_version": None,
                            "autofix": autofix if isinstance(autofix, str) else None},
        }
        if opts.include_raw:
            finding["raw"] = r
        if found:
            for key in ("evidence", "raw", "title", "message"):
                if key in finding:
                    finding[key] = scrub(finding[key], found)
        findings.append(finding)
    return findings
