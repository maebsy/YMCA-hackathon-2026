import pytest

from app.llm.pipeline import Explainer
from app.llm.prompts import PROMPT_VERSION
from tests.conftest import FAKE_OPENAI_KEY, blue_draft, red_review

pytestmark = pytest.mark.anyio


async def test_blue_only_is_variant_c(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft())

    result = await Explainer(fake_vllm.client()).blue(findings[1])

    assert result.variant == "C"
    assert result.fingerprint == "demo-code-sqli-orders"
    assert result.red_rounds == [] and result.red_verdict is None and result.attack_scenario is None
    assert result.model == "qwen3.8-27b"
    assert result.prompt_version == PROMPT_VERSION
    assert fake_vllm.calls("RedReview") == []


async def test_red_blue_passes_first_round(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft()).queue("RedReview", red_review("pass"))

    result = await Explainer(fake_vllm.client()).red_blue(findings[1])

    assert result.variant == "D"
    assert result.red_verdict == "pass"
    assert result.needs_manual_review is False
    assert [r.verdict for r in result.red_rounds] == ["pass"]
    assert result.attack_scenario.startswith("공격자가")
    assert result.completion_tokens == 100
    red_call = fake_vllm.calls("RedReview")[0]
    assert red_call["chat_template_kwargs"]["enable_thinking"] is True


async def test_red_blue_rewrites_until_pass(fake_vllm, findings):
    revised = blue_draft(ai_fix_prompt="매개변수 쿼리로 바꾸고, 로그인한 사용자 본인 주문만 조회하게 해 주세요.")
    fake_vllm.queue("BlueDraft", blue_draft(), revised)
    fake_vllm.queue("RedReview", red_review("bypass"), red_review("pass"))

    result = await Explainer(fake_vllm.client()).red_blue(findings[1])

    assert [r.verdict for r in result.red_rounds] == ["bypass", "pass"]
    assert result.ai_fix_prompt == revised["ai_fix_prompt"]
    assert result.needs_manual_review is False
    revise_request = fake_vllm.calls("BlueDraft")[1]["messages"][-1]["content"]
    assert "로그인한 사용자 본인 주문만 보이도록" in revise_request


async def test_red_blue_stops_after_max_rewrites(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft(), blue_draft(), blue_draft())
    fake_vllm.queue("RedReview", red_review("incomplete"), red_review("bypass"), red_review("bypass"))

    result = await Explainer(fake_vllm.client(), max_rewrites=2).red_blue(findings[1])

    assert len(fake_vllm.calls("BlueDraft")) == 3
    assert len(fake_vllm.calls("RedReview")) == 3
    assert [r.round for r in result.red_rounds] == [0, 1, 2]
    assert result.red_verdict == "bypass"
    assert result.needs_manual_review is True


async def test_secrets_written_by_model_are_masked(fake_vllm, findings):
    leaked = FAKE_OPENAI_KEY
    fake_vllm.queue("BlueDraft", blue_draft(ai_fix_prompt=f"키 {leaked} 를 지우세요"))

    result = await Explainer(fake_vllm.client()).blue(findings[0])

    assert leaked not in result.ai_fix_prompt
    assert "[가림]" in result.ai_fix_prompt


async def test_one_failure_does_not_sink_the_batch(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft(), 400, blue_draft())

    results = await Explainer(fake_vllm.client()).explain_many(findings[:3], "blue")

    assert [r.status for r in results] == ["done", "failed", "done"]
    assert results[1].error_code == "LLM_ERROR"
    assert results[1].explanation is None


async def test_unavailable_is_reported_per_finding(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", 503, 503, 503)

    [result] = await Explainer(fake_vllm.client()).explain_many(findings[:1], "blue")

    assert result.status == "failed"
    assert result.error_code == "LLM_UNAVAILABLE"
