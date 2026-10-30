"""LLM 단계의 입력·출력 규격.

- 입력 `FindingInput`은 DB `finding` 테이블(#7)과 칼럼 이름을 맞췄습니다. 보안엔진의 LLM 입력 꾸러미(#15)를
  이 모양으로 바꿔 넣으면 됩니다.
- 출력 `Explanation`은 DB `explanation` 테이블과 칼럼 이름을 맞추고, Red–Blue 결과를 더했습니다.
- `BlueDraft`·`RedReview`는 모델이 직접 만드는 JSON입니다. vLLM에 JSON 스키마로 넘겨 형식을 강제합니다.
"""

from typing import Literal

from pydantic import BaseModel, Field

Severity = Literal["critical", "high", "medium", "low", "info"]
Category = Literal["dependency", "code", "secret", "config"]
Priority = Literal["now", "soon", "later"]
Verdict = Literal["pass", "bypass", "breaks_function", "incomplete"]
Variant = Literal["C", "D"]  # 평가 설계: C = Blue 1회, D = C + Red–Blue 검증


# ── 입력 ──


class FindingRefs(BaseModel):
    cve: list[str] = Field(default_factory=list)
    cwe: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)


class FindingInput(BaseModel):
    fingerprint: str = Field(min_length=1, max_length=200)
    tool: str = Field(max_length=50)
    category: Category
    rule_id: str = Field(max_length=200)
    title: str = Field(max_length=500)
    severity: Severity
    file_path: str | None = Field(default=None, max_length=500)
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    package_name: str | None = Field(default=None, max_length=200)
    package_ecosystem: str | None = Field(default=None, max_length=50)
    installed_version: str | None = Field(default=None, max_length=100)
    fixed_version: str | None = Field(default=None, max_length=100)
    refs: FindingRefs = Field(default_factory=FindingRefs)
    # 보안엔진이 비밀값을 가린 코드 조각. LLM 모듈에서도 한 번 더 가립니다
    snippet: str | None = Field(default=None, max_length=4000)
    # 주변 코드 (맥락). 없으면 snippet만으로 판단합니다
    context: str | None = Field(default=None, max_length=8000)


# ── 모델이 만드는 JSON ──


class FixStep(BaseModel):
    title: str = Field(description="단계 이름, 한 줄", max_length=120)
    detail: str = Field(description="비개발자도 따라 할 수 있는 구체적인 방법", max_length=600)


class BlueDraft(BaseModel):
    summary: str = Field(description="무엇이 문제인지 한 문장", max_length=200)
    why_risky: str = Field(description="방치하면 어떤 일이 생기는지, 비개발자 눈높이로", max_length=800)
    priority: Priority = Field(description="now: 바로 악용 가능·비밀값 노출, soon: 조건부, later: 영향 낮음")
    fix_steps: list[FixStep] = Field(min_length=1, max_length=6)
    ai_fix_prompt: str = Field(
        description="AI 코딩툴에 그대로 붙여 넣을 수정 지시. 파일 경로·줄·규칙 ID만 쓰고 코드 원문과 비밀값은 넣지 않음",
        max_length=2000,
    )
    false_positive_suspect: bool = Field(description="테스트 코드·예시 값처럼 오탐으로 보이면 true")
    false_positive_reason: str | None = Field(default=None, max_length=400)


class RedReview(BaseModel):
    verdict: Verdict = Field(
        description="pass: 수정 지시대로 하면 막힘, bypass: 우회 가능, breaks_function: 기능이 깨짐, incomplete: 빠지거나 모호한 단계"
    )
    attack_scenario: str = Field(
        description="수정 전, 공격자가 이 문제를 어떻게 악용하는지 1~2문장. 공격 코드·명령어는 쓰지 않음",
        max_length=400,
    )
    issues: list[str] = Field(
        default_factory=list, description="pass가 아니면 수정 지시의 구멍을 구체적으로", max_length=5
    )


# ── 최종 결과 ──


class RedRound(BaseModel):
    round: int
    verdict: Verdict
    issues: list[str]
    latency_ms: int


class Explanation(BaseModel):
    fingerprint: str
    variant: Variant
    summary: str
    why_risky: str
    priority: Priority
    fix_steps: list[FixStep]
    ai_fix_prompt: str
    false_positive_suspect: bool
    false_positive_reason: str | None = None
    # Red–Blue(D)에서만 채워집니다
    attack_scenario: str | None = None
    red_verdict: Verdict | None = None
    red_rounds: list[RedRound] = Field(default_factory=list)
    # Red 검토를 끝내 통과하지 못하면 대시보드에 경고로 띄웁니다
    needs_manual_review: bool = False
    model: str
    prompt_version: str
    latency_ms: int
    completion_tokens: int


class ExplainResult(BaseModel):
    fingerprint: str
    # DB finding.explain_status 와 같은 값
    status: Literal["done", "failed"]
    explanation: Explanation | None = None
    error_code: Literal["LLM_UNAVAILABLE", "LLM_BAD_OUTPUT", "LLM_ERROR"] | None = None
    error: str | None = None
