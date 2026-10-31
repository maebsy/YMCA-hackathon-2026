"""스캐너마다 다른 결과 모양을 공통 형식으로 맞출 때 쓰는 도구 모음.

- 경로: 항상 검사 폴더 기준 상대 경로, '/' 구분 (Windows에서도 같은 지문이 나오게)
- 위험도: critical | high | medium | low | unknown
- 비밀값: 원래 값은 절대 결과에 남기지 않는다 (mask_secret, scrub)
"""
from __future__ import annotations

import re
from pathlib import Path, PurePosixPath

# ---------------------------------------------------------------- 경로


def rel_path(path: str | Path, root: Path) -> str:
    """스캐너가 준 경로(절대/상대 섞여 있음)를 root 기준 상대 경로(posix)로 바꾼다."""
    p = Path(path)
    if not p.is_absolute():
        p = (root / p)
    try:
        rel = p.resolve().relative_to(root.resolve())
        return PurePosixPath(*rel.parts).as_posix()
    except (ValueError, OSError):
        return Path(path).as_posix()


class SourceReader:
    """검사 폴더 안의 파일을 읽는다. 폴더 밖(심볼릭 링크 등)은 읽지 않는다."""

    MAX_BYTES = 2_000_000

    def __init__(self, root: Path):
        self.root = root.resolve()
        self._cache: dict[str, list[str] | None] = {}
        self._bytes: dict[str, bytes | None] = {}

    def _safe(self, rel: str) -> Path | None:
        try:
            p = (self.root / rel).resolve()
            p.relative_to(self.root)  # 폴더 밖이면 ValueError
        except (ValueError, OSError):
            return None
        if not p.is_file() or p.stat().st_size > self.MAX_BYTES:
            return None
        return p

    def exists(self, rel: str) -> bool:
        try:
            p = (self.root / rel).resolve()
            p.relative_to(self.root)
            return p.exists()
        except (ValueError, OSError):
            return False

    def raw(self, rel: str) -> bytes | None:
        if rel not in self._bytes:
            p = self._safe(rel)
            self._bytes[rel] = p.read_bytes() if p else None
        return self._bytes[rel]

    def lines(self, rel: str) -> list[str] | None:
        if rel not in self._cache:
            data = self.raw(rel)
            self._cache[rel] = (
                data.decode("utf-8", errors="replace").splitlines() if data is not None else None
            )
        return self._cache[rel]

    def line(self, rel: str, lineno: int | None) -> str:
        lines = self.lines(rel)
        if not lines or not lineno or lineno < 1 or lineno > len(lines):
            return ""
        return lines[lineno - 1]

    def span(self, rel: str, start: int | None, end: int | None) -> str:
        lines = self.lines(rel)
        if not lines or not start:
            return ""
        end = end or start
        return "\n".join(lines[start - 1:end])

    def context(self, rel: str, start: int | None, end: int | None, around: int) -> dict | None:
        lines = self.lines(rel)
        if not lines or not start:
            return None
        end = end or start
        first = max(1, start - around)
        last = min(len(lines), end + around)
        return {"start_line": first, "lines": lines[first - 1:last]}


# ---------------------------------------------------------------- 비밀값


def mask_secret(secret: str) -> str:
    """'sk_live_abcd...' -> 'sk_l********'. 짧은 값은 앞부분도 안 보여준다."""
    if not secret:
        return ""
    head = secret[:4] if len(secret) >= 12 else ""
    return head + "*" * 8


def secret_variants(secret: str) -> list[str]:
    """가릴 대상 목록: 비밀값 전체 + 여러 줄이면 줄마다 따로.

    개인키처럼 여러 줄인 비밀값은 파일의 줄바꿈(Windows \\r\\n / 리눅스 \\n)이 스캐너 보고와 달라
    통째로는 안 찾아질 수 있다. 그래서 줄 하나하나(6글자 이상)도 따로 가린다.
    """
    if not secret:
        return []
    out = {secret}
    for line in secret.replace("\r", "\n").split("\n"):
        line = line.strip()
        if len(line) >= 6:
            out.add(line)
    return sorted(out, key=len, reverse=True)


def scrub(text, secrets: list[str]):
    """문자열(또는 dict/list 안의 모든 문자열)에서 비밀값을 가린다."""
    if not secrets or text is None:
        return text
    if isinstance(text, str):
        for s in secrets:
            if s and s in text:
                text = text.replace(s, mask_secret(s))
        return text
    if isinstance(text, list):
        return [scrub(t, secrets) for t in text]
    if isinstance(text, dict):
        return {k: scrub(v, secrets) for k, v in text.items()}
    return text


# ---------------------------------------------------------------- 위험도

_OSV_LABEL = {
    "CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium", "MEDIUM": "medium", "LOW": "low",
}
_SEMGREP_LEVEL = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}


