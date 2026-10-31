"""명령줄 실행.

    python -m security_engine doctor
    python -m security_engine scan ./my-site -o result.json
    python -m security_engine scan ./my-site --previous result.json -o result2.json
    python -m security_engine scan --repo-url https://github.com/someone/someone.github.io -o result.json
    python -m security_engine compare old.json new.json -o compared.json

결과 JSON은 -o 파일(없으면 표준 출력)로, 사람이 읽는 요약은 표준 오류로 나간다.
종료 코드: 0 = 검사 완료(문제가 있어도 0), 2 = 사용법 오류, 3 = 검사 실패, 1 = --fail-on 기준 이상 문제 있음
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import compare_results, doctor, scan, scan_repo
from .git import CloneError
from .llm_input import build_llm_input, render_llm_text
from .models import (
    CODE_ISSUE,
    SEVERITIES,
    SEVERITY_RANK,
    STATUS_LABEL_KO,
    TOOLS,
    ScanOptions,
)


def _utf8_streams() -> None:
    # Windows 콘솔(cp949)에서 한글·특수문자 출력이 깨지거나 죽지 않게
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write(result: dict, output: str | None, compact: bool) -> None:
    text = json.dumps(result, ensure_ascii=False, indent=None if compact else 2)
    if output:
        Path(output).parent.mkdir(parents=True, exist_ok=True)
        Path(output).write_text(text + "\n", encoding="utf-8")
    else:
        sys.stdout.write(text + "\n")


def _print_summary(r: dict) -> None:
    p = lambda *a: print(*a, file=sys.stderr)  # noqa: E731
    p(f"\n[보안엔진] {r['target']['path']}  ({r['status']}, {r['duration_sec']}초)")
    for tool, c in r["coverage"].items():
        extra = f" - {c['message']}" if c["message"] else ""
        name = f"{tool}({c['engine']})" if c.get("engine") and c["engine"] not in (tool, "builtin") else tool
        p(f"  {name:<18} {c['status']:<13} {c['count']}건{extra}")
    s = r["summary"]
    sev = ", ".join(f"{k} {v}" for k, v in s["by_severity"].items() if v)
    p(f"  열린 문제 {s['open']}건" + (f" ({sev})" if sev else ""))
    if s["by_change"]["unverifiable"]:
        p(f"  주의: 지난번 문제 중 {s['by_change']['unverifiable']}건은 이번에 도구가 못 돌아 확인하지 못했습니다 (해결 아님)")
    if r.get("comparison"):
        c = r["comparison"]
        p(f"  지난 검사 대비: 새로 {c['new']} / 계속 {c['persisting']} / 해결 {c['resolved']} / 확인불가 {c['unverifiable']}")
    for f in r["findings"][:15]:
        loc = f["location"]
        where = f"{loc['file']}:{loc['start_line']}" if loc.get("start_line") else loc["file"]
        flags = f" [{', '.join(f['flags'])}]" if f.get("flags") else ""
        p(f"  - [{STATUS_LABEL_KO[f['status']]}][{f['severity']}] {f['title'][:70]} ({where}){flags}")
    if len(r["findings"]) > 15:
        p(f"  … 외 {len(r['findings']) - 15}건 (JSON 참고)")
    if r.get("suppressions"):
        p(f"  주의: 검사 예외 설정 파일 {len(r['suppressions'])}개 발견 (엔진은 무시하고 검사함)")


def _options(a) -> ScanOptions:
    tools = tuple(t.strip() for t in a.tools.split(",") if t.strip()) if a.tools else TOOLS
    bad = [t for t in tools if t not in TOOLS]
    if bad:
        raise SystemExit(f"알 수 없는 도구: {bad} (가능: {', '.join(TOOLS)})")
    registry = () if a.no_registry else tuple(a.with_registry or ())
    return ScanOptions(
        tools=tools,
        semgrep_registry=registry,
        semgrep_extra_configs=tuple(a.semgrep_config or ()),
        osv_offline=a.osv_offline,
        timeout_sec=a.timeout,
        include_raw=a.include_raw,
    )


def _fail_code(r: dict, level: str | None) -> int:
    if not level:
        return 0
    limit = SEVERITY_RANK[level]
    hit = any(f["status"] == CODE_ISSUE and SEVERITY_RANK[f["severity"]] <= limit for f in r["findings"])
    return 1 if hit else 0


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    ap = argparse.ArgumentParser(prog="python -m security_engine", description="보안엔진 (Semgrep · OSV-Scanner · Gitleaks)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scan", help="폴더 또는 저장소 검사")
    s.add_argument("target", nargs="?", help="검사할 폴더 (--repo-url을 쓰면 생략)")
    s.add_argument("--repo-url", help="https:// 공개 저장소 주소 (clone 후 검사, 끝나면 삭제)")
    s.add_argument("--ref", help="브랜치/태그 (--repo-url과 함께)")
    s.add_argument("--previous", help="직전 검사 결과 JSON (재검사 비교)")
    s.add_argument("-o", "--output", help="결과 JSON 저장 경로 (없으면 표준 출력)")
    s.add_argument("--tools", help="쉼표로 구분: osv,semgrep,gitleaks (기본: 전부)")
    s.add_argument("--with-registry", action="append", metavar="RULESET",
                   help="내부 비교용으로 Semgrep 레지스트리 룰셋 추가 (예: p/default). 라이선스상 서비스 결과에는 쓰지 말 것")
    s.add_argument("--no-registry", action="store_true", help="(기본값과 같음, 예전 명령 호환용)")
    s.add_argument("--semgrep-config", action="append", help="추가 Semgrep 규칙 파일/폴더")
    s.add_argument("--osv-offline", action="store_true", help="미리 받은 OSV DB만 사용 (인터넷 없이)")
    s.add_argument("--timeout", type=int, default=600, help="도구당 제한 시간(초), 기본 600")
    s.add_argument("--include-raw", action="store_true", help="스캐너 원본을 finding.raw에 포함")
    s.add_argument("--compact", action="store_true", help="JSON 한 줄로")
    s.add_argument("--quiet", action="store_true", help="요약 출력 안 함")
    s.add_argument("--fail-on", choices=SEVERITIES[:4], help="이 위험도 이상 열린 문제가 있으면 종료 코드 1")

    c = sub.add_parser("compare", help="저장된 두 결과 비교")
    c.add_argument("previous")
    c.add_argument("current")
    c.add_argument("-o", "--output")
    c.add_argument("--compact", action="store_true")
    c.add_argument("--quiet", action="store_true")

    li = sub.add_parser("llm-input", help="검사 결과 JSON → LLM 입력 꾸러미")
    li.add_argument("result", help="scan 결과 JSON")
    li.add_argument("-o", "--output")
    li.add_argument("--max-items", type=int, default=30)
    li.add_argument("--no-resolved", action="store_true", help="해결된 문제는 빼기")
    li.add_argument("--text", action="store_true", help="JSON 대신 프롬프트용 한국어 텍스트로")

    sub.add_parser("doctor", help="스캐너 설치 상태 확인")

    a = ap.parse_args(argv)

    if a.cmd == "doctor":
        info = doctor()
        for tool, v in info.items():
            mark = "OK " if v["path"] else "없음"
            eng = f"({v['engine']})" if v.get("engine") and v["engine"] != tool else ""
            print(f"{mark} {tool:<9} {eng:<11} {v['version'] or '':<10} {v['path'] or ''}")
        return 0 if all(v["path"] for v in info.values()) else 1

    if a.cmd == "llm-input":
        payload = build_llm_input(_load(a.result), max_items=a.max_items, include_resolved=not a.no_resolved)
        if a.text:
            text = render_llm_text(payload)
            if a.output:
                Path(a.output).write_text(text + "\n", encoding="utf-8")
            else:
                sys.stdout.write(text + "\n")
        else:
            _write(payload, a.output, False)
        return 0

    if a.cmd == "compare":
        r = compare_results(_load(a.current), _load(a.previous))
        _write(r, a.output, a.compact)
        if not a.quiet:
            _print_summary(r)
        return 0

    if not a.target and not a.repo_url:
        ap.error("검사할 폴더 또는 --repo-url이 필요합니다.")
    opts = _options(a)
    previous = _load(a.previous) if a.previous else None
    try:
        if a.repo_url:
            r = scan_repo(a.repo_url, previous, options=opts, ref=a.ref)
        else:
            r = scan(a.target, previous, options=opts)
    except (CloneError, NotADirectoryError) as exc:
        print(f"[보안엔진] 실패: {exc}", file=sys.stderr)
        return 3
    _write(r, a.output, a.compact)
    if not a.quiet:
        _print_summary(r)
    if r["status"] == "failed":
        return 3
    return _fail_code(r, a.fail_on)
