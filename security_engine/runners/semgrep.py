"""Semgrep: 코드 자체의 위험한 작성 방식.

- 우리 규칙(security_engine/rules/*.yml)은 항상 쓰고, 기본으로 Semgrep 레지스트리 룰셋(p/default)도 함께 쓴다.
  레지스트리에 접속하지 못하면 우리 규칙만으로 다시 돌린다. (레지스트리 규칙은 SaaS 제공 불가 라이선스 → 상용화 땐 끔)
- 레지스트리(semgrep.dev)에 접속하지 못하면 우리 규칙만으로 다시 돌리고 coverage.message에 남긴다.
- --disable-nosem: 'nosemgrep' 주석으로 숨긴 것도 찾아낸다 (숨김 = 해결 아님). 숨김 주석은 flags로 표시.
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
    severity_from_semgrep,
)
from .base import ToolRun, error_run, find_binary, run_cmd, tail, tool_version

TOOL = "semgrep"
LOCAL_PREFIX = "vibe-coding"


def builtin_rule_ids() -> set[str]:
    ids = set()
    for f in BUILTIN_RULES_DIR.glob("*.y*ml"):
        ids.update(re.findall(r"^\s*-\s*id:\s*([\w.\-]+)", f.read_text(encoding="utf-8"), re.M))
    return ids


def _cmd(binary: str, configs: list[str], opts: ScanOptions) -> list[str]:
    cmd = [binary, "scan", "--json", "--quiet", "--metrics=off", "--disable-nosem",
           "--timeout", "30", "--max-target-bytes", "1000000"]
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
        return ToolRun(TOOL, TOOL_NOT_INSTALLED, "semgrep이 설치되어 있지 않습니다. (pip install semgrep)")
    version = tool_version(binary, ["--version"])
    local = [str(BUILTIN_RULES_DIR), *opts.semgrep_extra_configs]
    registry = list(opts.semgrep_registry)
    started = time.monotonic()
    notes = []
    try:
        ok, data, proc, fatal = _execute(binary, local + registry, target, opts)
        if not ok and registry:
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
        r.duration_sec = duration
        return r

    warn = [e for e in data.get("errors", []) if e.get("level") != "error"]
    if warn:
        notes.append(f"일부 파일({len(warn)}건)은 문법을 읽지 못해 건너뛰었습니다.")
    findings = parse(data, target, opts)
    return ToolRun(TOOL, TOOL_OK, " ".join(notes), version, findings, duration)


def normalize_rule_id(check_id: str, local_ids: set[str]) -> str:
    last = check_id.rsplit(".", 1)[-1]
    if last in local_ids:
        return f"{LOCAL_PREFIX}/{last}"
    return check_id


def parse(data: dict, target: Path, opts: ScanOptions | None = None,
          reader: SourceReader | None = None) -> list[dict]:
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

        flags = []
        here, above = reader.line(file, start), reader.line(file, (start or 1) - 1)
        if "nosemgrep" in here or "nosemgrep" in above:
            flags.append(FLAG_SUPPRESSED_COMMENT)

        message = (extra.get("message") or "").strip()
        refs = meta.get("references") or []
        if isinstance(refs, str):
            refs = [refs]
        autofix = extra.get("fix")
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
            "cwe": normalize_cwe(meta.get("cwe")),
            "aliases": [],
            "references": [str(x) for x in refs][:8],
            "published": None,
            "flags": flags,
            "remediation": {"kind": "code_change", "target_version": None,
                            "autofix": autofix if isinstance(autofix, str) else None},
        }
        if opts.include_raw:
            finding["raw"] = r
        findings.append(finding)
    return findings
