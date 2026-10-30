"""Blue 단독(평가 C)과 Red–Blue(평가 D) 파이프라인.

Red–Blue 흐름 (docs/system-flow.md ③ 해석 · GPU):
  Blue가 설명·수정 지시 작성 → Red가 공격자 관점으로 판정
  → pass면 끝, 아니면 Red의 지적을 붙여 Blue가 다시 작성 (최대 `max_rewrites`회)
  → 끝까지 pass가 아니면 마지막 수정 지시에 needs_manual_review 를 붙여 내보냅니다.
"""

import asyncio
import logging
import time
from typing import Literal

from app.llm import prompts, quality
from app.llm.client import LLMBadOutput, LLMClient, LLMError, LLMUnavailable, Sampling
from app.llm.schemas import (
    BlueDraft,
    ExplainResult,
    Explanation,
    FindingInput,
    RedReview,
    RedRound,
)

log = logging.getLogger(__name__)

Mode = Literal["blue", "red_blue"]

# Blue는 생각 모드를 끄고 바로 씁니다. Red는 우회 경로를 따져야 해서 짧게 생각하게 합니다
BLUE_SAMPLING = Sampling(max_tokens=2500)
RED_SAMPLING = Sampling(max_tokens=3500)


class Explainer:
    def __init__(self, client: LLMClient, max_rewrites: int = 2, red_thinking: bool = True) -> None:
        self.client = client
        self.max_rewrites = max_rewrites
        self.red_thinking = red_thinking

    async def explain_many(self, findings: list[FindingInput], mode: Mode) -> list[ExplainResult]:
        """여러 건을 동시에 보냅니다. GPU가 묶어서 처리해야 L4에서 전체 시간이 줄어듭니다.

        한 건이 실패해도 나머지는 그대로 돌려줍니다.
        """
        run = self.blue if mode == "blue" else self.red_blue
        return list(await asyncio.gather(*(self._safe(run, f) for f in findings)))

    async def _safe(self, run, finding: FindingInput) -> ExplainResult:
        try:
            explanation = await run(finding)
        except LLMError as exc:
            log.warning("LLM 해석 실패 %s: %s", finding.fingerprint, exc)
            code = (
                "LLM_UNAVAILABLE"
                if isinstance(exc, LLMUnavailable)
                else "LLM_BAD_OUTPUT"
                if isinstance(exc, LLMBadOutput)
                else "LLM_ERROR"
            )
            return ExplainResult(fingerprint=finding.fingerprint, status="failed", error_code=code, error=str(exc))
        return ExplainResult(fingerprint=finding.fingerprint, status="done", explanation=explanation)

    async def blue(self, finding: FindingInput) -> Explanation:
        started = time.perf_counter()
        draft = await self._blue_draft(prompts.blue_messages(finding))
        return self._explanation(finding, "C", draft.data, started, draft.completion_tokens)

    async def red_blue(self, finding: FindingInput) -> Explanation:
        started = time.perf_counter()
        draft = await self._blue_draft(prompts.blue_messages(finding))
        tokens = draft.completion_tokens
        rounds: list[RedRound] = []
        for round_no in range(self.max_rewrites + 1):
            review = await self.client.chat_json(
                prompts.red_messages(finding, draft.data),
                RedReview,
                thinking=self.red_thinking,
                reasoning_effort="low",
                sampling=RED_SAMPLING,
                check=quality.problems,
            )
            tokens += review.completion_tokens
            rounds.append(
                RedRound(
                    round=round_no,
                    verdict=review.data.verdict,
                    issues=review.data.issues,
                    latency_ms=review.latency_ms,
                )
            )
            if review.data.verdict == "pass" or round_no == self.max_rewrites:
                break
            draft = await self._blue_draft(prompts.blue_revise_messages(finding, draft.data, review.data))
            tokens += draft.completion_tokens

        explanation = self._explanation(finding, "D", draft.data, started, tokens)
        explanation.attack_scenario = prompts.redact_secrets(review.data.attack_scenario)
        explanation.red_verdict = review.data.verdict
        explanation.red_rounds = rounds
        explanation.needs_manual_review = review.data.verdict != "pass"
        return explanation

    async def _blue_draft(self, messages: list[dict]):
        return await self.client.chat_json(
            messages, BlueDraft, thinking=False, sampling=BLUE_SAMPLING, check=quality.problems
        )

    def _explanation(
        self, finding: FindingInput, variant: str, draft: BlueDraft, started: float, tokens: int
    ) -> Explanation:
        # 모델이 실수로 비밀값을 다시 적어도 밖으로 나가지 않게 가립니다 (수정 지시는 외부 AI 코딩툴로 갑니다)
        redact = prompts.redact_secrets
        return Explanation(
            fingerprint=finding.fingerprint,
            variant=variant,
            summary=redact(draft.summary),
            why_risky=redact(draft.why_risky),
            priority=draft.priority,
            fix_steps=[step.model_copy(update={"detail": redact(step.detail)}) for step in draft.fix_steps],
            ai_fix_prompt=redact(draft.ai_fix_prompt),
            false_positive_suspect=draft.false_positive_suspect,
            # 모델이 오탐이 아니라고 하면서 이유를 적는 경우가 있어, 오탐 의심일 때만 남깁니다
            false_positive_reason=redact(draft.false_positive_reason) if draft.false_positive_suspect else None,
            model=self.client.model,
            prompt_version=prompts.PROMPT_VERSION,
            latency_ms=int((time.perf_counter() - started) * 1000),
            completion_tokens=tokens,
        )
