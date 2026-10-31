"""탐지 결과 1건을 해석하는 파이프라인 (docs/system-flow.md ③ 해석 · GPU).

  ① 문맥 분석: 규칙 신호(context.py) + LLM 판단. LLM 이 실패하면 규칙 신호만으로 판단
  ② 위험도: 문맥 분석 + KEV·EPSS → CISA SSVC 결정 (risk.py, 코드로 결정)
  ③ 대응 가이드: 사용자 OS·배포 환경에 맞는 명령 (remediation.py, 검증된 템플릿)
  ④ Blue: ①~③을 근거로 설명·수정 지시 작성 (평가 C 는 여기까지)
  ⑤ Red (red_blue 모드, 평가 D): 공격자 관점 판정 → pass 가 아니면 지적을 붙여 Blue 재작성 (최대 max_rewrites)
     끝까지 pass 가 아니면 마지막 수정 지시에 needs_manual_review 를 붙여 내보냅니다.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
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
from app.llm.context import ContextSignals, analysis_from_signals, collect_signals
from app.llm.intel import ThreatIntel
from app.llm.remediation import build_guide
from app.llm.risk import assess
from app.llm.schemas import (
    BROWSER_SECRET_REVIEW,
    BlueDraft,
    ContextAnalysis,
    ExplainResult,
    Explanation,
    FindingInput,
    RedReview,
    RedRound,
    RemediationGuide,
    RiskAssessment,
    ThreatIntelRecord,
    UserEnvironment,
)

log = logging.getLogger(__name__)

Mode = Literal["blue", "red_blue"]

# 문맥 길이를 넘으면 입력 예산을 이 비율로 차례로 줄여 다시 보냅니다
BUDGET_SCALES = (1.0, 0.5, 0.25)
# 출력 한도는 프롬프트 길이 예산(prompts.py)과 함께 문맥 12K(serve.sh --max-model-len) 안에 들어가게 정했습니다.
# Blue·문맥 분석은 생각 모드를 끄고 바로 씁니다. Red 는 우회 경로를 따져야 해서 짧게 생각하게 합니다
BLUE_SAMPLING = Sampling(max_tokens=2500)
RED_SAMPLING = Sampling(max_tokens=3500)
CONTEXT_SAMPLING = Sampling(temperature=0.3, max_tokens=900)


def skip_reason(finding: FindingInput) -> str | None:
    """설명하지 않을 항목이면 이유를 돌려줍니다.

    change 가 resolved 여도 status 가 runtime_check_needed 면 설명합니다. 코드에서 지운 비밀값처럼
    키 재발급 같은 조치가 아직 남은 경우입니다.
    """
    if finding.status == "code_resolved":
        return "코드에서 이미 해결된 항목입니다"
    if finding.status == "out_of_scope" or (finding.status is None and finding.change == "unverifiable"):
        # 재검사에서 도구가 실패해 확인하지 못한 항목. "지금 문제 있음"으로 설명하면 안 됩니다
        # (리포트 app/reports/plain.py 의 finding_state 와 같은 기준)
        return "이번 검사에서 확인하지 못했습니다. 다시 검사가 필요합니다"
    if finding.status is None and finding.change == "resolved":
        return "재검사에서 해결된 항목입니다"
    return None


@dataclass
class Briefing:
    """Blue·Red 앞 단계(①~③)의 결과. 탐지 결과와 함께 모델에 넘기고 최종 결과에도 담습니다."""

    signals: ContextSignals
    analysis: ContextAnalysis
    risk: RiskAssessment
    environment: UserEnvironment | None = None
    guide: RemediationGuide | None = None
    tokens: int = 0

    def render(self) -> str:
        return prompts.render_briefing(self.analysis, self.risk, self.environment, self.guide)


class Explainer:
    def __init__(
        self,
        client: LLMClient,
        max_rewrites: int = 2,
        red_thinking: bool = True,
        red_reasoning_effort: str = "low",
        analyze_context: bool = False,
        intel: ThreatIntel | None = None,
    ) -> None:
        self.client = client
        self.max_rewrites = max_rewrites
        self.red_thinking = red_thinking
        self.red_reasoning_effort = red_reasoning_effort
        # False 면 문맥 분석을 LLM 없이 규칙 신호로만 합니다 (호출 1회 절약)
        self.analyze_context = analyze_context
        self.intel = intel

    async def aclose(self) -> None:
        await self.client.aclose()
        if close := getattr(self.intel, "aclose", None):
            await close()

    async def explain_many(
        self, findings: list[FindingInput], mode: Mode, environment: UserEnvironment | None = None
    ) -> list[ExplainResult]:
        """여러 건을 동시에 보냅니다. GPU가 묶어서 처리해야 L4에서 전체 시간이 줄어듭니다.

        한 건이 실패해도 나머지는 그대로 돌려줍니다. 코드에서 이미 해결된 항목은 GPU를 쓰지 않고 건너뜁니다.
        """
        intel = await self._intel_for([f for f in findings if not skip_reason(f)])
        run = self.blue if mode == "blue" else self.red_blue
        return list(await asyncio.gather(*(self._safe(run, f, intel, environment) for f in findings)))

    async def _intel_for(self, findings: list[FindingInput]) -> dict[str, ThreatIntelRecord]:
        """요청 안의 CVE 를 한 번에 조회합니다 (EPSS 는 100개씩 묶어 조회)."""
        cves = sorted({c for f in findings for c in f.refs.cve})
        if not self.intel or not cves:
            return {}
        return await self.intel.lookup(cves)

    async def _safe(self, run, finding, intel, environment) -> ExplainResult:
        if reason := skip_reason(finding):
            return ExplainResult(fingerprint=finding.fingerprint, status="skipped", reason=reason, covers=finding.covers)
        try:
            explanation = await run(finding, intel, environment)
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
            return ExplainResult(
                fingerprint=finding.fingerprint, status="failed", error_code=code, error=str(exc), covers=finding.covers
            )
        return ExplainResult(
            fingerprint=finding.fingerprint, status="done", explanation=explanation, covers=finding.covers
        )

    async def brief(
        self,
        finding: FindingInput,
        intel: dict[str, ThreatIntelRecord] | None = None,
        environment: UserEnvironment | None = None,
    ) -> Briefing:
        """①~③: 문맥 분석, 위험도 결정, 대응 가이드."""
        signals = collect_signals(finding)
        analysis, tokens = await self._analyze(finding, signals)
        if intel is None:
            intel = await self._intel_for([finding])
        risk = assess(finding, analysis, signals, intel)
        guide = build_guide(finding, environment)
        return Briefing(signals, analysis, risk, environment, guide=guide, tokens=tokens)

    async def _analyze(self, finding: FindingInput, signals: ContextSignals) -> tuple[ContextAnalysis, int]:
        if not self.analyze_context:
            return analysis_from_signals(finding, signals), 0
        try:
            result = await self._fitted(
                lambda scale: prompts.context_messages(finding, signals, scale),
                ContextAnalysis,
                thinking=False,
                sampling=CONTEXT_SAMPLING,
                check=quality.problems,
            )
        except LLMUnavailable:
            raise
        except LLMError as exc:
            # 문맥 분석이 안 돼도 설명은 계속합니다. 규칙 신호로 판단하고 확신도는 low 로 둡니다
            log.warning("문맥 분석 실패, 규칙 신호로 대신합니다 %s: %s", finding.fingerprint, exc)
            return analysis_from_signals(finding, signals), 0
        return result.data, result.completion_tokens

    async def blue(self, finding: FindingInput, intel=None, environment: UserEnvironment | None = None) -> Explanation:
        started = time.perf_counter()
        briefing = await self.brief(finding, intel, environment)
        extra = briefing.render()
        draft = await self._blue_draft(lambda scale: prompts.blue_messages(finding, scale, extra))
        tokens = briefing.tokens + draft.completion_tokens
        return self._explanation(finding, "C", draft.data, briefing, started, tokens)

    async def red_blue(
        self, finding: FindingInput, intel=None, environment: UserEnvironment | None = None
    ) -> Explanation:
        started = time.perf_counter()
        briefing = await self.brief(finding, intel, environment)
        extra = briefing.render()
        draft = await self._blue_draft(lambda scale: prompts.blue_messages(finding, scale, extra))
        tokens = briefing.tokens + draft.completion_tokens
        rounds: list[RedRound] = []
        for round_no in range(self.max_rewrites + 1):
            current = draft.data
            review = await self._fitted(
                lambda scale, current=current: prompts.red_messages(finding, current, scale, extra),
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
                lambda scale, prev=draft.data, rev=review.data: prompts.blue_revise_messages(
                    finding, prev, rev, scale, extra
                )
            )
            tokens += draft.completion_tokens

        explanation = self._explanation(finding, "D", draft.data, briefing, started, tokens)
        explanation.attack_scenario = prompts.redact_secrets(review.data.attack_scenario)
        explanation.red_verdict = review.data.verdict
        explanation.red_rounds = rounds
        # 브라우저로 나가는 키처럼 Red 가 통과시켜도 사람이 권한을 확인해야 하는 경우는 그대로 둡니다 (#100)
        explanation.needs_manual_review = review.data.verdict != "pass" or explanation.needs_manual_review
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
        self, finding: FindingInput, variant: str, draft: BlueDraft, briefing: Briefing, started: float, tokens: int
    ) -> Explanation:
        # 모델이 실수로 비밀값을 다시 적어도 밖으로 나가지 않게 가립니다 (수정 지시는 외부 AI 코딩툴로 갑니다)
        redact = prompts.redact_secrets
        analysis = briefing.analysis.model_copy(
            update={
                "evidence": [redact(e) for e in briefing.analysis.evidence],
                "attacker_needs": [redact(a) for a in briefing.analysis.attacker_needs],
            }
        )
        return Explanation(
            fingerprint=finding.fingerprint,
            variant=variant,
            summary=redact(draft.summary),
            why_risky=redact(draft.why_risky),
            # 우선순위는 모델이 아니라 SSVC 결정에서 나옵니다
            priority=briefing.risk.priority,
            fix_steps=[
                step.model_copy(update={"title": redact(step.title), "detail": redact(step.detail)})
                for step in draft.fix_steps
            ],
            ai_fix_prompt=redact(draft.ai_fix_prompt),
            false_positive_suspect=draft.false_positive_suspect,
            needs_manual_review=briefing.signals.browser_secret,
            manual_review_reason=BROWSER_SECRET_REVIEW if briefing.signals.browser_secret else None,
            # 모델이 오탐이 아니라고 하면서 이유를 적는 경우가 있어, 오탐 의심일 때만 남깁니다
            false_positive_reason=redact(draft.false_positive_reason) if draft.false_positive_suspect else None,
            context=analysis,
            risk=briefing.risk,
            guide=briefing.guide,
            model=self.client.model,
            prompt_version=prompts.PROMPT_VERSION,
            latency_ms=int((time.perf_counter() - started) * 1000),
            completion_tokens=tokens,
        )
