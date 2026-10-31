"""Gitleaks: 코드에 들어간 비밀번호·API 키.

- 현재 파일만 본다 (--no-git). 깃 기록은 보지 않으므로, 지운 키도 기록에는 남아 있을 수 있다 → 키 폐기 안내.
- 저장소의 .gitleaks.toml / .gitleaksignore / 'gitleaks:allow' 주석으로 숨긴 것도 찾는다 (숨김 = 해결 아님).
- 찾은 비밀값은 여기서 바로 가린다. 원래 값은 지문(해시)을 만들 때만 잠깐 쓰고 버린다.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
import time
from pathlib import Path

from .. import fingerprint as fp
from ..models import (
    FLAG_LIKELY_PUBLIC_KEY,
    FLAG_ROTATE_SECRET,
    FLAG_SUPPRESSED_COMMENT,
    PUBLIC_KEY_HINT,
    TOOL_NOT_INSTALLED,
    TOOL_OK,
    ScanOptions,
)
from ..normalize import SourceReader, mask_secret, rel_path, scrub, secret_variants
from .base import ToolRun, error_run, find_binary, run_cmd, tail, tool_version

TOOL = "gitleaks"

# 저장소의 .gitleaks.toml 대신 이걸 쓴다 → 기본 규칙 전체 사용, 저장소 쪽 예외 목록 무시
_FORCED_CONFIG = "[extend]\nuseDefault = true\n"


def run(target: Path, opts: ScanOptions) -> ToolRun:
    binary = find_binary(TOOL)
    if not binary:
        return ToolRun(TOOL, TOOL_NOT_INSTALLED, "gitleaks가 설치되어 있지 않습니다.")
    version = tool_version(binary, ["version"])
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="se-gl-") as tmp:
        tmpdir = Path(tmp)
        report = tmpdir / "report.json"
        cfg = tmpdir / "gitleaks.toml"
        cfg.write_text(_FORCED_CONFIG, encoding="utf-8")
        empty_ignore_dir = tmpdir / "noignore"
        empty_ignore_dir.mkdir()
        cmd = [binary, "detect", "--no-git", "--source", ".",
               "--report-format", "json", "--report-path", str(report),
               "--no-banner", "--log-level", "error",
               "--ignore-gitleaks-allow",
               "--config", str(cfg),
               "--gitleaks-ignore-path", str(empty_ignore_dir),
               "--max-target-megabytes", "5"]
        try:
            proc = run_cmd(cmd, timeout=opts.timeout_sec, cwd=str(target), extra_env=opts.extra_env)
        except subprocess.TimeoutExpired:
            return error_run(TOOL, f"{opts.timeout_sec}초 안에 끝나지 않았습니다.", version)
        except OSError as exc:
            return error_run(TOOL, f"실행 실패: {exc}", version)
        duration = round(time.monotonic() - started, 2)
        if proc.returncode not in (0, 1) or not report.exists():
            r = error_run(TOOL, f"종료 코드 {proc.returncode}: {tail(proc.stderr)}", version)
            r.duration_sec = duration
            return r
        try:
            items = json.loads(report.read_text(encoding="utf-8") or "[]")
        except json.JSONDecodeError as exc:
            return error_run(TOOL, f"결과 JSON을 읽지 못했습니다: {exc}", version)
        finally:
            report.unlink(missing_ok=True)  # 원본 비밀값이 든 파일은 바로 지운다

    findings, secrets = parse(items, target, opts)
    run_ = ToolRun(TOOL, TOOL_OK, "", version, findings, duration)
    run_.secrets = secrets
    return run_


def _severity(rule_id: str) -> str:
    # 서비스가 특정되는 키(AWS, Stripe, GitHub, 개인키 등)는 바로 악용 가능 → critical
    return "high" if rule_id.startswith("generic") else "critical"


_PUBLIC_KEY = re.compile(PUBLIC_KEY_HINT)
_LONG_TOKEN = re.compile(r"[A-Za-z0-9+/=_\-]{24,}")


def _mask_long_tokens(text: str) -> str:
    """두 번째 안전장치: 비밀값이 있던 줄에 남은 긴 무작위 문자열(24자 이상)을 가린다."""
    return _LONG_TOKEN.sub(lambda m: m.group(0)[:4] + "********", text or "")


def _mask_context(ctx: dict | None, start: int | None, end: int | None) -> dict | None:
    if not ctx or not start:
        return ctx
    end = end or start
    lines = [
        _mask_long_tokens(line) if start <= ctx["start_line"] + i <= end else line
        for i, line in enumerate(ctx["lines"])
    ]
    return {"start_line": ctx["start_line"], "lines": lines}


def _fingerprint_secret(secret: str) -> str:
    """지문용 비밀값: 줄바꿈만 \\n으로 통일한다 (#58).

    같은 커밋이라도 Windows(\\r\\n)와 Linux(\\n)에서 받은 여러 줄 개인키가 다른 지문이 되면
    재검사에서 '새로 1 / 해결 1'로 잘못 나뉜다. 줄바꿈 말고는 아무것도 바꾸지 않으므로
    실제 값이 바뀐 비밀은 여전히 다른 지문이 되고, Linux(\\n) 결과의 기존 지문도 그대로다.
    """
    return secret.replace("\r\n", "\n").replace("\r", "\n")


def parse(items: list[dict], target: Path, opts: ScanOptions | None = None,
          reader: SourceReader | None = None) -> tuple[list[dict], list[str]]:
    """(finding 목록, 가려야 할 비밀값 목록). finding에는 원래 비밀값이 들어가지 않는다."""
    opts = opts or ScanOptions()
    reader = reader or SourceReader(target)
    secrets = sorted({v for i in items for v in secret_variants(i.get("Secret") or "")}, key=len, reverse=True)
    findings = []
    for it in items:
        secret = it.get("Secret") or ""
        rule_id = it.get("RuleID", "unknown")
        file = rel_path(it.get("File", ""), target)
        start = it.get("StartLine")
        end = it.get("EndLine") or start
        line_text = reader.line(file, start)
        severity = _severity(rule_id)
        if _PUBLIC_KEY.search(line_text):
            # 검색 전용 키·reCAPTCHA siteKey처럼 원래 공개되는 키: 숨기지 않고 위험도만 낮춘다
            flags = [FLAG_LIKELY_PUBLIC_KEY]
            severity = "low"
        else:
            flags = [FLAG_ROTATE_SECRET]
        if "gitleaks:allow" in line_text:
            flags.append(FLAG_SUPPRESSED_COMMENT)
        description = it.get("Description") or rule_id
        finding = {
            "fingerprint": fp.make(TOOL, rule_id, file,
                                   fp.secret_hash(_fingerprint_secret(secret or it.get("Match", "")))),
            "tool": TOOL,
            "category": "secret",
            "rule_id": rule_id,
            "title": f"코드에 비밀값 노출: {rule_id}",
            "message": description,
            "severity": severity,
            "location": {"file": file, "start_line": start, "end_line": end},
            "package": None,
            "evidence": {
                "snippet": _mask_long_tokens(scrub(reader.span(file, start, end), secrets)),
                "context": _mask_context(scrub(reader.context(file, start, end, opts.context_lines), secrets),
                                         start, end),
                "masked_secret": mask_secret(secret),
                "entropy": it.get("Entropy"),
            },
            "cwe": ["CWE-798"],
            "aliases": [],
            "references": [],
            "published": None,
            "flags": flags,
            "remediation": {"kind": "rotate_secret", "target_version": None, "autofix": None},
        }
        if opts.include_raw:
            raw = {k: v for k, v in it.items() if k not in ("Secret", "Match")}
            raw["Match"] = scrub(it.get("Match", ""), secrets)
            finding["raw"] = raw
        findings.append(finding)
    return findings, secrets
