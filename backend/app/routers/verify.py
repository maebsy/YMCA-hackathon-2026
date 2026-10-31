"""실검증 API: 데모 과녁에서 '수정 전 공격 성공 → 수정 후 차단 + 기능 테스트 통과'를 실제로 실행해 확인합니다.

- POST /api/verify        : 실검증을 접수하고 바로 job_id를 돌려줍니다 (202).
- GET  /api/verify/{id}   : 진행 상태(queued·running·done·failed)와, 끝났으면 result(VerifyResult)를 돌려줍니다.
  검사 API(scans.py)와 같은 "접수 → 작업 번호 → 조회" 방식이고 로그인 규칙도 같습니다.

지금은 우리 데모 과녁(demo-vulnerable-site)만 받습니다.
- 공격 정의(verify/attacks.json)와 기준 수정본(verify/fix/)은 서버에 있는 파일에서 읽고, 요청으로는 코드·경로·명령을
  받지 않습니다. 데모 과녁은 우리 코드라 Docker가 없으면 격리 없는 LocalSandbox로 돌기 때문입니다(trusted=True).
  요청으로 수정본을 받으면 그 코드가 서버에서 격리 없이 실행됩니다.
- 사용자 저장소 실검증은 Red·Blue 출력 연결(#97)과 서버 Docker가 있어야 하고, 그때는 trusted=False로 Docker만 씁니다.
"""
import difflib
import json
import shutil
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict

from app.routers.scans import ActorDep
from app.verify import AttackSpec, Patch, VerifyRequest, verify
from app.verify.jobs import VerifyJobs
from app.verify.sandbox import docker_available

DEMO = Path(__file__).resolve().parents[3] / "demo-vulnerable-site"

router = APIRouter(prefix="/verify", tags=["verify"])


class VerifyStart(BaseModel):
    # repo_dir·patch·start_cmd 같은 값을 보내면 조용히 무시하지 않고 422로 거절합니다
    model_config = ConfigDict(extra="forbid")
    target: Literal["demo"] = "demo"  # 지금은 우리 데모 과녁만


def get_verify_jobs(request: Request) -> VerifyJobs:
    return request.app.state.verify_jobs


JobsDep = Annotated[VerifyJobs, Depends(get_verify_jobs)]


def _unavailable(message: str) -> HTTPException:
    return HTTPException(503, detail={"code": "VERIFY_UNAVAILABLE", "message": message})


def _runtime_ready() -> bool:
    # Docker가 있으면 Docker로, 없으면 데모 과녁에 한해 이 서버의 Node로 실행합니다 (sandbox.pick_sandbox)
    return docker_available() or bool(shutil.which("node") and shutil.which("npm"))


def _demo_inputs() -> tuple[list[AttackSpec], Patch]:
    spec = json.loads((DEMO / "verify" / "attacks.json").read_text(encoding="utf-8"))
    fix_dir = DEMO / "verify" / "fix"
    files = {p.relative_to(fix_dir).as_posix(): p.read_text(encoding="utf-8")
             for p in sorted(fix_dir.rglob("*")) if p.is_file()}
    return [AttackSpec(**a) for a in spec["attacks"]], Patch(files=files)


def _diff(patch: Patch) -> str:
    """화면에 보여 줄 수정 내용 (원본 대비 unified diff)."""
    lines: list[str] = []
    for rel, new in patch.files.items():
        old = DEMO / rel
        lines += difflib.unified_diff((old.read_text(encoding="utf-8") if old.is_file() else "").splitlines(keepends=True),
                                      new.splitlines(keepends=True), f"a/{rel}", f"b/{rel}", n=2)
    return "".join(lines)


@router.post("", status_code=202)
async def start_verify(response: Response, jobs: JobsDep, user: ActorDep, body: VerifyStart | None = None):
    response.headers["Cache-Control"] = "no-store"
    if not (DEMO / "verify" / "attacks.json").is_file():
        raise _unavailable("이 서버에는 데모 과녁(demo-vulnerable-site)이 없습니다.")
    if not await run_in_threadpool(_runtime_ready):
        raise _unavailable("이 서버에는 실검증을 실행할 환경(Docker 또는 Node 22.5 이상)이 없습니다.")
    attacks, patch = _demo_inputs()
    # npm 스크립트와 같은 명령을 node로 바로 실행합니다 (Windows 개발 PC에서는 shell 없이 npm을 띄울 수 없음).
    # 테스트 출력은 TAP로 고정합니다. Node 23부터 기본 출력이 바뀌어 probe가 통과·실패 건수를 못 읽습니다
    req = VerifyRequest(repo_dir=str(DEMO), attacks=attacks, patch=patch,
                        start_cmd=["node", "server.js"], test_cmd=["node", "--test", "--test-reporter=tap"])
    extra = {
        "target": "demo",
        # 화면이 공격 요청·CWE·정적 탐지만 하는 항목까지 보여 줄 수 있게 공격 정의를 함께 돌려줍니다
        "attacks": [a.model_dump(exclude_none=True) for a in attacks],
        "patched_files": sorted(patch.files),
        "patch_diff": _diff(patch),
    }
    return jobs.submit(lambda: verify(req, trusted=True), owner=user, extra=extra)


@router.get("/{job_id}")
async def get_verify(job_id: str, response: Response, jobs: JobsDep, user: ActorDep):
    response.headers["Cache-Control"] = "no-store"
    return jobs.get(job_id, owner=user)
