"""검사 API: 저장소 주소 → 보안엔진(clone·스캐너 4종) → LLM 입력 꾸러미.

- POST /api/scans        : 검사를 접수하고 바로 job_id를 돌려줍니다 (202). 검사는 서버에서 계속 돕니다.
- GET  /api/scans/{id}   : 진행 상태(queued·running·done·failed)와, 끝났으면 결과를 돌려줍니다.
  검사가 1~3분 걸려도 프록시·터널의 응답 제한(Cloudflare 약 100초)에 걸리지 않게 하려는 구조입니다.
- 결과를 DB에 저장하므로 API 재시작 후에도 같은 job_id로 조회할 수 있습니다.
- 동시에 도는 검사는 MAX_RUNNING건으로 제한합니다 (서버 보호).
보안엔진(security_engine/)은 저장소 루트에 있어서 경로를 한 번 추가합니다.
"""
import asyncio
import logging
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import DBAPIError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeout

from app.llm.engine_adapter import from_engine_item, from_engine_payload
from app.explain_jobs.auth import bearer, current_user
from app.explain_jobs.config import job_settings
from app.scan_store import ScanSchemaRequired, ScanStore

_ROOT = Path(__file__).resolve().parents[3]
if (_ROOT / "security_engine").is_dir() and str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

router = APIRouter(prefix="/scans", tags=["scans"])

MAX_RUNNING = 2
_slots = asyncio.Semaphore(MAX_RUNNING)
_tasks: set[asyncio.Task] = set()
logger = logging.getLogger(__name__)
PERSIST_RETRY_DELAYS = (1, 2)


async def scan_user(request: Request, credential: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if job_settings.llm_jobs_enabled:
        return await current_user(request, credential)
    return None


def get_scan_store(request: Request, user: Annotated[object, Depends(scan_user)]) -> ScanStore:
    # Authenticate before reflecting tables or revealing schema readiness.
    if request.app.state.scan_store is None:
        try:
            request.app.state.scan_store = ScanStore(request.app.state.scan_engine)
        except ScanSchemaRequired:
            raise HTTPException(503, "SCAN_SCHEMA_REQUIRED: apply db-schema.sql and migrations/052-scan-persistence.sql") from None
        except Exception:
            raise HTTPException(503, "SCAN_STORAGE_UNAVAILABLE") from None
    return request.app.state.scan_store


StoreDep = Annotated[ScanStore, Depends(get_scan_store)]
ActorDep = Annotated[object, Depends(scan_user)]


class ScanRequest(BaseModel):
    repo_url: str = Field(min_length=1, max_length=300, description="https://github.com/<owner>/<repo>")
    # 기존 응답 result를 보낼 수 있지만 scan_id만 조회 키로 사용합니다.
    # 비교 입력은 소유권/저장소를 확인한 서버 저장본에서 읽습니다.
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
    valid_items, validated, preview_errors = [], [], []
    for item in llm_input["items"]:
        try:
            finding = from_engine_item(item)
        except ValidationError:
            preview_errors.append({"fingerprint": item["id"], "code": "LLM_INPUT_INVALID"})
        else:
            valid_items.append(item)
            validated.append(finding)
    try:
        preview = from_engine_payload({**llm_input, "items": valid_items})
    except ValidationError:
        # A package group can exceed limits even when every member is valid.
        preview = validated
    findings = [f.model_dump(mode="json") for f in preview]
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
        "preview_errors": preview_errors,
    }


async def _fail_job(store, job_id, error):
    try:
        await run_in_threadpool(store.fail, job_id, error)
    except Exception:
        # No exception text: SQL connection details may include credentials.
        # The lease expires durably even when the failure cannot be written now.
        logger.error("Unable to persist scan failure for job %s; lease recovery will apply", job_id)


async def _heartbeat(store, job_id):
    while True:
        await asyncio.sleep(30)
        try:
            if not await run_in_threadpool(store.heartbeat, job_id):
                return
        except Exception:
            logger.error("Unable to renew scan lease for job %s", job_id)


