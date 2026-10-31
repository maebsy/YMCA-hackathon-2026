"""추천 업그레이드 버전을 OSV에 다시 물어, 그 버전에도 알려진 취약점이 남아 있는지 확인한다 (#109).

OSV가 알려 준 '고친 버전'은 그 취약점 하나가 고쳐진 버전일 뿐이다. 추천 버전에 다른 취약점이 또 있을 수 있어
https://api.osv.dev/v1/querybatch 로 (생태계, 패키지, 추천 버전)을 한 번에 조회한다.

- 결과는 각 finding의 remediation.target_check 에 남긴다:
  {"status": "clean" | "vulnerable" | "unknown", "remaining": [취약점 ID...], "remaining_count": N, "reason": ...}
  clean = OSV 기준 알려진 취약점 없음(안전 보장은 아님), unknown = 조회 실패·생략 (안전하다고 단정하지 않음)
- 오프라인 모드(--osv-offline)나 osv_recheck=False 면 조회하지 않고 unknown 으로 둔다.
- 조회 수 상한(MAX_QUERIES), 시간 제한(TIMEOUT_SEC), 같은 버전 결과 캐시(CACHE_TTL_SEC)를 둔다.
"""
from __future__ import annotations

import json
import threading
import time
import urllib.request
from typing import Callable

from .models import CODE_ISSUE, ScanOptions

QUERYBATCH_URL = "https://api.osv.dev/v1/querybatch"
MAX_QUERIES = 200        # 검사 1건에서 다시 조회할 (패키지, 버전) 최대 개수
TIMEOUT_SEC = 15         # 조회 전체 시간 제한
CACHE_TTL_SEC = 6 * 3600  # 같은 (생태계, 패키지, 버전) 결과를 다시 쓰는 시간
MAX_LISTED = 20          # remaining 에 남길 ID 개수

Key = tuple[str, str, str]
Query = Callable[[list[Key]], list[list[str]]]

_cache: dict[Key, tuple[float, list[str]]] = {}
_lock = threading.Lock()


def _http_query(keys: list[Key]) -> list[list[str]]:
    """OSV querybatch. 쿼리 순서대로 취약점 ID 목록을 돌려준다. 실패하면 예외."""
    body = json.dumps({"queries": [{"package": {"ecosystem": e, "name": n}, "version": v} for e, n, v in keys]})
    request = urllib.request.Request(QUERYBATCH_URL, data=body.encode(), method="POST",
                                     headers={"content-type": "application/json", "user-agent": "72hours-security-engine"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as response:
        data = json.load(response)
    results = data.get("results")
    if not isinstance(results, list) or len(results) != len(keys):
        raise ValueError("OSV querybatch 응답 개수가 요청과 다릅니다")
    out = []
    for r in results:
        if (r or {}).get("next_page_token"):
            raise ValueError("OSV querybatch 결과가 잘렸습니다")  # 일부만 보고 '안전'이라 하지 않는다
        out.append(sorted({v["id"] for v in (r or {}).get("vulns") or [] if v.get("id")}))
    return out


def _unknown(reason: str) -> dict:
    return {"status": "unknown", "remaining": [], "remaining_count": None, "reason": reason}


def _check(ids: list[str]) -> dict:
    if not ids:
        return {"status": "clean", "remaining": [], "remaining_count": 0, "reason": None}
    return {"status": "vulnerable", "remaining": ids[:MAX_LISTED], "remaining_count": len(ids), "reason": None}


def recheck(findings: list[dict], opts: ScanOptions | None = None, query: Query | None = None,
            now: Callable[[], float] = time.monotonic) -> None:
    """findings 의 추천 버전을 OSV에 다시 조회해 remediation.target_check 를 채운다 (제자리 수정)."""
    opts = opts or ScanOptions()
    targets: dict[Key, list[dict]] = {}
    for f in findings:
        rem, pkg = f.get("remediation") or {}, f.get("package") or {}
        if f.get("tool") != "osv" or f.get("status") != CODE_ISSUE or not rem.get("target_version"):
            continue
        targets.setdefault((pkg.get("ecosystem", ""), pkg.get("name", ""), rem["target_version"]), []).append(f)
    if not targets:
        return

    if opts.osv_offline or not opts.osv_recheck:
        reason = "오프라인 검사라 추천 버전을 다시 조회하지 않았습니다" if opts.osv_offline else "추천 버전 재조회를 껐습니다"
        for fs in targets.values():
            for f in fs:
                f["remediation"]["target_check"] = _unknown(reason)
        return

    results: dict[Key, dict] = {}
    pending: list[Key] = []
    with _lock:
        for key in targets:
            hit = _cache.get(key)
            if hit and now() - hit[0] < CACHE_TTL_SEC:
                results[key] = _check(hit[1])
            else:
                pending.append(key)
    over = pending[MAX_QUERIES:]
    pending = pending[:MAX_QUERIES]
    for key in over:
        results[key] = _unknown(f"조회 상한({MAX_QUERIES}개)을 넘어 확인하지 못했습니다")
    if pending:
        try:
            answers = (query or _http_query)(pending)
            if len(answers) != len(pending):
                raise ValueError("응답 개수 불일치")
        except Exception:  # 네트워크·형식 오류: 안전하다고 단정하지 않는다
            for key in pending:
                results[key] = _unknown("OSV에 추천 버전을 다시 조회하지 못했습니다")
        else:
            with _lock:
                for key, ids in zip(pending, answers):
                    _cache[key] = (now(), list(ids))
                    results[key] = _check(list(ids))

    for key, fs in targets.items():
        for f in fs:
            f["remediation"]["target_check"] = dict(results[key], remaining=list(results[key]["remaining"]))


def clear_cache() -> None:
    with _lock:
        _cache.clear()
