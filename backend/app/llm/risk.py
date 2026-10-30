"""위험도 해석: 문맥 분석 + 위협 정보 → CISA SSVC 결정 (코드로 결정, LLM 이 정하지 않음).

SSVC(Stakeholder-Specific Vulnerability Categorization)는 CISA 가 쓰는 우선순위 결정 방식입니다.
네 가지 질문의 답을 공식 결정표에 넣어 Act·Attend·Track*·Track 중 하나를 고릅니다.
  - Exploitation: 실제 공격(active)·공개된 공격 방법(public poc)·없음(none)
  - Automatable: 공격 단계를 자동화할 수 있나
  - Technical Impact: 시스템을 완전히 장악·전부 유출(total)인가, 일부(partial)인가
  - Mission & Well-Being: 사업과 사람(고객 정보 등)에 미치는 영향

결정표: data/ssvc_cisa_coordinator_2_0_3.csv (CERT/CC SSVC 사본, 라이선스는 data/SSVC-LICENSE.txt)
같은 입력엔 항상 같은 결정이 나와 평가와 감사에 쓸 수 있습니다.
"""

import csv
from pathlib import Path

from app.llm.context import ContextSignals
from app.llm.schemas import (
    ContextAnalysis,
    FindingInput,
    RiskAssessment,
    RiskFactor,
    SsvcDecision,
    ThreatIntelRecord,
)

POLICY_VERSION = "ssvc-cisa-coordinator-2.0.3+ymca-1"
_TABLE_PATH = Path(__file__).parent / "data" / "ssvc_cisa_coordinator_2_0_3.csv"

# EPSS 가 이 값 이상이면 "공개된 공격 방법이 있다"로 봅니다 (30일 내 악용 확률 10% 또는 상위 5%)
EPSS_POC_THRESHOLD = 0.1
EPSS_POC_PERCENTILE = 0.95

# 공격 방법이 널리 알려진 약점 유형 (코드·설정 탐지는 CVE 가 없어 이것으로 공개 공격 방법 여부를 봅니다)
WELL_KNOWN_CWE = {
    "CWE-79", "CWE-89", "CWE-78", "CWE-77", "CWE-94", "CWE-22", "CWE-918", "CWE-502", "CWE-352",
    "CWE-284", "CWE-285", "CWE-287", "CWE-306", "CWE-639", "CWE-862", "CWE-863", "CWE-798", "CWE-200", "CWE-1321",
}  # fmt: skip
# 악용되면 시스템 장악·데이터 전부 유출로 이어지는 유형
TOTAL_IMPACT_CWE = {
    "CWE-78", "CWE-77", "CWE-94", "CWE-95", "CWE-502", "CWE-89", "CWE-287", "CWE-288", "CWE-306",
    "CWE-285", "CWE-862", "CWE-863", "CWE-639", "CWE-798", "CWE-522", "CWE-284",
}  # fmt: skip

_ORDER: tuple[SsvcDecision, ...] = ("track", "track*", "attend", "act")
_PRIORITY = {"act": "now", "attend": "soon", "track*": "later", "track": "later"}
_LABEL = {
    "act": "지금 바로 고치세요",
    "attend": "이번 주 안에 고치세요",
    "track*": "주의해서 지켜보세요",
    "track": "정해진 일정에 맞춰 고치세요",
}
_BASE_SCORE = {"act": 85, "attend": 65, "track*": 40, "track": 15}
_DATA_KO = {"credentials": "계정·키", "personal": "고객 개인정보", "payment": "결제 정보", "business": "업무 데이터"}


def _load_table() -> dict[tuple[str, str, str, str], SsvcDecision]:
    with _TABLE_PATH.open(encoding="utf-8") as f:
        rows = list(csv.reader(f))[1:]
    return {(r[1], r[2], r[3], r[4]): r[5] for r in rows}


SSVC_TABLE = _load_table()


def assess(
    finding: FindingInput,
    analysis: ContextAnalysis,
    signals: ContextSignals,
    intel: dict[str, ThreatIntelRecord] | None = None,
) -> RiskAssessment:
    records = [intel[c] for c in finding.refs.cve if intel and c in intel]
    exploitation, why_exploit = _exploitation(finding, analysis, signals, records)
    automatable, why_auto = _automatable(finding, analysis, exploitation)
    impact, why_impact = _technical_impact(finding, signals)
    mission, why_mission = _mission(finding, analysis)

    decision = SSVC_TABLE[(exploitation, automatable, impact, mission)]
    factors = [
        RiskFactor(name="exploitation", value=exploitation, reason=why_exploit),
        RiskFactor(name="automatable", value=automatable, reason=why_auto),
        RiskFactor(name="technical_impact", value=impact, reason=why_impact),
        RiskFactor(name="mission_impact", value=mission, reason=why_mission),
    ]
    for cap, reason in _caps(finding, analysis, signals):
        if _ORDER.index(decision) > _ORDER.index(cap):
            factors.append(RiskFactor(name="cap", value=f"{decision}→{cap}", reason=reason))
            decision = cap
    if signals.suppressed:
        factors.append(
            RiskFactor(name="note", value="suppressed", reason="숨김 주석·설정으로 경고만 가려 두었습니다. 문제는 그대로입니다")
        )

    return RiskAssessment(
        decision=decision,
        priority=_PRIORITY[decision],
        score=_score(decision, exploitation, mission, records),
        exploitation=exploitation,
        automatable=automatable,
        technical_impact=impact,
        mission_impact=mission,
        summary=f"{_LABEL[decision]}. {why_exploit}",
        factors=factors,
        intel=records,
        policy=POLICY_VERSION,
    )