async def drain_tasks():
    pending = set(_tasks)
    if not pending:
        return
    _, pending = await asyncio.wait(pending, timeout=10)
    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _retryable_storage_error(exc):
    if isinstance(exc, PoolTimeout):
        return True
    if exc.connection_invalidated or isinstance(exc, InterfaceError):
        return True
    if not isinstance(exc, OperationalError):
        return False
    sqlstate = getattr(exc.orig, "sqlstate", None)
    if sqlstate:
        return sqlstate.startswith(("08", "40", "53")) or sqlstate in {"57P01", "57P02", "57P03"}
    sqlite_code = getattr(exc.orig, "sqlite_errorcode", None)
    # SQLITE_BUSY, LOCKED, IOERR and CANTOPEN (including extended codes).
    return sqlite_code is None or sqlite_code & 255 in {5, 6, 10, 14}


async def _persist_result(store, job_id, result):
    for attempt in range(len(PERSIST_RETRY_DELAYS) + 1):
        try:
            await run_in_threadpool(store.complete, job_id, result)
            return
        except (DBAPIError, PoolTimeout) as exc:
            if not _retryable_storage_error(exc) or attempt == len(PERSIST_RETRY_DELAYS):
                raise
            # Retain this result in memory and retry only storage, never the scan.
            # A lost commit acknowledgement is safe because complete is idempotent.
            logger.warning("Retrying scan result storage for job %s (attempt %s)", job_id, attempt + 2)
            await asyncio.sleep(PERSIST_RETRY_DELAYS[attempt])


async def _worker(job_id: str, body: "ScanRequest", store: ScanStore) -> None:
    heartbeat = asyncio.create_task(_heartbeat(store, job_id))
    try:
        async with _slots:
            if not await run_in_threadpool(store.running, job_id):
                return
            result = await _run_scan(body)
            await _persist_result(store, job_id, result)
    except asyncio.CancelledError:
        await _fail_job(store, job_id, {"code": "SCAN_INTERRUPTED", "message": "검사 서버가 중단되었습니다. 다시 검사해 주세요."})
        raise
    except HTTPException as exc:
        await _fail_job(store, job_id, exc.detail)
    except Exception:  # Provider/SQL errors may contain credentials; expose only a stable code.
        await _fail_job(store, job_id, {"code": "SCAN_ERROR", "message": "검사 결과 처리 또는 저장에 실패했습니다."})
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


@router.post("", status_code=202)
async def start_scan(body: ScanRequest, response: Response, store: StoreDep, user: ActorDep):
    """검사를 접수합니다. 주소 형식은 바로 확인해서, 잘못된 주소는 기다리지 않고 400으로 돌려줍니다."""
    from security_engine.git import _ALLOWED_URL  # github.com 공개 저장소 주소만

    if not _ALLOWED_URL.match(body.repo_url.strip()):
        raise HTTPException(400, detail={"code": "CLONE_FAILED",
                                         "message": "https://github.com/<owner>/<repo> 형식의 공개 저장소 주소만 받을 수 있습니다."})
    if body.previous is not None:
        scan_id = body.previous.get("scan_id")
        previous = None
        if isinstance(scan_id, str) and len(scan_id) == 32:
            try:
                previous = await run_in_threadpool(store.previous_result, scan_id, body.repo_url.strip(), user)
            except Exception:
                raise HTTPException(503, "SCAN_STORAGE_UNAVAILABLE") from None
        if previous is None:
            raise HTTPException(404, "PREVIOUS_SCAN_NOT_FOUND")
        body = body.model_copy(update={"previous": previous})
    job_id = uuid.uuid4().hex
    response.headers["Cache-Control"] = "no-store"
    try:
        await run_in_threadpool(store.create, job_id, body.repo_url.strip(), user)
    except Exception:
        raise HTTPException(503, "SCAN_STORAGE_UNAVAILABLE") from None
    task = asyncio.create_task(_worker(job_id, body, store))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return {"job_id": job_id, "status": "queued"}


@router.get("/{job_id}")
async def get_scan(job_id: str, response: Response, store: StoreDep, user: ActorDep):
    response.headers["Cache-Control"] = "no-store"
    try:
        job = await run_in_threadpool(store.get, job_id, user)
    except Exception:
        raise HTTPException(503, "SCAN_STORAGE_UNAVAILABLE") from None
    if not job:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND", "message": "검사 작업을 찾을 수 없습니다."})
    return job
