import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.llm.client import LLMUnavailable
from app.llm.pipeline import Explainer, Mode
from app.llm.prompts import PROMPT_VERSION
from app.llm.schemas import ExplainResult, FindingInput, UserEnvironment

router = APIRouter(prefix="/llm", tags=["llm"])


def get_explainer(request: Request) -> Explainer:
    return request.app.state.explainer


ExplainerDep = Annotated[Explainer, Depends(get_explainer)]


class ExplainRequest(BaseModel):
    # GPU 한 장을 한 요청이 오래 붙잡지 않게 한 번에 50건까지만 받습니다
    findings: list[FindingInput] = Field(min_length=1, max_length=50)
    mode: Mode = "red_blue"
    # 사용자 OS·배포 환경. 비우면 Windows·macOS·Linux 명령을 모두 만듭니다
    environment: UserEnvironment | None = None


class ExplainResponse(BaseModel):
    mode: Mode
    model: str
    prompt_version: str
    latency_ms: int
    results: list[ExplainResult]


@router.post("/explain/tasks", status_code=202)
async def start_explain_task(body: ExplainRequest, request: Request, explainer: ExplainerDep):
    """Legacy demo: acknowledge immediately so public proxies never wait on GPU generation."""
    return request.app.state.preview_jobs.submit(lambda: explain(body, explainer))


@router.get("/explain/tasks/{job_id}")
async def get_explain_task(job_id: str, request: Request):
    return request.app.state.preview_jobs.get(job_id)


@router.get("/health")
async def health(explainer: ExplainerDep):
    try:
        await explainer.client.health()
    except LLMUnavailable as exc:
        raise HTTPException(503, detail={"code": "LLM_UNAVAILABLE", "message": str(exc)}) from exc
    return {"status": "ok", "model": explainer.client.model}


@router.post("/explain", response_model=ExplainResponse)
async def explain(body: ExplainRequest, explainer: ExplainerDep):
    """탐지 결과를 쉬운 설명·수정 지시로 바꿉니다. mode=blue 는 평가 C, red_blue 는 평가 D 입니다."""
    started = time.perf_counter()
    results = await explainer.explain_many(body.findings, body.mode, body.environment)
    # 부른 항목이 전부 서버 문제로 실패했으면 결과 목록 대신 503 으로 알려 프론트가 "잠시 후 다시"를 띄우게 합니다
    attempted = [r for r in results if r.status != "skipped"]
    if attempted and all(r.error_code == "LLM_UNAVAILABLE" for r in attempted):
        raise HTTPException(503, detail={"code": "LLM_UNAVAILABLE", "message": attempted[0].error})
    return ExplainResponse(
        mode=body.mode,
        model=explainer.client.model,
        prompt_version=PROMPT_VERSION,
        latency_ms=int((time.perf_counter() - started) * 1000),
        results=results,
    )