def severity_from_osv_label(label: str | None) -> str | None:
    return _OSV_LABEL.get((label or "").upper())


def severity_from_cvss(score) -> str | None:
    """'7.4' 같은 CVSS 기본 점수 -> 위험도."""
    try:
        s = float(score)
    except (TypeError, ValueError):
        return None
    if s >= 9.0:
        return "critical"
    if s >= 7.0:
        return "high"
    if s >= 4.0:
        return "medium"
    if s > 0:
        return "low"
    return None


def severity_from_semgrep(level: str | None, metadata: dict | None) -> str:
    meta = metadata or {}
    override = str(meta.get("engine_severity", "")).lower()
    if override in ("critical", "high", "medium", "low"):
        return override
    return _SEMGREP_LEVEL.get((level or "").upper(), "unknown")


# ---------------------------------------------------------------- 기타


def normalize_code(text: str) -> str:
    """공백·줄바꿈을 모두 뺀 코드. 'eval( x )'와 'eval(x)'를 같은 코드로 본다 (자동 정렬·들여쓰기 변화 무시)."""
    return re.sub(r"\s+", "", text or "")


def normalize_cwe(value) -> list[str]:
    """'CWE-79: Improper ...', ['CWE-79'], 'CWE-79' -> ['CWE-79']"""
    items = value if isinstance(value, list) else [value] if value else []
    out = []
    for item in items:
        m = re.search(r"CWE-\d+", str(item))
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


def first_sentence(text: str, limit: int = 120) -> str:
    text = (text or "").strip().replace("\n", " ")
    m = re.search(r"(.+?[.!?。])(\s|$)", text)
    s = m.group(1) if m else text
    return s if len(s) <= limit else s[: limit - 1] + "…"


# 정식 출시 뒤에 붙는 표시 (PyPI '.post1', Maven '-sp1' 등). 이것만 정식 버전보다 높게 본다
_POST_RELEASE = re.compile(r"(?i)^(post|rev|r|p|sp|patch)\d*$")
_VERSION_CORE = re.compile(r"(\d+(?:\.\d+)*)(.*)")
# 사전 출시 꼬리표의 순서 (PEP 440: dev < a < b < rc). 그 밖의 글자는 이들 뒤에서 글자 순으로 비교한다
_PRE_RANK = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "c": 3, "rc": 3, "pre": 3, "preview": 3}


def version_key(v: str) -> tuple:
    """버전 비교용 키. SemVer 규칙을 따르고 PyPI·Maven의 흔한 꼬리표도 다룬다 (#92).

    - 숫자 부분은 숫자로 비교하고 끝의 .0은 무시한다: 1.2 == 1.2.0 < 1.2.1
    - 사전 출시(-beta.1, -rc.2, rc1, .dev0)는 같은 숫자의 정식 출시보다 낮다: 1.2.3-beta.1 < 1.2.3
    - 사전 출시끼리는 SemVer처럼 점으로 나눈 조각을 비교한다(숫자 < 글자, 짧은 쪽이 낮음)
    - 정식 출시 뒤 표시(.post1, -sp1)는 정식 출시보다 높다
    - 맨 앞 v와 빌드 정보(+...)는 무시한다
    """
    s = str(v).strip().lstrip("vV").split("+", 1)[0]
    m = _VERSION_CORE.match(s)
    if not m:
        return ((), 0, ((1, 0, s.lower()),))
    core = [int(x) for x in m[1].split(".")]
    while len(core) > 1 and core[-1] == 0:
        core.pop()
    rest = m[2].lstrip(".-_")
    if not rest:
        return (tuple(core), 1, ())
    # 'rc1'·'beta.2'·'dev0' 모두 글자와 숫자를 나눠 비교한다
    pieces = [p for chunk in re.split(r"[.\-_]", rest) for p in re.findall(r"\d+|[A-Za-z]+", chunk)]
    ids = tuple((0, int(p), "") if p.isdigit() else (1, _PRE_RANK.get(p.lower(), 9), p.lower()) for p in pieces)
    phase = 2 if _POST_RELEASE.match(re.sub(r"[.\-_]", "", rest)) else 0
    return (tuple(core), phase, ids)


def pick_fix_version(current: str | None, fixed: list[str]) -> str | None:
    """현재 버전보다 높은 '고친 버전' 중 가장 낮은 것 (가장 작게 올리는 버전).

    현재 버전보다 높은 후보가 없으면 None이다. 낮은 버전을 '업그레이드'로 안내하지 않는다 (#92).
    현재 버전을 모르면 가장 높은 후보를 돌려준다.
    """
    if not fixed:
        return None
    cands = sorted(set(fixed), key=version_key)
    if current:
        now = version_key(current)
        higher = [f for f in cands if version_key(f) > now]
        return higher[0] if higher else None
    return cands[-1]
