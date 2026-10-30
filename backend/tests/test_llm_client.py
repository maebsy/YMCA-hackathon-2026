import asyncio
import json

import httpx
import pytest

from app.llm.client import LLMBadOutput, LLMClient, LLMError, LLMUnavailable, Sampling
from app.llm.quality import problems
from app.llm.schemas import BlueDraft, RedReview
from tests.conftest import FakeVLLM, blue_draft, red_review

pytestmark = pytest.mark.anyio


def user(text: str = "탐지 결과") -> list[dict]:
    return [{"role": "user", "content": text}]


async def test_request_forces_json_schema_and_turns_off_thinking(fake_vllm):
    fake_vllm.queue("BlueDraft", blue_draft())
    client = fake_vllm.client()

    result = await client.chat_json(user(), BlueDraft, sampling=Sampling(max_tokens=777))

    body = fake_vllm.requests[0]
    assert body["model"] == "qwen3.8-27b"
    assert body["response_format"]["type"] == "json_schema"
    assert body["response_format"]["json_schema"]["strict"] is True
    assert body["response_format"]["json_schema"]["schema"] == BlueDraft.model_json_schema()
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert body["max_tokens"] == 777
    assert fake_vllm.headers[0]["authorization"] == "Bearer test-key"
    assert result.data.summary.startswith("주문 조회")
    assert result.completion_tokens == 50


async def test_thinking_passes_reasoning_effort(fake_vllm):
    fake_vllm.queue("RedReview", red_review())
    await fake_vllm.client().chat_json(user(), RedReview, thinking=True, reasoning_effort="low")

    assert fake_vllm.requests[0]["chat_template_kwargs"] == {"enable_thinking": True, "reasoning_effort": "low"}


async def test_retries_server_errors_then_succeeds(fake_vllm):
    fake_vllm.queue("BlueDraft", 503, httpx.ConnectError("boom"), blue_draft())

    result = await fake_vllm.client(max_retries=2).chat_json(user(), BlueDraft)

    assert len(fake_vllm.requests) == 3
    assert result.data.summary


async def test_gives_up_after_retries(fake_vllm):
    fake_vllm.queue("BlueDraft", 503, 503, 503)

    with pytest.raises(LLMUnavailable, match="503"):
        await fake_vllm.client(max_retries=2).chat_json(user(), BlueDraft)
    assert len(fake_vllm.requests) == 3


async def test_timeout_is_unavailable(fake_vllm):
    fake_vllm.queue("BlueDraft", httpx.ReadTimeout("slow"))

    with pytest.raises(LLMUnavailable, match="시간 초과"):
        await fake_vllm.client(max_retries=0).chat_json(user(), BlueDraft)


async def test_client_errors_are_not_retried(fake_vllm):
    fake_vllm.queue("BlueDraft", 400)

    with pytest.raises(LLMError) as excinfo:
        await fake_vllm.client().chat_json(user(), BlueDraft)
    assert not isinstance(excinfo.value, LLMUnavailable)
    assert len(fake_vllm.requests) == 1


async def test_invalid_json_is_repaired_once(fake_vllm):
    fake_vllm.queue("BlueDraft", "설명입니다 (JSON 아님)", blue_draft())

    result = await fake_vllm.client().chat_json(user(), BlueDraft)

    assert result.data.summary.startswith("주문 조회")
    retry_messages = fake_vllm.requests[1]["messages"]
    assert retry_messages[-2] == {"role": "assistant", "content": "설명입니다 (JSON 아님)"}
    assert "JSON이 아닙니다" in retry_messages[-1]["content"]
    assert result.completion_tokens == 100


async def test_invalid_twice_raises_bad_output(fake_vllm):
    fake_vllm.queue("BlueDraft", "{}", '{"summary": 1}')

    with pytest.raises(LLMBadOutput):
        await fake_vllm.client().chat_json(user(), BlueDraft)


async def test_truncated_answer_is_repaired(fake_vllm):
    fake_vllm.queue("BlueDraft", ('{"summary": "잘린', "length"), blue_draft())

    await fake_vllm.client().chat_json(user(), BlueDraft)

    assert "잘렸습니다" in fake_vllm.requests[1]["messages"][-1]["content"]


async def test_think_block_is_stripped(fake_vllm):
    fake_vllm.queue("RedReview", "<think>우회 경로를 따져 보자</think>\n" + json.dumps(red_review()))

    result = await fake_vllm.client().chat_json(user(), RedReview)

    assert result.data.verdict == "pass"


async def test_quality_problem_triggers_one_rewrite(fake_vllm):
    fake_vllm.queue("BlueDraft", blue_draft(summary="주문 조회 API에 SQL 注入 문제가 있습니다."), blue_draft())

    result = await fake_vllm.client().chat_json(user(), BlueDraft, check=problems)

    assert "注入" not in result.data.summary
    assert "한자" in fake_vllm.requests[1]["messages"][-1]["content"]


async def test_quality_problem_left_after_rewrite_is_returned(fake_vllm):
    mixed = blue_draft(summary="SQL 注入 문제")
    fake_vllm.queue("BlueDraft", mixed, mixed)

    result = await fake_vllm.client().chat_json(user(), BlueDraft, check=problems)

    assert result.data.summary == "SQL 注入 문제"
    assert len(fake_vllm.requests) == 2


async def test_concurrency_is_limited():
    in_flight = 0
    peak = 0

    async def slow_handler(request: httpx.Request) -> httpx.Response:
        nonlocal in_flight, peak
        in_flight += 1
        peak = max(peak, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(red_review())}, "finish_reason": "stop"}], "usage": {}},
        )

    client = LLMClient("http://vllm.test/v1", "qwen3.8-27b", max_concurrency=2, transport=httpx.MockTransport(slow_handler))
    await asyncio.gather(*(client.chat_json(user(), RedReview) for _ in range(6)))

    assert peak == 2


async def test_health_lists_models(fake_vllm):
    assert await fake_vllm.client().health() == ["qwen3.8-27b"]


async def test_health_fails_when_model_missing():
    with pytest.raises(LLMUnavailable, match="없습니다"):
        await FakeVLLM(models=("other-model",)).client().health()


async def test_health_fails_when_server_down():
    def refuse(request):
        raise httpx.ConnectError("refused")

    client = LLMClient("http://vllm.test/v1", "qwen3.8-27b", transport=httpx.MockTransport(refuse))
    with pytest.raises(LLMUnavailable, match="연결할 수 없습니다"):
        await client.health()
