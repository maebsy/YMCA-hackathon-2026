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


async def test_false_positive_reason_only_when_suspected(fake_vllm, findings):
    fake_vllm.queue(
        "BlueDraft",
        blue_draft(false_positive_suspect=False, false_positive_reason="실제 코드라 오탐이 아닙니다"),
        blue_draft(false_positive_suspect=True, false_positive_reason="테스트 폴더의 예시 값입니다"),
    )
    explainer = Explainer(fake_vllm.client())

    assert (await explainer.blue(findings[1])).false_positive_reason is None
    assert (await explainer.blue(findings[1])).false_positive_reason == "테스트 폴더의 예시 값입니다"


async def test_context_overflow_retries_with_smaller_input(fake_vllm, findings):
    overflow = (400, '{"error": {"message": "This model\'s maximum context length is 12288 tokens."}}')
    long = findings[1].model_copy(update={"context": "x" * 8000})
    fake_vllm.queue("BlueDraft", overflow, overflow, blue_draft())

    result = await Explainer(fake_vllm.client()).blue(long)

    sizes = [len(r["messages"][-1]["content"]) for r in fake_vllm.calls("BlueDraft")]
    assert len(sizes) == 3 and sizes[0] > sizes[1] > sizes[2]
    assert result.summary


async def test_context_overflow_gives_up_with_clear_code(fake_vllm, findings):
    overflow = (400, "maximum context length exceeded")
    fake_vllm.queue("BlueDraft", overflow, overflow, overflow)

    [result] = await Explainer(fake_vllm.client()).explain_many(findings[1:2], "blue")

    assert result.status == "failed"
    assert result.error_code == "LLM_INPUT_TOO_LONG"


async def test_secrets_in_red_issues_and_step_titles_are_masked(fake_vllm, findings):
    leaked = FAKE_OPENAI_KEY
    step = {"title": f"키 {leaked} 지우기", "detail": "코드에서 지웁니다."}
    fake_vllm.queue("BlueDraft", blue_draft(fix_steps=[step]), blue_draft(fix_steps=[step]))
    fake_vllm.queue("RedReview", red_review("incomplete", issues=[f"{leaked} 를 재발급하라는 단계가 없습니다"]), red_review())

    result = await Explainer(fake_vllm.client()).red_blue(findings[0])

    dumped = result.model_dump_json()
    assert leaked not in dumped
    assert result.red_rounds[0].issues[0].startswith("[가림]")
    assert result.fix_steps[0].title == "키 [가림] 지우기"


# ── 문맥 분석·위험도 단계 (#33) ──


async def test_context_analysis_feeds_risk_and_prompts(fake_vllm, findings):
    from tests.conftest import context_analysis

    fake_vllm.queue("ContextAnalysis", context_analysis())
    fake_vllm.queue("BlueDraft", blue_draft()).queue("RedReview", red_review("pass"))

    result = await Explainer(fake_vllm.client(), analyze_context=True).red_blue(findings[1])

    assert result.context.exposure == "public" and result.context.confidence == "high"
    assert result.risk.decision == "attend" and result.priority == "soon"
    blue_prompt = fake_vllm.calls("BlueDraft")[0]["messages"][-1]["content"]
    red_prompt = fake_vllm.calls("RedReview")[0]["messages"][-1]["content"]
    assert "<analysis>" in blue_prompt and '"decision": "attend"' in blue_prompt
    assert "<analysis>" in red_prompt
    context_prompt = fake_vllm.calls("ContextAnalysis")[0]["messages"][-1]["content"]
    assert "<signals>" in context_prompt and "server_route" in context_prompt


async def test_context_failure_falls_back_to_signals(fake_vllm, findings):
    fake_vllm.queue("ContextAnalysis", "not json", "still not json")
    fake_vllm.queue("BlueDraft", blue_draft())

    [result] = await Explainer(fake_vllm.client(), analyze_context=True).explain_many(findings[1:2], "blue")

    assert result.status == "done"
    assert result.explanation.context.confidence == "low"
    assert result.explanation.risk is not None


async def test_context_outage_fails_the_finding(fake_vllm, findings):
    fake_vllm.queue("ContextAnalysis", 503, 503, 503)

    [result] = await Explainer(fake_vllm.client(), analyze_context=True).explain_many(findings[1:2], "blue")

    assert result.status == "failed" and result.error_code == "LLM_UNAVAILABLE"


async def test_priority_comes_from_risk_not_model(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft(priority="later"))  # 모델이 priority 를 적어도 무시됩니다

    result = await Explainer(fake_vllm.client()).blue(findings[0])  # 브라우저 코드에 service_role 키

    assert result.risk.decision == "act"
    assert result.priority == "now"


async def test_threat_intel_is_looked_up_once_per_batch(fake_vllm, findings):
    from app.llm.intel import StaticThreatIntel
    from app.llm.schemas import ThreatIntelRecord

    class CountingIntel(StaticThreatIntel):
        calls = 0

        async def lookup(self, cves):
            CountingIntel.calls += 1
            return await super().lookup(cves)

    cve = "CVE-2025-29927"
    intel = CountingIntel({cve: ThreatIntelRecord(cve=cve, epss=0.99, epss_percentile=0.999)})
    fake_vllm.queue("BlueDraft", *[blue_draft() for _ in findings])

    results = await Explainer(fake_vllm.client(), intel=intel).explain_many(findings, "blue")

    assert CountingIntel.calls == 1
    dep = next(r for r in results if r.fingerprint == "demo-dep-next-middleware-bypass")
    assert dep.explanation.risk.exploitation == "public poc"
    assert dep.explanation.risk.intel[0].epss == 0.99
