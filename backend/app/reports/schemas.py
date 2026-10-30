"""리포트 입력·출력 규격.

입력
- 탐지 결과는 LLM 단계와 같은 `FindingInput`, 해석 결과는 `/api/llm/explain` 응답의 `results`(`ExplainResult`)를
  그대로 받습니다. DB 테이블(#7)이 생기면 라우터에서 DB를 읽어 같은 모양으로 넘기면 됩니다.
- 시각은 모두 시간대가 있어야 합니다(`AwareDatetime`). 시간대가 없으면 서버마다 해석이 달라 신고 기한이 틀어집니다.
- 사고 정보 `IncidentInput`은 사용자가 대시보드의 신고 도우미 화면에서 채웁니다. 모르는 칸은 비워 두면
  리포트의 "아직 채워야 할 칸"(`missing`)에 나옵니다.

출력
- 세 리포트 모두 같은 `Report` 구조입니다. 화면(JSON), 마크다운, 인쇄용 HTML이 같은 구조에서 나옵니다.
"""

from datetime import datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field

from app.llm.schemas import ExplainResult, FindingInput

ReportKind = Literal["plain", "incident_24h", "privacy_72h"]
Tone = Literal["danger", "warning", "ok", "info", "muted"]
ReportFormat = Literal["json", "markdown", "html"]


# ── 입력 ──


class NotChecked(BaseModel):
    """이번 검사에서 확인하지 못한 영역. 보안엔진 LLM 입력의 `not_checked`를 그대로 받습니다 (#28)."""

    tool: str = Field(max_length=50)
    category: str | None = Field(default=None, max_length=50)
    reason: str = Field(default="", max_length=1000)


class ScanContext(BaseModel):
    """검사 한 번의 정보. 72시간 타이머는 첫 발견 시각(detected_at)에 시작합니다."""

    site_name: str = Field(min_length=1, max_length=200)
    site_url: str | None = Field(default=None, max_length=500)
    repo: str | None = Field(default=None, max_length=200)
    scanned_at: AwareDatetime
    detected_at: AwareDatetime | None = Field(
        default=None, description="처음 취약점이 발견된 시각. 72시간 타이머 시작점"
    )
    resolved_at: AwareDatetime | None = Field(default=None, description="재검사를 통과한 시각. 있으면 완료 리포트")
    not_checked: list[NotChecked] = Field(
        default_factory=list, max_length=20, description="도구 실패·lockfile 없음 등으로 검사하지 못한 영역"
    )


class PlainReportRequest(BaseModel):
    scan: ScanContext
    findings: list[FindingInput] = Field(max_length=500)
    explain_results: list[ExplainResult] = Field(default_factory=list, max_length=500)


class Organization(BaseModel):
    name: str | None = Field(default=None, max_length=200, description="회사(기관) 이름")
    service_name: str | None = Field(default=None, max_length=200)
    service_url: str | None = Field(default=None, max_length=500)
    department: str | None = Field(default=None, max_length=100, description="대응 담당 부서")
    contact_name: str | None = Field(default=None, max_length=50)
    contact_phone: str | None = Field(default=None, max_length=30)
    contact_email: str | None = Field(default=None, max_length=200)


IncidentType = Literal[
    "hacking",  # 해킹(무단 침입)
    "malware",  # 악성코드·랜섬웨어
    "ddos",  # 서비스 거부 공격
    "defacement",  # 홈페이지 위·변조
    "account_takeover",  # 관리자·사용자 계정 탈취
    "data_leak",  # 데이터 유출
    "other",
]
IncidentStatus = Literal["ongoing", "contained", "recovered"]


class ActionTaken(BaseModel):
    at: AwareDatetime | None = None
    action: str = Field(min_length=1, max_length=500)


LeakState = Literal["confirmed", "suspected", "none"]


