"""OSV-Scanner: 외부 부품(의존성)의 알려진 취약점.

- lockfile(package-lock.json, yarn.lock, pnpm-lock.yaml, requirements.txt, Gemfile.lock 등)을 읽는다.
- 인터넷(api.osv.dev)에 물어본다. --offline 옵션이면 미리 받아둔 DB를 쓴다.
- 종료 코드: 0 = 취약점 없음, 1 = 취약점 있음, 128 = 읽을 파일 없음, 그 외 = 실패
  실패를 '문제 0건'으로 착각하면 검사 안 한 것을 안전하다고 보여주게 되므로 반드시 구분한다.
- 저장소에 osv-scanner.toml(무시 목록)이 있어도 무시하지 않도록 빈 설정 파일을 강제로 쓴다.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path

from .. import fingerprint as fp
from ..models import (
    SEVERITIES,
    TOOL_NO_TARGET,
    TOOL_NOT_INSTALLED,
    TOOL_OK,
    ScanOptions,
)
from ..normalize import (
    normalize_cwe,
    pick_fix_version,
    rel_path,
    severity_from_cvss,
    severity_from_osv_label,
)
from .base import ToolRun, error_run, find_binary, run_cmd, tail, tool_version

TOOL = "osv"
NO_LOCKFILE_MSG = (
    "읽을 수 있는 잠금 파일(lockfile)이 없어 외부 부품 검사를 하지 못했습니다. "
    "package.json만 있다면 'npm install'로 package-lock.json을 만들어 저장소에 올려주세요."
)


def run(target: Path, opts: ScanOptions) -> ToolRun:
    binary = find_binary(TOOL)
    if not binary:
        return ToolRun(TOOL, TOOL_NOT_INSTALLED, "osv-scanner가 설치되어 있지 않습니다.")
    version = tool_version(binary, ["--version"])
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="se-osv-") as tmp:
        empty_cfg = Path(tmp) / "osv-scanner.toml"
        empty_cfg.write_text("", encoding="utf-8")
        cmd = [binary, "scan", "source", "-r", str(target), "--format", "json",
               "--config", str(empty_cfg)]
        if opts.osv_offline:
            cmd.append("--offline-vulnerabilities")
        try:
            proc = run_cmd(cmd, timeout=opts.timeout_sec, extra_env=opts.extra_env)
        except subprocess.TimeoutExpired:
            return error_run(TOOL, f"{opts.timeout_sec}초 안에 끝나지 않았습니다.", version)
        except OSError as exc:
            return error_run(TOOL, f"실행 실패: {exc}", version)

    duration = round(time.monotonic() - started, 2)
    if proc.returncode == 128:
        run_ = ToolRun(TOOL, TOOL_NO_TARGET, NO_LOCKFILE_MSG, version)
        run_.duration_sec = duration
        return run_
    if proc.returncode not in (0, 1) or not (proc.stdout or "").strip():
        hint = ""
        if "api.osv.dev" in (proc.stderr or "") or "offline" in (proc.stderr or "").lower():
            hint = " (취약점 DB에 접속하지 못했습니다. 인터넷 연결 또는 --osv-offline 설정을 확인하세요.)"
        r = error_run(TOOL, f"종료 코드 {proc.returncode}{hint}: {tail(proc.stderr)}", version)
        r.duration_sec = duration
        return r
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return error_run(TOOL, f"결과 JSON을 읽지 못했습니다: {exc}", version)

    findings = parse(data, target, opts)
    return ToolRun(TOOL, TOOL_OK, "", version, findings, duration)


def _fixed_versions(vuln: dict, pkg_name: str, ecosystem: str) -> list[str]:
    out = []
    for aff in vuln.get("affected") or []:
        p = aff.get("package") or {}
        if p.get("name") != pkg_name:
            continue
        if ecosystem and p.get("ecosystem") and p.get("ecosystem") != ecosystem:
            continue
        for rng in aff.get("ranges") or []:
            for ev in rng.get("events") or []:
                if "fixed" in ev and ev["fixed"] not in out:
                    out.append(ev["fixed"])
    return out


def _group_severity(vulns: list[dict], group: dict) -> str:
    labels = [severity_from_osv_label((v.get("database_specific") or {}).get("severity")) for v in vulns]
    labels = [s for s in labels if s]
    if labels:
        return min(labels, key=SEVERITIES.index)
    return severity_from_cvss(group.get("max_severity")) or "unknown"


def _primary_id(ids: list[str], aliases: list[str]) -> str:
    """지문용 대표 ID: CVE가 있으면 CVE(가장 안 바뀜), 없으면 정렬한 첫 ID."""
    cves = sorted(a for a in aliases if a.startswith("CVE-"))
    if cves:
        return cves[0]
    return sorted(ids)[0]


def parse(data: dict, target: Path, opts: ScanOptions | None = None) -> list[dict]:
    opts = opts or ScanOptions()
    findings = []
    for result in data.get("results") or []:
        lockfile = rel_path((result.get("source") or {}).get("path", ""), target)
        for pkg_entry in result.get("packages") or []:
            pkg = pkg_entry.get("package") or {}
            name, version, eco = pkg.get("name", ""), pkg.get("version", ""), pkg.get("ecosystem", "")
            by_id = {v.get("id"): v for v in pkg_entry.get("vulnerabilities") or []}
            groups = pkg_entry.get("groups") or [
                {"ids": [vid], "aliases": by_id[vid].get("aliases") or []} for vid in by_id
            ]
            for group in groups:
                ids = [i for i in group.get("ids") or [] if i]
                vulns = [by_id[i] for i in ids if i in by_id]
                if not ids or not vulns:
                    continue
                main = vulns[0]
                aliases = sorted(set((group.get("aliases") or []) + ids +
                                     [a for v in vulns for a in v.get("aliases") or []]))
                fixed = []
                for v in vulns:
                    for f in _fixed_versions(v, name, eco):
                        if f not in fixed:
                            fixed.append(f)
                cwe = []
                for v in vulns:
                    cwe += [c for c in normalize_cwe((v.get("database_specific") or {}).get("cwe_ids"))
                            if c not in cwe]
                refs = []
                for v in vulns:
                    for r in v.get("references") or []:
                        if r.get("url") and r["url"] not in refs:
                            refs.append(r["url"])
                primary = _primary_id(ids, aliases)
                title = main.get("summary") or (main.get("details") or "").split("\n")[0] or primary
                recommended = pick_fix_version(version, fixed, eco)
                finding = {
                    "fingerprint": fp.make(TOOL, eco, name, primary, lockfile),
                    "tool": TOOL,
                    "category": "dependency",
                    "rule_id": primary,
                    "title": f"{name} {version}: {title}",
                    "message": (main.get("details") or main.get("summary") or "")[:2000],
                    "severity": _group_severity(vulns, group),
                    "location": {"file": lockfile, "start_line": None, "end_line": None},
                    "package": {
                        "name": name, "version": version, "ecosystem": eco,
                        "fixed_versions": fixed,
                    },
                    "evidence": {"snippet": f"{name}@{version}", "context": None},
                    "cwe": cwe,
                    "aliases": aliases,
                    "references": refs[:8],
                    "published": main.get("published"),
                    "flags": [],
                    "remediation": {
                        "kind": "upgrade_dependency" if recommended else "no_fix_available",
                        "target_version": recommended,
                        "autofix": None,
                    },
                }
                if opts.include_raw:
                    finding["raw"] = {"package": pkg, "group": group, "vulnerabilities": vulns}
                findings.append(finding)
    return findings


def ignored_ids(target: Path) -> dict[str, list[str]]:
    """저장소 안 osv-scanner.toml의 [[IgnoredVulns]] 목록 {파일: [ID…]} (꼼수 탐지용)."""
    out: dict[str, list[str]] = {}
    for cfg in _walk(target, "osv-scanner.toml"):
        text = cfg.read_text(encoding="utf-8", errors="replace")
        ids = []
        try:
            import tomllib  # Python 3.11+
            data = tomllib.loads(text)
            ids = [str(e.get("id")) for e in data.get("IgnoredVulns", []) if e.get("id")]
        except Exception:  # 3.10 또는 문법 오류: 대충이라도 찾는다
            import re
            ids = re.findall(r'^\s*id\s*=\s*"([^"]+)"', text, re.M)
        if ids:
            out[rel_path(cfg, target)] = ids
    return out


def _walk(root: Path, filename: str):
    skip = {"node_modules", ".git", "vendor", ".venv", "venv"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in skip]
        if filename in filenames:
            yield Path(dirpath) / filename
