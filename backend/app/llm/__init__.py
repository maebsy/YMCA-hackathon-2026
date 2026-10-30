"""③ 해석 · GPU: 로컬 LLM(vLLM)으로 탐지 결과를 설명하고 Red–Blue로 수정 지시를 검증합니다."""

from app.config import settings
from app.llm.client import LLMClient
from app.llm.pipeline import Explainer


def create_explainer() -> Explainer:
    client = LLMClient(
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        api_key=settings.llm_api_key,
        timeout_s=settings.llm_timeout_s,
        max_concurrency=settings.llm_max_concurrency,
    )
    return Explainer(
        client,
        max_rewrites=settings.llm_red_blue_max_rewrites,
        red_reasoning_effort=settings.llm_red_reasoning_effort,
    )
