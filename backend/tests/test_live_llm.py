"""GPU 서버의 실제 vLLM으로 돌리는 통합 테스트.

    LLM_LIVE=1 pytest -m live -s

`.env`의 LLM_BASE_URL·LLM_API_KEY·LLM_MODEL을 씁니다 (SSH 터널이 열려 있어야 합니다).
"""

import os

import pytest

from app.llm import create_explainer
from app.llm.quality import foreign_script_count, hangul_ratio

pytestmark = [
    pytest.mark.live,
    pytest.mark.anyio,
    pytest.mark.skipif(os.environ.get("LLM_LIVE") != "1", reason="LLM_LIVE=1 일 때만 실제 vLLM으로 돕니다"),
]


@pytest.fixture
async def explainer():
    explainer = create_explainer()
    yield explainer
    await explainer.aclose()


def readable_korean(explanation) -> str:
    return "\n".join([explanation.summary, explanation.why_risky, *(s.detail for s in explanation.fix_steps)])


async def test_server_has_model(explainer):
    assert explainer.client.model in await explainer.client.health()


async def test_blue_writes_plain_korean(explainer, findings):
    result = await explainer.blue(findings[1])  # SQL 주입
    text = readable_korean(result)
    print(f"\n[blue] {result.latency_ms} ms, {result.completion_tokens} tokens\n{result.model_dump_json(indent=2)}")

    assert foreign_script_count(text) == 0
    assert hangul_ratio(text) > 0.6
    assert result.priority in ("now", "soon")
    assert "route.ts" in result.ai_fix_prompt


async def test_red_blue_on_leaked_key(explainer, findings):
    result = await explainer.red_blue(findings[0])  # service_role 키 노출
    print(f"\n[red-blue] {result.latency_ms} ms, rounds={[r.verdict for r in result.red_rounds]}")
    print(result.model_dump_json(indent=2))

    assert result.red_rounds
    assert result.attack_scenario and "```" not in result.attack_scenario
    assert foreign_script_count(readable_korean(result) + result.attack_scenario) == 0
    # 키가 노출되면 지우는 것만으로는 부족하고 재발급까지 안내해야 합니다
    assert any(word in result.model_dump_json() for word in ("재발급", "새로 발급", "폐기", "교체"))
