"""'같은 문제'를 알아보기 위한 지문(fingerprint).

재검사 때 지난번 결과와 이번 결과를 지문으로 맞춰서 새로 생김/계속 있음/해결됨을 판단한다.
줄 번호는 지문에 넣지 않는다 (위에 코드 한 줄만 추가해도 다른 문제로 보이면 안 되므로).

| 도구 | 지문 재료 |
|---|---|
| osv | 생태계 + 패키지 이름 + 취약점 대표 ID(CVE 우선) + lockfile 경로 |
| semgrep | 규칙 ID + 파일 경로 + 걸린 코드(공백 정리) |
| gitleaks | 규칙 ID + 파일 경로 + 비밀값의 해시 (값 자체는 저장 안 함) |

같은 파일에 똑같은 코드가 두 번 있으면 '#2', '#3'을 붙여 구분한다.
"""
from __future__ import annotations

import hashlib
import hmac
import os

# 비밀값 해시에 섞는 값. 운영에서는 환경 변수로 바꿔서 해시만 보고 원래 값을 추측하지 못하게 한다.
_DEFAULT_SALT = "ymca-security-engine"


def make(tool: str, *parts: str) -> str:
    joined = "\x1f".join(str(p) for p in parts)
    digest = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:24]
    return f"{tool}:{digest}"


def secret_hash(secret: str) -> str:
    salt = os.environ.get("SECURITY_ENGINE_FP_SALT", _DEFAULT_SALT).encode("utf-8")
    return hmac.new(salt, secret.encode("utf-8"), hashlib.sha256).hexdigest()[:32]


def make_unique(findings: list[dict]) -> None:
    """같은 지문이 여러 개면 위치 순서대로 #2, #3 …을 붙인다 (제자리 수정)."""
    def pos(f):
        loc = f.get("location") or {}
        return (loc.get("file") or "", loc.get("start_line") or 0)

    seen: dict[str, int] = {}
    for f in sorted(findings, key=pos):
        fp = f["fingerprint"]
        seen[fp] = seen.get(fp, 0) + 1
        if seen[fp] > 1:
            f["fingerprint"] = f"{fp}#{seen[fp]}"