def _exploitation(finding, analysis, signals, records) -> tuple[str, str]:
    if kev := next((r for r in records if r.kev), None):
        return "active", f"{kev.cve}는 실제 공격에 쓰인 것이 확인된 취약점입니다(CISA KEV {kev.kev_date_added or ''})".replace(" )", ")")
    if finding.category == "secret" and analysis.exposure == "public" and not signals.likely_public_key:
        return "active", "공개된 곳에 드러난 키는 자동 수집 봇이 곧바로 찾아 악용합니다"
    top = max(records, key=lambda r: r.epss or 0, default=None)
    if top and top.epss is not None and (top.epss >= EPSS_POC_THRESHOLD or (top.epss_percentile or 0) >= EPSS_POC_PERCENTILE):
        return "public poc", f"{top.cve}는 30일 안에 악용될 확률이 {top.epss:.0%}로 높은 편입니다(EPSS)"
    if finding.category != "dependency" and (known := sorted(set(finding.refs.cwe) & WELL_KNOWN_CWE)):
        return "public poc", f"{known[0]} 유형은 공격 방법이 널리 알려져 있습니다"
    return "none", "실제 공격이나 공개된 공격 방법은 확인되지 않았습니다"


def _automatable(finding, analysis, exploitation) -> tuple[str, str]:
    if analysis.exposure == "public" and analysis.reachable == "yes":
        return "yes", "로그인 없이 인터넷에서 바로 닿아, 공격을 자동으로 반복할 수 있습니다"
    if finding.category == "secret" and exploitation == "active":
        return "yes", "드러난 키는 사람이 개입하지 않아도 자동으로 수집·사용됩니다"
    reason = {
        "authenticated": "로그인한 사용자만 닿는 곳이라 자동화가 어렵습니다",
        "internal": "내부망에서만 닿습니다",
        "not_deployed": "실제 서비스에 배포되지 않는 코드입니다",
    }.get(analysis.exposure, "외부에서 바로 닿는지 확인되지 않았습니다")
    return "no", reason


def _technical_impact(finding, signals) -> tuple[str, str]:
    total = sorted(set(finding.refs.cwe) & TOTAL_IMPACT_CWE)
    if finding.category == "secret" and not signals.likely_public_key:
        return "total", "키를 가진 사람은 그 서비스의 권한을 그대로 쓸 수 있습니다"
    if total:
        return "total", f"{total[0]} 유형은 데이터 전체 유출이나 시스템 장악으로 이어질 수 있습니다"
    if finding.severity == "critical":
        return "total", "스캐너가 치명적(critical)으로 분류했습니다"
    return "partial", "피해가 일부 기능·데이터에 그칩니다"


def _mission(finding, analysis) -> tuple[str, str]:
    data = set(analysis.data_at_risk)
    if analysis.exposure == "not_deployed" or analysis.runtime == "test":
        return "low", "실제 서비스에 영향을 주지 않는 코드입니다"
    if sensitive := [d for d in ("credentials", "personal", "payment") if d in data]:
        return "high", f"{', '.join(_DATA_KO[d] for d in sensitive)}이(가) 걸려 있습니다"
    if "business" in data or finding.severity in ("critical", "high"):
        return "medium", "서비스 운영에 영향을 줄 수 있습니다"
    if data == {"none"}:
        return "low", "민감한 데이터가 걸려 있지 않습니다"
    return "medium", "어떤 데이터가 걸려 있는지 확인되지 않아 중간으로 봅니다"


def _caps(finding, analysis, signals) -> list[tuple[SsvcDecision, str]]:
    caps: list[tuple[SsvcDecision, str]] = []
    if analysis.vex_status == "not_affected" and analysis.confidence != "low":
        caps.append(("track", "분석 결과 실제로는 영향이 없습니다(OpenVEX not_affected)"))
    if signals.test_or_example or analysis.exposure == "not_deployed":
        caps.append(("track", "테스트·예시 코드라 실제 서비스에 배포되지 않습니다"))
    if signals.likely_public_key:
        caps.append(("track", "원래 공개용으로 만든 키로 보입니다"))
    return caps


def _score(decision, exploitation, mission, records) -> int:
    bonus = {"active": 8, "public poc": 4, "none": 0}[exploitation] + (4 if mission == "high" else 0)
    bonus += round(max((r.epss_percentile or 0 for r in records), default=0) * 2)
    return min(100, _BASE_SCORE[decision] + min(bonus, 14))
