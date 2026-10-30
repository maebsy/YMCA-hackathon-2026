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
from app.llm.client import (
    LLMBadOutput,
    LLMClient,
    LLMContextOverflow,
    LLMError,
    LLMUnavailable,
    Sampling,
)
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
# 문맥 길이를 넘으면 입력 예산을 이 비율로 차례로 줄여 다시 보냅니다
BUDGET_SCALES = (1.0, 0.5, 0.25)
# 출력 한도는 프롬프트 길이 예산(prompts.py)과 함께 문맥 12K(serve.sh --max-model-len) 안에 들어가게 정했습니다
BLUE_SAMPLING = Sampling(max_tokens=2500)
RED_SAMPLING = Sampling(max_tokens=3500)


def skip_reason(finding: FindingInput) -> str | None:
    """설명하지 않을 항목이면 이유를 돌려줍니다.

    change 가 resolved 여도 status 가 runtime_check_needed 면 설명합니다. 코드에서 지운 비밀값처럼
    키 재발급 같은 조치가 아직 남은 경우입니다.
    """
    if finding.status == "code_resolved":
        return "코드에서 이미 해결된 항목입니다"
    if finding.status == "out_of_scope":
        # 재검사에서 도구가 실패해 확인하지 못한 항목. "지금 문제 있음"으로 설명하면 안 됩니다
        return "이번 검사에서 확인하지 못했습니다. 다시 검사가 필요합니다"
    if finding.status is None and finding.change == "resolved":
        return "재검사에서 해결된 항목입니다"
    return None


class Explainer:
    def __init__(
        self, client: LLMClient, max_rewrites: int = 2, red_thinking: bool = True, red_reasoning_effort: str = "low"
    ) -> None:
        self.client = client
        self.max_rewrites = max_rewrites
        self.red_thinking = red_thinking
        self.red_reasoning_effort = red_reasoning_effort

    async def explain_many(self, findings: list[FindingInput], mode: Mode) -> list[ExplainResult]:
        """여러 건을 동시에 보냅니다. GPU가 묶어서 처리해야 L4에서 전체 시간이 줄어듭니다.

        한 건이 실패해도 나머지는 그대로 돌려줍니다. 코드에서 이미 해결된 항목은 GPU를 쓰지 않고 건너뜁니다.
        """
        run = self.blue if mode == "blue" else self.red_blue
        return list(await asyncio.gather(*(self._safe(run, f) for f in findings)))

    async def _safe(self, run, finding: FindingInput) -> ExplainResult:
        if reason := skip_reason(finding):
            return ExplainResult(fingerprint=finding.fingerprint, status="skipped", reason=reason)
        try:
            explanation = await run(finding)
        except LLMError as exc:
            log.warning("LLM 해석 실패 %s: %s", finding.fingerprint, exc)
            code = (
                "LLM_UNAVAILABLE"
                if isinstance(exc, LLMUnavailable)
                else "LLM_BAD_OUTPUT"
                if isinstance(exc, LLMBadOutput)
                else "LLM_INPUT_TOO_LONG"
                if isinstance(exc, LLMContextOverflow)
                else "LLM_ERROR"
            )
            return ExplainResult(fingerprint=finding.fingerprint, status="failed", error_code=code, error=str(exc))
        return ExplainResult(fingerprint=finding.fingerprint, status="done", explanation=explanation)

    async def blue(self, finding: FindingInput) -> Explanation:
        started = time.perf_counter()
        draft = await self._blue_draft(lambda scale: prompts.blue_messages(finding, scale))
        return self._explanation(finding, "C", draft.data, started, draft.completion_tokens)

    async def red_blue(self, finding: FindingInput) -> Explanation:
        started = time.perf_counter()
        draft = await self._blue_draft(lambda scale: prompts.blue_messages(finding, scale))
        tokens = draft.completion_tokens
        rounds: list[RedRound] = []
        for round_no in range(self.max_rewrites + 1):
            current = draft.data
            review = await self._fitted(
                lambda scale, current=current: prompts.red_messages(finding, current, scale),
                RedReview,
                thinking=self.red_thinking,
                reasoning_effort=self.red_reasoning_effort,
                sampling=RED_SAMPLING,
                check=quality.problems,
            )
            tokens += review.completion_tokens
            rounds.append(
                RedRound(
                    round=round_no,
                    verdict=review.data.verdict,
                    issues=[prompts.redact_secrets(issue) for issue in review.data.issues],
                    latency_ms=review.latency_ms,
                )
            )
            if review.data.verdict == "pass" or round_no == self.max_rewrites:
                break
            draft = await self._blue_draft(
                lambda scale, prev=draft.data, rev=review.data: prompts.blue_revise_messages(finding, prev, rev, scale)
            )
            tokens += draft.completion_tokens

        explanation = self._explanation(finding, "D", draft.data, started, tokens)
        explanation.attack_scenario = prompts.redact_secrets(review.data.attack_scenario)
        explanation.red_verdict = review.data.verdict
        explanation.red_rounds = rounds
        explanation.needs_manual_review = review.data.verdict != "pass"
        return explanation

    async def _blue_draft(self, build):
        return await self._fitted(build, BlueDraft, thinking=False, sampling=BLUE_SAMPLING, check=quality.problems)

    async def _fitted(self, build, schema, **kwargs):
        """build(scale) 로 만든 메시지를 보냅니다. 문맥 길이를 넘으면 탐지 결과·수정 지시를 줄여 다시 보냅니다."""
        for i, scale in enumerate(BUDGET_SCALES):
            try:
                return await self.client.chat_json(build(scale), schema, **kwargs)
            except LLMContextOverflow:
                if i == len(BUDGET_SCALES) - 1:
                    raise
                log.warning("입력이 문맥 길이를 넘어 예산 %.0f%% 로 줄여 다시 보냅니다", BUDGET_SCALES[i + 1] * 100)

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
            fix_steps=[
                step.model_copy(update={"title": redact(step.title), "detail": redact(step.detail)})
                for step in draft.fix_steps
            ],
            ai_fix_prompt=redact(draft.ai_fix_prompt),
            false_positive_suspect=draft.false_positive_suspect,
            # 모델이 오탐이 아니라고 하면서 이유를 적는 경우가 있어, 오탐 의심일 때만 남깁니다
            false_positive_reason=redact(draft.false_positive_reason) if draft.false_positive_suspect else None,
            model=self.client.model,
            prompt_version=prompts.PROMPT_VERSION,
            latency_ms=int((time.perf_counter() - started) * 1000),
            completion_tokens=tokens,
        )
