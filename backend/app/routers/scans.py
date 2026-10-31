"""검사 API: 저장소 주소 → 보안엔진(clone·스캐너 4종) → LLM 입력 꾸러미.

- POST /api/scans        : 검사를 접수하고 바로 job_id를 돌려줍니다 (202). 검사는 서버에서 계속 돕니다.
- GET  /api/scans/{id}   : 진행 상태(queued·running·done·failed)와, 끝났으면 결과를 돌려줍니다.
  검사가 1~3분 걸려도 프록시·터널의 응답 제한(Cloudflare 약 100초)에 걸리지 않게 하려는 구조입니다.
- 결과는 서버 메모리에만 잠시 둡니다 (최근 50건, 재시작하면 사라짐). DB 저장은 추후 개발 예정입니다.
- 동시에 도는 검사는 MAX_RUNNING건으로 제한합니다 (서버 보호).
보안엔진(security_engine/)은 저장소 루트에 있어서 경로를 한 번 추가합니다.
"""
import asyncio
import sys
import uuid
from collections import OrderedDict
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.llm.engine_adapter import from_engine_payload

_ROOT = Path(__file__).resolve().parents[3]
if (_ROOT / "security_engine").is_dir() and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

router = APIRouter(prefix="/scans", tags=["scans"])

MAX_RUNNING = 2
MAX_KEPT = 50
_jobs: "OrderedDict[str, dict]" = OrderedDict()
_slots = asyncio.Semaphore(MAX_RUNNING)


class ScanRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=300, description="https://github.com/<owner>/<repo>")
    # 재검사: 같은 저장소의 직전 검사 결과(응답의 result)를 그대로 넣으면 새로/계속/해결을 비교합니다
    previous: dict | None = None


def _report_scan(result: dict, llm_input: dict, repo_url: str) -> dict:
    """리포트 API(/api/reports/plain)의 scan 칸. 72시간 타이머는 열린 문제의 첫 발견 시각에서 시작합니다."""
    findings = result.get("findings", [])
    open_ = [f for f in findings if f.get("status") == "code_issue"]
    seen = sorted(f.get("first_seen") for f in (open_ or findings) if f.get("first_seen"))
    is_rescan = result.get("comparison") is not None
    return {
        "site_name": repo_url.removeprefix("https://github.com/").rstrip("/") or repo_url,
        "repo": repo_url,
        "scanned_at": result["scanned_at"],
        "detected_at": seen[0] if seen else None,
        # 재검사에서 열린 문제가 0건이면 '해결 확인' 시각 (리포트가 완료 리포트가 되고 타이머가 멈춤)
        "resolved_at": result["scanned_at"] if is_rescan and not open_ else None,
        "not_checked": [
            {"tool": n.get("tool", ""), "category": n.get("category"), "reason": n.get("reason", "")}
            for n in llm_input.get("not_checked", [])
        ][:20],
    }


async def _run_scan(body: "ScanRequest") -> dict:
    try:
        from security_engine import CloneError, build_llm_input, scan_repo
    except ImportError as exc:  # 엔진 폴더가 없는 배포본
        raise HTTPException(503, detail={"code": "ENGINE_UNAVAILABLE", "message": str(exc)}) from exc
    repo_url = body.repo_url.strip()
    prev = body.previous
    if prev and (prev.get("target") or {}).get("repo_url") != repo_url:
        prev = None  # 다른 저장소의 결과와는 비교하지 않습니다
    try:
        result = await run_in_threadpool(scan_repo, repo_url, prev)
    except CloneError as exc:
        raise HTTPException(400, detail={"code": "CLONE_FAILED", "message": str(exc)}) from exc
    llm_input = build_llm_input(result, max_items=50)
    findings = [f.model_dump(mode="json") for f in from_engine_payload(llm_input)]
    return {
        "scan_id": result["scan_id"],
        "status": result["status"],
        "duration_sec": result["duration_sec"],
        "coverage": {t: {k: c.get(k) for k in ("status", "engine", "count", "message", "duration_sec")}
                     for t, c in result["coverage"].items()},
        "summary": result["summary"],
        "comparison": result.get("comparison"),
        "report_scan": _report_scan(result, llm_input, repo_url),
        # 다음 재검사 때 previous로 그대로 돌려보내는 전체 결과 (비밀값은 엔진에서 이미 가림)
        "result": result,
        "llm_input": llm_input,
        "findings": findings[:50],
    }


async def _worker(job_id: str, body: "ScanRequest") -> None:
    job = _jobs[job_id]
    async with _slots:
        job["status"] = "running"
        try:
            job["result"] = await _run_scan(body)
            job["status"] = "done"
        except HTTPException as exc:
            job["status"], job["error"] = "failed", exc.detail
        except Exception as exc:  # 검사 하나가 터져도 서버는 계속
            job["status"], job["error"] = "failed", {"code": "SCAN_ERROR", "message": f"{type(exc).__name__}: {exc}"}


@router.post("", status_code=202)
async def start_scan(body: ScanRequest):
    """검사를 접수합니다. 주소 형식은 바로 확인해서, 잘못된 주소는 기다리지 않고 400으로 돌려줍니다."""
    from security_engine.git import _ALLOWED_URL  # github.com 공개 저장소 주소만

    if not _ALLOWED_URL.match(body.repo_url.strip()):
        raise HTTPException(400, detail={"code": "CLONE_FAILED",
                                         "message": "https://github.com/<owner>/<repo> 형식의 공개 저장소 주소만 받을 수 있습니다."})
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"job_id": job_id, "status": "queued", "repo_url": body.repo_url.strip(), "result": None, "error": None}
    while len(_jobs) > MAX_KEPT:
        _jobs.popitem(last=False)
    asyncio.create_task(_worker(job_id, body))
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}")
async def get_scan(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "검사 작업을 찾을 수 없습니다 (서버 재시작 등)."})
    return job
