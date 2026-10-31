"""LLM 단계의 입력·출력 규격.

- 입력 `FindingInput`은 DB `finding` 테이블(#7)과 칼럼 이름을 맞췄습니다. 보안엔진의 LLM 입력 꾸러미(#15)는
  `engine_adapter.from_engine_item`으로 이 모양으로 바꿉니다. 엔진만 아는 정보(flags, fix_hint, 상태)도 받습니다.
- 출력 `Explanation`은 DB `explanation` 테이블과 칼럼 이름을 맞추고, Red–Blue 결과를 더했습니다.
- `BlueDraft`·`RedReview`는 모델이 직접 만드는 JSON입니다. vLLM에 JSON 스키마로 넘겨 형식을 강제합니다.
"""

from typing import Literal

from pydantic import BaseModel, Field

# 보안엔진은 심각도 정보가 없는 결과를 unknown 으로 둡니다
Severity = Literal["critical", "high", "medium", "low", "info", "unknown"]
Category = Literal["dependency", "code", "secret", "config"]
Priority = Literal["now", "soon", "later"]
Verdict = Literal["pass", "bypass", "breaks_function", "incomplete"]
# 보안엔진의 4가지 상태와 재검사 변화
EngineStatus = Literal["code_issue", "code_resolved", "runtime_check_needed", "out_of_scope"]
Change = Literal["new", "persisting", "resolved", "unverifiable"]
Variant = Literal["C", "D"]  # 평가 설계: C = Blue 1회, D = C + Red–Blue 검증


# ── 입력 ──


class FindingRefs(BaseModel):
    cve: list[str] = Field(default_factory=list)
    cwe: list[str] = Field(default_factory=list)
    urls: list[str] = Field(default_factory=list)


class FindingFlag(BaseModel):
    """보안엔진이 붙인 주의 표시. 예: suppressed_by_comment(숨김 주석으로 우회 시도), rotate_secret, likely_public_key"""

    flag: str = Field(max_length=50)
    note: str = Field(default="", max_length=300)


class FixHint(BaseModel):
    """보안엔진이 계산한 고치는 힌트. 의존성이면 한 번에 다 고치는 버전과 업그레이드 명령이 들어 있습니다."""

    kind: str | None = Field(default=None, max_length=50)
    text: str | None = Field(default=None, max_length=1000)
    package: str | None = Field(default=None, max_length=200)
    ecosystem: str | None = Field(default=None, max_length=50)
    current_version: str | None = Field(default=None, max_length=100)
    target_version: str | None = Field(default=None, max_length=100)
    lockfile: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=300)
    # 추천 버전을 OSV에 다시 조회한 결과 (#109). clean=알려진 취약점 없음, vulnerable=남아 있음, unknown=확인 못 함
    target_check: Literal["clean", "vulnerable", "unknown"] | None = None
    autofix: str | None = Field(default=None, max_length=2000)


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
    # 아래는 보안엔진 LLM 입력 꾸러미에서 옵니다 (DB finding 에는 없음)
    what: str | None = Field(default=None, max_length=2000, description="규칙 설명. 엔진의 what")
    flags: list[FindingFlag] = Field(default_factory=list, max_length=10)
    fix_hint: FixHint | None = None
    status: EngineStatus | None = None
    change: Change | None = None
    # 여러 탐지 결과를 한 번에 설명할 때(예: 같은 패키지의 의존성 취약점) 묶인 결과들의 fingerprint.
    # 모델에는 넘기지 않고, 결과를 DB의 각 finding 에 나눠 저장할 때 씁니다
    covers: list[str] = Field(default_factory=list, max_length=500)


# ── 모델이 만드는 JSON ──

Runtime = Literal["browser", "server", "database", "build", "test", "config", "dependency", "unknown"]
Exposure = Literal["public", "authenticated", "internal", "not_deployed", "unknown"]
DataKind = Literal["credentials", "personal", "payment", "business", "none", "unknown"]
# OpenVEX 상태·사유 (https://github.com/openvex/spec). 나중에 VEX 문서로 내보낼 수 있게 같은 용어를 씁니다
VexStatus = Literal["affected", "not_affected", "under_investigation"]
VexJustification = Literal[
    "component_not_present",
    "vulnerable_code_not_present",
    "vulnerable_code_not_in_execute_path",
    "vulnerable_code_cannot_be_controlled_by_adversary",
    "inline_mitigations_already_exist",
]


class ContextAnalysis(BaseModel):
    """탐지 결과가 실제 서비스에서 악용될 수 있는 환경인지에 대한 판단 (문맥 분석)."""

    runtime: Runtime = Field(description="이 코드가 실행되는 곳")
    exposure: Exposure = Field(description="누가 이 코드·값에 닿을 수 있나")
    reachable: Literal["yes", "no", "unknown"] = Field(description="공격자 입력이 문제 지점까지 도달하나")
    data_at_risk: list[DataKind] = Field(description="악용되면 걸리는 데이터", min_length=1, max_length=3)
    attacker_needs: list[str] = Field(default_factory=list, description="공격자가 갖춰야 할 조건", max_length=3)
    evidence: list[str] = Field(description="판단 근거 (코드·경로에서 본 것)", min_length=1, max_length=3)
    vex_status: VexStatus
    vex_justification: VexJustification | None = None
    confidence: Literal["high", "medium", "low"]


