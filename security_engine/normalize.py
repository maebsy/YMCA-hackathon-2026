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


# ── 버전 비교 (#92) ──
# 생태계마다 규칙이 달라 한 가지 규칙으로 비교하면 낮은 버전을 '업그레이드'로 안내할 수 있다.
# 그래서 OSV 생태계 이름으로 비교기를 고르고, 그 규칙으로 읽을 수 없는 버전은 None(비교 불가)으로 둔다.
# 비교 불가한 버전은 추천에 쓰지 않는다 (추측해서 올리라고 하지 않음).
SEMVER_ECOSYSTEMS = frozenset({"npm", "Go", "crates.io", "Hex", "Pub", "SwiftURL"})
PEP440_ECOSYSTEMS = frozenset({"PyPI"})
MAVEN_ECOSYSTEMS = frozenset({"Maven"})

_SEMVER = re.compile(
    r"^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
_PEP440 = re.compile(
    r"^v?(?:(\d+)!)?(\d+(?:\.\d+)*)"
    r"(?:[-_.]?(a|alpha|b|beta|rc|c|pre|preview)[-_.]?(\d*))?"
    r"(?:-(\d+)|[-_.]?(?:post|rev|r)[-_.]?(\d*))?"
    r"(?:[-_.]?(dev)[-_.]?(\d*))?"
    r"(?:\+[a-z0-9]+(?:[-_.][a-z0-9]+)*)?$",
    re.IGNORECASE,
)
_PEP440_PRE = {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2, "c": 2, "pre": 2, "preview": 2}
_MAVEN = re.compile(r"^(\d+(?:\.\d+)*)(?:[-.]?([A-Za-z]+)[-.]?(\d*))?$")
# Maven 한정자 순서: alpha < beta < milestone < rc(cr) < snapshot < 정식(ga·final·release) < sp
_MAVEN_QUALIFIER = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "milestone": 2, "m": 2, "rc": 3, "cr": 3,
                    "snapshot": 4, "": 5, "ga": 5, "final": 5, "release": 5, "sp": 6}
_NUMERIC = re.compile(r"^v?(\d+(?:\.\d+)*)$")


def _trim(parts: list[int]) -> tuple:
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _semver_key(v: str) -> tuple | None:
    """SemVer 2.0.0 §11: 사전 출시는 정식보다 낮고, 점으로만 나눈 식별자를 비교한다.
    숫자로만 된 식별자는 숫자로, 나머지는 대소문자를 구분해 ASCII 순서로 비교한다(alpha10 < alpha2)."""
    m = _SEMVER.match(v)
    if not m:
        return None
    pre = m[4]
    if pre is None:
        return (int(m[1]), int(m[2]), int(m[3]), 1, ())
    ids = tuple((0, int(p), "") if p.isdigit() else (1, 0, p) for p in pre.split("."))
    return (int(m[1]), int(m[2]), int(m[3]), 0, ids)


def _pep440_key(v: str) -> tuple | None:
    """PEP 440: epoch(1!) → 숫자 → dev < a < b < rc < 정식 < post. 지역 버전(+...)은 무시한다."""
    m = _PEP440.match(v)
    if not m:
        return None
    epoch = int(m[1] or 0)
    release = _trim([int(x) for x in m[2].split(".")])
    pre_l, pre_n = m[3], m[4]
    post_n = m[5] if m[5] is not None else m[6]
    dev = m[7] is not None
    if pre_l:
        pre = (1, _PEP440_PRE[pre_l.lower()], int(pre_n or 0))
    elif post_n is None and dev:
        pre = (0,)  # 1.0.dev0 은 1.0a1 보다도 앞선다
    else:
        pre = (2,)  # 사전 출시 아님
    post = (1, int(post_n or 0)) if post_n is not None else (0,)
    dev_key = (0, int(m[8] or 0)) if dev else (1,)
    return (epoch, release, pre, post, dev_key)


def _maven_key(v: str) -> tuple | None:
    m = _MAVEN.match(v)
    if not m:
        return None
    qualifier = (m[2] or "").lower()
    if qualifier not in _MAVEN_QUALIFIER:
        return None  # 모르는 한정자는 비교하지 않는다
    return (_trim([int(x) for x in m[1].split(".")]), _MAVEN_QUALIFIER[qualifier], int(m[3] or 0))


def _numeric_key(v: str) -> tuple | None:
    m = _NUMERIC.match(v)
    return (_trim([int(x) for x in m[1].split(".")]),) if m else None


def version_key(v: str, ecosystem: str | None = None) -> tuple | None:
    """생태계 규칙에 맞는 비교 키. 그 규칙으로 읽을 수 없으면 None(비교 불가).

    - npm·Go·crates.io 등: SemVer 2.0.0 (사전 출시는 같은 숫자의 정식보다 항상 낮음, -post1 포함)
    - PyPI: PEP 440 (epoch, dev/a/b/rc, post)
    - Maven: 알려진 한정자(alpha·beta·milestone·rc·snapshot·sp)만
    - 그 밖·생태계 모름: 숫자로만 된 버전(1.2.3)만
    """
    s = str(v or "").strip()
    if not s:
        return None
    if ecosystem in SEMVER_ECOSYSTEMS:
        return _semver_key(s)
    if ecosystem in PEP440_ECOSYSTEMS:
        return _pep440_key(s)
    if ecosystem in MAVEN_ECOSYSTEMS:
        return _maven_key(s)
    return _numeric_key(s)


def pick_fix_version(current: str | None, fixed: list[str], ecosystem: str | None = None) -> str | None:
    """현재 버전보다 높은 '고친 버전' 중 가장 낮은 것 (가장 작게 올리는 버전).

    - 현재 버전보다 높은 후보가 없으면 None. 낮은 버전을 '업그레이드'로 안내하지 않는다 (#92).
    - 그 생태계 규칙으로 읽을 수 없는 후보(커밋 해시 등)는 빼고, 현재 버전을 읽을 수 없으면 추천하지 않는다.
    - 현재 버전을 모르면 읽을 수 있는 후보 중 가장 높은 것을 돌려준다.
    """
    keyed = sorted((k, f) for f in set(fixed or []) if (k := version_key(f, ecosystem)) is not None)
    if not keyed:
        return None
    if current:
        now = version_key(current, ecosystem)
        if now is None:
            return None
        higher = [f for k, f in keyed if k > now]
        return higher[0] if higher else None
    return keyed[-1][1]
