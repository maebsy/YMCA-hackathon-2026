"""실검증 API: 데모 과녁에서 '수정 전 공격 성공 → 수정 후 차단 + 기능 테스트 통과'를 실제로 실행해 확인합니다.

- POST /api/verify        : 실검증을 접수하고 바로 job_id를 돌려줍니다 (202).
- GET  /api/verify/{id}   : 진행 상태(queued·running·done·failed)와, 끝났으면 result(VerifyResult)를 돌려줍니다.
  검사 API(scans.py)와 같은 "접수 → 작업 번호 → 조회" 방식이고 로그인 규칙도 같습니다.
- 같은 데모의 최근 done 결과(error 제외)는 요청자 소유의 새 작업으로 복사하며 실행 환경 확인도 건너뜁니다.
  재사용 시간은 VERIFY_REUSE_SECONDS로 정하고, 0이면 매번 실행합니다.

지금은 우리 데모 과녁(demo-vulnerable-site)만 받습니다. mode로 수정본을 고릅니다.
- reference(기본): 사람이 쓴 기준 수정본(verify/fix/)과 공격 정의(verify/attacks.json)로 실행합니다.
- ai: 데모의 탐지 결과를 GPU의 Red·Blue에 보내 공격 요청과 수정본을 만들게 하고(llm_bridge), 그걸로 실행합니다.
  모델이 만든 코드를 실행하므로 데모라도 trusted=False, 즉 Docker 격리(--network none)에서만 돌립니다.
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
from pydantic import BaseModel, ConfigDict, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import ROOT_DIR
from app.llm.client import LLMUnavailable
from app.llm.schemas import FindingInput, FindingRefs
from app.routers.scans import ActorDep
from app.verify import AttackSpec, Patch, VerifyRequest, VerifyResult, verify
from app.verify import llm_bridge
from app.verify.jobs import VerifyJobs
from app.verify.sandbox import docker_available

DEMO = Path(__file__).resolve().parents[3] / "demo-vulnerable-site"
DEFAULT_REUSE_SECONDS = 300  # 공개 데모 부하를 줄이기 위한 임시값입니다.
# AI 수정본 실검증: 실패하면 실행 결과를 Blue에게 돌려주고 한 번 더 고쳐 다시 실행합니다(최대 2회, 약 2~4분)
AI_MAX_ATTEMPTS = 2

router = APIRouter(prefix="/verify", tags=["verify"])


class _ReuseSettings(BaseSettings):
    # 다른 설정과 같은 루트 .env를 읽고, 요청마다 환경 변수 변경도 반영합니다.
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")
    verify_reuse_seconds: int = DEFAULT_REUSE_SECONDS

    @field_validator("verify_reuse_seconds", mode="before")
    @classmethod
    def _seconds_or_default(cls, value):
        try:
            seconds = int(value)
        except (TypeError, ValueError):
            return DEFAULT_REUSE_SECONDS
        return seconds if seconds >= 0 else DEFAULT_REUSE_SECONDS


class VerifyStart(BaseModel):
    # repo_dir·patch·start_cmd 같은 값을 보내면 조용히 무시하지 않고 422로 거절합니다
    model_config = ConfigDict(extra="forbid")
    target: Literal["demo"] = "demo"  # 지금은 우리 데모 과녁만
    mode: Literal["reference", "ai"] = "reference"


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


# 데모에서 Red·Blue에 보낼 탐지 결과. 런타임으로 재현되는 두 가지(SQL 주입·반사형 XSS)만 보냅니다.
# 줄 번호는 server.js에서 표식 문자열을 찾아 정하므로, 데모 코드가 바뀌어도 어긋나지 않습니다.
_DEMO_FINDINGS = [
    dict(fingerprint="demo:sqli-orders", tool="semgrep", rule_id="vibe-coding/sql-string-concat",
         title="SQL 문자열 연결 (주문 조회)", severity="critical", cwe="CWE-89",
         marker='"SELECT * FROM orders WHERE id = " +'),
    dict(fingerprint="demo:xss-search", tool="runtime", rule_id="reflected-xss",
         title="검색어가 HTML에 그대로 출력됨", severity="high", cwe="CWE-79",
         marker="req.query.q"),
]


def _demo_findings() -> list[FindingInput]:
    lines = (DEMO / "server.js").read_text(encoding="utf-8").splitlines()
    found = []
    for f in _DEMO_FINDINGS:
        line = next((n for n, text in enumerate(lines, 1) if f["marker"] in text), None)
        if line is None:
            continue
        found.append(FindingInput(fingerprint=f["fingerprint"], tool=f["tool"], category="code", rule_id=f["rule_id"],
                                  title=f["title"], severity=f["severity"], file_path="server.js",
                                  start_line=line, end_line=line, snippet=lines[line - 1].strip(),
                                  refs=FindingRefs(cwe=[f["cwe"]])))
    return found


def _ai_extra(plan: llm_bridge.VerificationPlan) -> dict:
    return {
        "attacks": [a.model_dump(exclude_none=True) for a in plan.attacks],
        "patched_files": sorted(plan.patch.files),
        "patch_diff": _diff(plan.patch),
        # 화면에서 'AI가 왜 이 공격·수정을 냈는지'와 건너뛴 항목을 보여 줄 수 있게 함께 돌려줍니다
        "ai": {
            "attack_fingerprints": plan.attack_fingerprints,
            "red_reasons": plan.red_reasons,
            "patch_summaries": plan.patch_summaries,
            "skipped": [s.model_dump() for s in plan.skipped],
        },
    }


def _ai_work(client, findings: list[FindingInput]):
    async def work():
        plan = await llm_bridge.plan_verification(client, findings, DEMO)
        # 수정본이 없는 파일의 공격은 빼고 실행합니다. 그대로 두면 '고치지 않았으니 여전히 뚫림'이
        # 수정 실패(fix_failed)로 보입니다
        keep = {f.fingerprint for f in findings if f.file_path in plan.patch.files}
        plan.attacks = [a for a in plan.attacks if plan.attack_fingerprints.get(a.id) in keep]
        if not plan.attacks or not plan.patch.files:
            reasons = "; ".join(s.reason for s in plan.skipped[:3])
            result = VerifyResult(status="error", message="AI가 실행할 공격이나 수정본을 만들지 못했습니다."
                                  + (f" ({reasons})" if reasons else ""))
            return result, _ai_extra(plan)
        attempts: list[dict] = []
        for attempt in range(1, AI_MAX_ATTEMPTS + 1):
            req = VerifyRequest(repo_dir=str(DEMO), attacks=plan.attacks, patch=plan.patch,
                                start_cmd=["node", "server.js"], test_cmd=["node", "--test", "--test-reporter=tap"])
            # 모델이 만든 코드를 실행하므로 Docker 격리만 허용합니다
            result = await run_in_threadpool(verify, req, trusted=False)
            attempts.append({"attempt": attempt, "status": result.status, "message": result.message[:300]})
            feedback = llm_bridge.run_feedback(result)
            if feedback is None or attempt == AI_MAX_ATTEMPTS:
                break
            # 실행 결과(앱 응답 없음·공격 통과·테스트 깨짐)를 Blue에게 돌려주고 원본 기준으로 다시 고치게 합니다
            revised: dict[str, str] = {}
            for rel, previous in plan.patch.files.items():
                group = [f for f in findings if f.file_path == rel]
                content, note = await llm_bridge.revise_patch(client, group, DEMO, rel, previous, feedback)
                if content is None:
                    attempts[-1]["retry_skipped"] = note[:300]
                    break
                revised[rel] = content
                plan.patch_summaries[rel] = note
            if len(revised) != len(plan.patch.files):
                break
            plan.patch.files.update(revised)
        extra = _ai_extra(plan)
        extra["ai"]["attempts"] = attempts
        return result, extra
    return work


def _diff(patch: Patch) -> str:
    """화면에 보여 줄 수정 내용 (원본 대비 unified diff)."""
    lines: list[str] = []
    for rel, new in patch.files.items():
        old = DEMO / rel
        lines += difflib.unified_diff((old.read_text(encoding="utf-8") if old.is_file() else "").splitlines(keepends=True),
                                      new.splitlines(keepends=True), f"a/{rel}", f"b/{rel}", n=2)
    return "".join(lines)


@router.post("", status_code=202)
async def start_verify(request: Request, response: Response, jobs: JobsDep, user: ActorDep,
                       body: VerifyStart | None = None):
    response.headers["Cache-Control"] = "no-store"
    if body is not None and body.mode == "ai":
        return await _start_ai(request, jobs, user)
    reused = jobs.reuse_recent(target="demo", owner=user, seconds=_ReuseSettings().verify_reuse_seconds)
    if reused is not None:
        return reused
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
        "mode": "reference",
        # 화면이 공격 요청·CWE·정적 탐지만 하는 항목까지 보여 줄 수 있게 공격 정의를 함께 돌려줍니다
        "attacks": [a.model_dump(exclude_none=True) for a in attacks],
        "patched_files": sorted(patch.files),
        "patch_diff": _diff(patch),
    }
    return jobs.submit(lambda: verify(req, trusted=True), owner=user, extra=extra)


async def _start_ai(request: Request, jobs: VerifyJobs, user) -> dict:
    # AI 결과는 기준 수정본 결과와 따로 재사용합니다 (GPU 호출을 줄이려고)
    reused = jobs.reuse_recent(target="demo-ai", owner=user, seconds=_ReuseSettings().verify_reuse_seconds)
    if reused is not None:
        return reused
    if not (DEMO / "server.js").is_file():
        raise _unavailable("이 서버에는 데모 과녁(demo-vulnerable-site)이 없습니다.")
    if not await run_in_threadpool(docker_available):
        raise _unavailable("AI 수정본 실검증은 Docker 격리가 있는 서버에서만 실행합니다.")
    explainer = getattr(request.app.state, "explainer", None)
    if explainer is None:
        raise _unavailable("이 서버에는 LLM 연결이 설정되어 있지 않습니다.")
    try:
        await explainer.client.health()
    except LLMUnavailable as exc:
        raise _unavailable("GPU LLM 서버에 연결할 수 없습니다.") from exc
    findings = _demo_findings()
    if not findings:
        raise _unavailable("데모 과녁에서 실검증할 탐지 결과를 찾지 못했습니다.")
    extra = {"target": "demo-ai", "mode": "ai",
             "findings": [f.model_dump(include={"fingerprint", "rule_id", "title", "severity", "start_line"})
                          for f in findings]}
    return jobs.submit(_ai_work(explainer.client, findings), owner=user, extra=extra)


@router.get("/{job_id}")
async def get_verify(job_id: str, response: Response, jobs: JobsDep, user: ActorDep):
    response.headers["Cache-Control"] = "no-store"
    return jobs.get(job_id, owner=user)