class FixStep(BaseModel):
    title: str = Field(description="단계 이름, 한 줄", max_length=120)
    detail: str = Field(description="비개발자도 따라 할 수 있는 구체적인 방법", max_length=600)


class BlueDraft(BaseModel):
    summary: str = Field(description="무엇이 문제인지 한 문장", max_length=200)
    why_risky: str = Field(description="방치하면 어떤 일이 생기는지, 비개발자 눈높이로", max_length=800)
    # 우선순위는 모델이 정하지 않습니다. risk.py 가 문맥 분석·KEV·EPSS로 SSVC 결정을 내립니다
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


# ── 위험도 해석 (risk.py, 코드로 결정) ──

SsvcDecision = Literal["act", "attend", "track*", "track"]


class RiskFactor(BaseModel):
    name: str  # SSVC 결정 요소 또는 보정 이름
    value: str
    reason: str  # 비개발자가 읽을 한국어 근거


class ThreatIntelRecord(BaseModel):
    cve: str
    # CISA KEV: True=실제 공격에 쓰인 것이 확인됨, False=목록을 받아 확인했는데 없음, None=목록을 받지 못해 모름 (#93)
    kev: bool | None = False
    kev_date_added: str | None = None
    kev_checked_at: str | None = None  # 판정에 쓴 KEV 목록을 받은 시각 (UTC, ISO 8601)
    kev_stale: bool = False  # 새로 받지 못해 보관 기간이 지난 목록으로 판정했는지
    epss: float | None = None  # FIRST EPSS: 30일 안에 악용될 확률 (0~1)
    epss_percentile: float | None = None


class RiskAssessment(BaseModel):
    decision: SsvcDecision
    priority: Priority
    score: int = Field(ge=0, le=100)  # 같은 결정 안에서 정렬용
    exploitation: Literal["none", "public poc", "active"]
    automatable: Literal["yes", "no"]
    technical_impact: Literal["partial", "total"]
    mission_impact: Literal["low", "medium", "high"]
    summary: str  # 한 줄 결론
    factors: list[RiskFactor]
    intel: list[ThreatIntelRecord] = Field(default_factory=list)
    policy: str  # 결정 규칙 버전 (평가·감사용)


# ── OS별 대응 가이드 (remediation.py, 검증된 템플릿) ──

TargetOS = Literal["windows", "macos", "linux"]
PackageManager = Literal["npm", "pnpm", "yarn", "bun", "pip", "uv", "poetry", "composer", "bundler", "go", "cargo"]


class CommandBlock(BaseModel):
    os: TargetOS
    shell: Literal["powershell", "zsh", "bash"]
    lines: list[str]


class GuideAction(BaseModel):
    id: str  # upgrade_dependency, rotate_secret, ...
    title: str
    why: str
    commands: list[CommandBlock] = Field(default_factory=list)  # OS별. OS와 무관한 작업이면 비어 있음
    manual_steps: list[str] = Field(default_factory=list)  # 대시보드에서 하는 일 등
    links: list[str] = Field(default_factory=list)
    optional: bool = False


class RemediationGuide(BaseModel):
    package_manager: PackageManager | None = None
    actions: list[GuideAction] = Field(default_factory=list)


# ── 최종 결과 ──


class RedRound(BaseModel):
    round: int
    verdict: Verdict
    issues: list[str]
    latency_ms: int


# 브라우저로 전달되는 비밀값: 코드만 보고는 키 권한(검색 전용인지, 쓰기·관리 권한인지)을 알 수 없습니다 (#100)
BROWSER_SECRET_REVIEW = (
    "이 키는 페이지와 함께 방문자 브라우저로 전달됩니다. 검색 전용처럼 공개해도 되는 키인지, "
    "쓰기·관리 권한이 있는 키인지 키를 발급한 서비스 관리 화면에서 직접 확인해야 합니다."
)


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
    # 사람 확인이 필요한 이유 (Red 미통과 말고 다른 이유일 때). 예) 브라우저로 나가는 키라 권한 확인 필요
    manual_review_reason: str | None = None
    # 문맥 분석 (LLM 또는 규칙 신호), 위험도 (SSVC 결정), OS별 명령
    context: ContextAnalysis | None = None
    risk: RiskAssessment | None = None
    guide: RemediationGuide | None = None
    model: str
    prompt_version: str
    latency_ms: int
    completion_tokens: int


class ExplainResult(BaseModel):
    fingerprint: str
    # done·failed 는 DB finding.explain_status 와 같은 값. skipped 는 코드에서 이미 해결된 항목이라 부르지 않은 것
    status: Literal["done", "failed", "skipped"]
    explanation: Explanation | None = None
    reason: str | None = None
    # 이 결과가 함께 설명하는 탐지 결과들 (패키지 단위 묶음일 때)
    covers: list[str] = Field(default_factory=list)
    error_code: Literal["LLM_UNAVAILABLE", "LLM_BAD_OUTPUT", "LLM_INPUT_TOO_LONG", "LLM_ERROR"] | None = None
    error: str | None = None