class PersonalInfoBreach(BaseModel):
    leaked: LeakState = "suspected"
    affected_count: int | None = Field(default=None, ge=0, description="유출된 정보주체 수")
    count_is_estimate: bool = False
    items: list[str] = Field(default_factory=list, max_length=30, description="유출 항목. 예: 이름, 이메일, 비밀번호")
    includes_sensitive: bool = Field(default=False, description="민감정보(건강·정치 성향 등) 포함")
    includes_unique_id: bool = Field(default=False, description="고유식별정보(주민등록번호·여권번호 등) 포함")
    external_unauthorized_access: bool = Field(default=False, description="외부의 불법 접근으로 유출")
    recovered_low_risk: bool = Field(
        default=False, description="유출 경로를 확인하고 회수·삭제해 피해 가능성이 현저히 낮아짐 (신고 예외 사유)"
    )
    subjects_notified: bool = False
    notified_at: AwareDatetime | None = None
    notify_method: str | None = Field(default=None, max_length=200)
    subject_mitigations: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="정보주체가 할 수 있는 피해 최소화 방법. 비우면 항목에 맞춰 제안",
    )
    relief_procedure: str | None = Field(default=None, max_length=1000, description="피해 구제 절차")
    damage_report_contact: str | None = Field(default=None, max_length=300, description="피해 신고 접수 부서·연락처")


class IncidentInput(BaseModel):
    organization: Organization = Field(default_factory=Organization)
    discovered_at: AwareDatetime = Field(description="사고를 알게 된 시각. 24시간·72시간 신고 기한의 시작점")
    occurred_at: AwareDatetime | None = Field(default=None, description="사고가 실제로 일어난 시각 (추정 가능)")
    incident_types: list[IncidentType] = Field(default_factory=list, max_length=7)
    summary: str | None = Field(default=None, max_length=1000, description="무슨 일이 있었는지 한두 문장")
    cause: str | None = Field(default=None, max_length=2000)
    damage: str | None = Field(default=None, max_length=2000)
    affected_systems: list[str] = Field(default_factory=list, max_length=20)
    actions_taken: list[ActionTaken] = Field(default_factory=list, max_length=30)
    status: IncidentStatus = "ongoing"
    is_supplement: bool = Field(default=False, description="이미 한 신고를 보완하는 신고인지")
    related_fingerprints: list[str] = Field(default_factory=list, max_length=50, description="관련 탐지 결과")
    personal_info: PersonalInfoBreach | None = None


class FilingRequest(BaseModel):
    incident: IncidentInput
    # 관련 탐지 결과가 있으면 원인 칸의 근거로 붙입니다 (선택)
    findings: list[FindingInput] = Field(default_factory=list, max_length=100)


# ── 출력 ──


class Badge(BaseModel):
    text: str
    tone: Tone = "info"


class FormField(BaseModel):
    """신고서의 한 칸. 채우지 못한 필수 칸은 value 가 None 이고 missing 에도 올라갑니다."""

    label: str
    value: str | None = None
    required: bool = False
    hint: str | None = None
    auto: bool = Field(default=False, description="사용자가 적지 않아 서비스가 제안한 값. 제출 전 확인 필요")


class Card(BaseModel):
    title: str
    badges: list[Badge] = Field(default_factory=list)
    paragraphs: list[str] = Field(default_factory=list)
    fields: list[FormField] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)


class Section(BaseModel):
    heading: str
    paragraphs: list[str] = Field(default_factory=list)
    fields: list[FormField] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    cards: list[Card] = Field(default_factory=list)


class Deadline(BaseModel):
    label: str
    basis: str = Field(description="법적 근거 또는 서비스 기준")
    starts_at: datetime
    due_at: datetime
    hours: int
    remaining_minutes: int = Field(description="음수면 기한이 지남")
    overdue: bool
    stopped_at: datetime | None = Field(default=None, description="완료되어 타이머가 멈춘 시각")


class Report(BaseModel):
    kind: ReportKind
    title: str
    subtitle: str | None = None
    generated_at: datetime
    status: Badge
    deadline: Deadline | None = None
    sections: list[Section]
    missing: list[str] = Field(default_factory=list, description="제출 전에 채워야 할 필수 칸")
    submit_to: list[str] = Field(default_factory=list, description="제출처 안내")
    disclaimer: str | None = None


class FilingNeed(BaseModel):
    kind: Literal["incident_24h", "privacy_72h"]
    required: bool
    reasons: list[str]
    deadline: Deadline | None = None


class AssessResponse(BaseModel):
    needs: list[FilingNeed]
