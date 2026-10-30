"""vLLM(OpenAI 호환 API) 클라이언트.

모델이 바뀌어도 OpenAI 호환 서버면 그대로 씁니다. vLLM 전용 값(`chat_template_kwargs`, `top_k`)은
다른 서버가 무시해도 동작에 문제가 없게만 씁니다.
"""

import asyncio
import json
import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# 서버에 reasoning parser 가 없으면 생각 과정이 본문에 섞여 옵니다
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


class LLMError(Exception):
    """LLM 호출 실패의 공통 부모."""


class LLMUnavailable(LLMError):
    """연결 실패, 시간 초과, 5xx. 서버가 꺼졌거나 과부하입니다."""


class LLMBadOutput(LLMError):
    """응답이 규격(JSON 스키마)에 맞지 않습니다."""


@dataclass
class ChatResult(Generic[T]):
    data: T
    completion_tokens: int
    latency_ms: int


@dataclass(frozen=True)
class Sampling:
    temperature: float = 0.6
    top_p: float = 0.9
    top_k: int = 20
    max_tokens: int = 1500


DEFAULT_SAMPLING = Sampling()


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout_s: float = 300.0,
        max_concurrency: int = 8,
        max_retries: int = 2,
        retry_backoff_s: float = 1.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.model = model
        self.max_retries = max_retries
        self.retry_backoff_s = retry_backoff_s
        self._http = httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/",
            headers=headers,
            timeout=httpx.Timeout(timeout_s, connect=10.0),
            transport=transport,
        )
        # GPU 한 장에 한꺼번에 몰리지 않게 동시 요청 수를 제한합니다
        self._slots = asyncio.Semaphore(max_concurrency)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def health(self) -> list[str]:
        """서버가 응답하고 설정한 모델이 올라가 있는지 확인하고, 올라간 모델 이름을 돌려줍니다."""
        try:
            resp = await self._http.get("models", timeout=10.0)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"LLM 서버에 연결할 수 없습니다: {type(exc).__name__}") from exc
        if resp.status_code != 200:
            raise LLMUnavailable(f"LLM 서버 응답 {resp.status_code}")
        models = [m.get("id") for m in resp.json().get("data", [])]
        if self.model not in models:
            raise LLMUnavailable(f"모델 {self.model!r}이 서버에 없습니다 (있는 모델: {models})")
        return models

    async def chat_json(
        self,
        messages: list[dict],
        schema: type[T],
        *,
        thinking: bool = False,
        reasoning_effort: str | None = None,
        sampling: Sampling = DEFAULT_SAMPLING,
        check: Callable[[T], list[str]] | None = None,
    ) -> ChatResult[T]:
        """JSON 스키마를 강제해 호출하고, 결과를 `schema`로 검증해 돌려줍니다.

        형식이 어긋나거나 `check`가 문제를 찾으면 그 내용을 알려 주고 한 번 더 요청합니다.
        다시 받은 응답이 형식에 맞으면 `check` 문제가 남아 있어도 돌려줍니다(로그만 남김).
        """
        template_kwargs: dict = {"enable_thinking": thinking}
        if thinking and reasoning_effort:
            template_kwargs["reasoning_effort"] = reasoning_effort
        body = {
            "model": self.model,
            "messages": messages,
            "temperature": sampling.temperature,
            "top_p": sampling.top_p,
            "top_k": sampling.top_k,
            "max_tokens": sampling.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema(), "strict": True},
            },
            "chat_template_kwargs": template_kwargs,
        }

        started = time.perf_counter()
        tokens = 0
        for attempt in range(2):
            payload = await self._post_chat(body)
            tokens += payload.get("usage", {}).get("completion_tokens", 0)
            choice = payload["choices"][0]
            content = choice["message"].get("content") or ""
            try:
                data = _parse(content, schema, truncated=choice.get("finish_reason") == "length")
                problems = check(data) if check else []
            except LLMBadOutput as exc:
                if attempt == 1:
                    raise
                problems = [str(exc)]
            if problems and attempt == 0:
                log.warning("LLM 응답에 문제가 있어 다시 요청합니다: %s", problems)
                body = {
                    **body,
                    "messages": [
                        *messages,
                        {"role": "assistant", "content": content[:4000]},
                        {"role": "user", "content": "응답을 고쳐야 합니다: " + "; ".join(problems) + "\n같은 JSON 형식으로 다시 출력하세요."},
                    ],
                }
                continue
            if problems:
                log.warning("다시 요청한 응답에도 문제가 남았습니다: %s", problems)
            latency_ms = int((time.perf_counter() - started) * 1000)
            return ChatResult(data=data, completion_tokens=tokens, latency_ms=latency_ms)
        raise AssertionError("unreachable")

    async def _post_chat(self, body: dict) -> dict:
        last_error = "알 수 없는 오류"
        for attempt in range(self.max_retries + 1):
            if attempt:
                await asyncio.sleep(self.retry_backoff_s * 2 ** (attempt - 1))
            try:
                async with self._slots:
                    resp = await self._http.post("chat/completions", json=body)
            except httpx.TimeoutException:
                last_error = "응답 시간 초과"
                continue
            except httpx.HTTPError as exc:
                last_error = f"연결 오류: {type(exc).__name__}"
                continue
            if resp.status_code >= 500 or resp.status_code == 429:
                last_error = f"서버 응답 {resp.status_code}"
                continue
            if resp.status_code != 200:
                # 4xx 는 요청이 잘못된 것이라 다시 보내도 같습니다
                raise LLMError(f"LLM 요청 거부 {resp.status_code}: {resp.text[:300]}")
            return resp.json()
        raise LLMUnavailable(last_error)


def _parse(content: str, schema: type[T], *, truncated: bool) -> T:
    text = _THINK_RE.sub("", content).strip()
    if truncated:
        raise LLMBadOutput("최대 길이에서 잘렸습니다. 더 짧게 쓰세요")
    try:
        return schema.model_validate(json.loads(text))
    except json.JSONDecodeError as exc:
        raise LLMBadOutput(f"JSON이 아닙니다 ({exc.msg})") from exc
    except ValidationError as exc:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors()[:5])
        raise LLMBadOutput(problems) from exc
