"""검사 API: 저장소 주소 → 보안엔진(clone·스캐너 4종) → LLM 입력 꾸러미.

- POST /api/scans        : 검사를 접수하고 바로 job_id를 돌려줍니다 (202). 검사는 서버에서 계속 돕니다.
- GET  /api/scans/{id}   : 진행 상태(queued·running·done·failed)와, 끝났으면 결과를 돌려줍니다.
  검사가 1~3분 걸려도 프록시·터널의 응답 제한(Cloudflare 약 100초)에 걸리지 않게 하려는 구조입니다.
- 결과는 서버 메모리에만 잠시 둡니다 (최근 50건, 재시작하면 사라짐). DB 저장은 추후 개발 예정입니다.
- 동시에 도는 검사는 MAX_RUNNING건, 기다리는 검사까지 합쳐 MAX_ACTIVE건으로 제한합니다 (넘으면 429).
- SCAN_REQUIRE_AUTH=true 이면 Supabase 로그인(Bearer) 사용자만 검사를 걸고, 자기 검사만 조회합니다 (#53).
보안엔진(security_engine/)은 저장소 루트에 있어서 경로를 한 번 추가합니다.
"""
import asyncio
import logging
import sys
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.explain_jobs.auth import bearer, current_user
from app.explain_jobs.config import job_settings
from app.llm.engine_adapter import from_engine_payload

_ROOT = Path(__file__).resolve().parents[3]
if (_ROOT / "security_engine").is_dir() and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

log = logging.getLogger(__name__)
router = APIRouter(prefix="/scans", tags=["scans"])

MAX_RUNNING = 2
MAX_ACTIVE = 10  # 실행 중 + 대기 중. 넘으면 429로 거절해 대기열이 끝없이 쌓이지 않게 합니다
MAX_KEPT = 50  # 끝난 검사 결과를 보관하는 건수. 진행 중인 검사는 밀어내지 않습니다
_jobs: "OrderedDict[str, dict]" = OrderedDict()
_slots = asyncio.Semaphore(MAX_RUNNING)
_tasks: set[asyncio.Task] = set()  # 작업 참조를 보관해 실행 중에 가비지 컬렉션되지 않게 합니다


def _active() -> int:
    return sum(job["status"] in ("queued", "running") for job in _jobs.values())


def _evict_finished() -> None:
    finished = [k for k, job in _jobs.items() if job["status"] in ("done", "failed")]
    for k in finished[: max(0, len(_jobs) - MAX_KEPT)]:
        del _jobs[k]


async def scan_user(
    request: Request,
    credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> UUID | None:
    """인증을 켰으면 로그인 사용자 ID, 껐으면(데모) None."""
    if not job_settings.scan_require_auth:
        return None
    return await current_user(request, credential)


ScanUserDep = Annotated[UUID | None, Depends(scan_user)]


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
    except ImportError:  # 엔진 폴더가 없는 배포본
        raise _engine_unavailable() from None
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
        except Exception:  # 검사 하나가 터져도 서버는 계속. 원문(경로 등)은 서버 로그에만 남깁니다
            log.exception("scan %s failed", job_id)
            job["status"], job["error"] = "failed", {"code": "SCAN_ERROR", "message": "검사 중 서버 오류가 났습니다. 잠시 뒤 다시 시도해 주세요."}
    _evict_finished()


def _engine_unavailable() -> HTTPException:
    return HTTPException(503, detail={"code": "ENGINE_UNAVAILABLE", "message": "이 서버에는 보안엔진이 설치되어 있지 않습니다."})


@router.post("", status_code=202)
async def start_scan(body: ScanRequest, user: ScanUserDep):
    """검사를 접수합니다. 주소 형식은 바로 확인해서, 잘못된 주소는 기다리지 않고 400으로 돌려줍니다."""
    try:
        from security_engine.git import _ALLOWED_URL  # github.com 공개 저장소 주소만
    except ImportError:  # 엔진 폴더가 없는 배포본 (Compose 이미지)
        raise _engine_unavailable() from None

    if not _ALLOWED_URL.match(body.repo_url.strip()):
        raise HTTPException(400, detail={"code": "CLONE_FAILED",
                                         "message": "https://github.com/<owner>/<repo> 형식의 공개 저장소 주소만 받을 수 있습니다."})
    if _active() >= MAX_ACTIVE:
        raise HTTPException(429, detail={"code": "SCAN_QUEUE_FULL", "message": "검사가 몰려 있습니다. 1~2분 뒤 다시 시도해 주세요."},
                            headers={"Retry-After": "60"})
    job_id = uuid.uuid4().hex
    _jobs[job_id] = {"job_id": job_id, "status": "queued", "repo_url": body.repo_url.strip(), "result": None, "error": None,
                     "owner": user}
    _evict_finished()
    task = asyncio.create_task(_worker(job_id, body))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}")
async def get_scan(job_id: str, user: ScanUserDep):
    job = _jobs.get(job_id)
    if not job or job["owner"] != user:  # 남의 검사는 있는지조차 알려 주지 않습니다
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "검사 작업을 찾을 수 없습니다 (서버 재시작 등)."})
    return {k: v for k, v in job.items() if k != "owner"}
