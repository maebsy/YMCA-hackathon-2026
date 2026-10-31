"""사고가 의심될 때의 신고서 초안 (72시간 산출물 · 신고서 작성 서포트).

- 침해사고 신고 (24시간, KISA): 시행령이 정한 세 가지 신고 사항을 칸으로 만듭니다.
- 개인정보 유출 신고 (72시간, 개인정보보호위원회·KISA): 유출신고서 항목과 정보주체 통지문 초안을 만듭니다.
- `assess`: 사고 정보만 보고 어떤 신고가 필요한지, 기한이 언제인지 알려 줍니다.

법 문장을 모델이 지어내면 안 되므로 LLM을 쓰지 않고 정해진 항목에 사용자 입력을 채웁니다.
빈 필수 칸은 지어내지 않고 `missing`에 올립니다. 서비스가 대신 제안한 값은 `auto=True`로 표시합니다.
"""

from datetime import datetime

from app.llm.prompts import redact_secrets
from app.llm.schemas import FindingInput
from app.reports import legal
from app.reports.common import deadline, fmt_time, join_or_none, missing_labels
from app.reports.plain import location
from app.reports.schemas import (
    AssessResponse,
    Badge,
    Card,
    FilingNeed,
    FilingRequest,
    FormField,
    IncidentInput,
    PersonalInfoBreach,
    Report,
    Section,
)

# 이 유형이면 외부 공격에 의한 침해사고로 봅니다. 단순 실수로 인한 유출(data_leak만)은 판단이 필요합니다
ATTACK_TYPES = {"hacking", "malware", "ddos", "defacement", "account_takeover"}


# ── 신고 필요 여부 ──


def incident_need(incident: IncidentInput, now: datetime) -> FilingNeed:
    attack = ATTACK_TYPES.intersection(incident.incident_types)
    external = bool(incident.personal_info and incident.personal_info.external_unauthorized_access)
    reasons: list[str] = []
    if attack:
        labels = ", ".join(legal.INCIDENT_TYPE_LABEL[t] for t in incident.incident_types if t in attack)
        reasons.append(f"외부 공격({labels})은 침해사고에 해당합니다.")
    if external:
        reasons.append("외부의 불법 접근으로 정보가 빠져나갔습니다.")
    required = bool(attack or external)
    if required:
        reasons.append(
            "웹사이트·앱으로 영리 목적의 서비스를 하는 사업자(정보통신서비스 제공자)는 신고 의무가 있습니다."
        )
        reasons.append("공격 '의심' 단계에서도 신고할 수 있습니다. 확실해질 때까지 기다리지 마세요.")
    else:
        reasons.append(
            "외부 공격 흔적이 확인되지 않았습니다. 해킹·악성코드·계정 탈취가 의심되면 사고 유형을 고르고 다시 확인하세요."
        )
    d = deadline("침해사고 신고 기한", legal.INCIDENT_BASIS, incident.discovered_at, legal.INCIDENT_HOURS, now)
    return FilingNeed(kind="incident_24h", required=required, reasons=reasons, deadline=d if required else None)


def privacy_need(incident: IncidentInput, now: datetime) -> FilingNeed:
    pi = incident.personal_info
    if pi is None or pi.leaked == "none":
        return FilingNeed(kind="privacy_72h", required=False, reasons=["개인정보 유출이 확인되거나 의심되지 않습니다."])

    reasons: list[str] = []
    if pi.affected_count is not None and pi.affected_count >= legal.PRIVACY_THRESHOLD:
        reasons.append(f"유출 규모가 {pi.affected_count:,}명으로 1천명 이상입니다.")
    if pi.includes_sensitive:
        reasons.append("민감정보가 포함되었습니다.")
    if pi.includes_unique_id:
        reasons.append("고유식별정보(주민등록번호 등)가 포함되었습니다.")
    if pi.external_unauthorized_access:
        reasons.append("외부의 불법 접근으로 유출되었습니다.")
    required = bool(reasons)

    if required and pi.recovered_low_risk:
        reasons.append(
            "유출 경로를 확인하고 회수·삭제해 피해 가능성이 현저히 낮다고 표시했습니다. 이 경우 신고하지 않을 수 있지만, "
            "회수·삭제를 입증할 기록을 남겨 두세요. 판단이 애매하면 신고하는 편이 안전합니다."
        )
        required = False
    elif not required:
        if pi.affected_count is None:
            reasons.append(
                "유출 규모를 아직 모릅니다. 1천명 이상인지 먼저 확인하세요. 모르는 채로 기한이 다가오면 신고하는 편이 안전합니다."
            )
        else:
            reasons.append("신고 기준(1천명 이상, 민감·고유식별정보, 외부 불법 접근)에 해당하지 않습니다.")
    # 신고 대상이 아니어도 유출 사실을 정보주체에게 알려야 합니다 (법 제34조, 시행령 제39조: 72시간)
    reasons.append(
        f"신고 대상과 상관없이 유출된 사람(정보주체)에게는 알게 된 때부터 {legal.SUBJECT_NOTICE_HOURS}시간 이내에 알려야 합니다."
    )
    if pi.leaked == "suspected":
        # 2026-09-11 신설: 확인 전이라도 가능성 통지 대상일 수 있습니다 (시행령 제39조의2)
        reasons.append(legal.POSSIBILITY_NOTICE_NOTE + ".")
    d = deadline("개인정보 유출 신고 기한", legal.PRIVACY_BASIS, incident.discovered_at, legal.PRIVACY_HOURS, now)
    return FilingNeed(kind="privacy_72h", required=required, reasons=reasons, deadline=d if required else None)


def assess(incident: IncidentInput, now: datetime) -> AssessResponse:
    return AssessResponse(needs=[incident_need(incident, now), privacy_need(incident, now)])


# ── 공통 칸 ──


def contact_fields(incident: IncidentInput) -> list[FormField]:
    org = incident.organization
    return [
        FormField(label="담당 부서", value=org.department, required=True),
        FormField(label="담당자", value=org.contact_name, required=True),
        FormField(
            label="연락처(전화)", value=org.contact_phone, required=True, hint="신고 기관이 바로 연락할 수 있는 번호"
        ),
        FormField(label="전자우편", value=org.contact_email),
    ]


def actions_text(incident: IncidentInput) -> str | None:
    lines = []
    for a in sorted(incident.actions_taken, key=lambda a: (a.at is None, a.at)):
        when = fmt_time(a.at)
        lines.append(f"{when} {a.action}" if when else a.action)
    return join_or_none(lines, "\n")


def cause_from_findings(incident: IncidentInput, findings: list[FindingInput]) -> str | None:
    """원인 칸이 비었을 때 관련 탐지 결과로 원인 후보를 제안합니다."""
    related = (
        [f for f in findings if f.fingerprint in incident.related_fingerprints] if incident.related_fingerprints else []
    )
    if not related:
        return None
    parts = []
    for f in related[:5]:
        loc = location(f)
        parts.append(f"{redact_secrets(f.title)}" + (f" ({loc})" if loc else ""))
    return "보안 점검에서 발견한 취약점이 원인일 수 있습니다: " + "; ".join(parts)


def status_badge(missing: list[str], overdue: bool) -> Badge:
    if overdue:
        return Badge(text="기한 지남 · 즉시 신고", tone="danger")
    if missing:
        return Badge(text=f"작성 중 · {len(missing)}칸 남음", tone="warning")
    return Badge(text="제출 준비 완료", tone="ok")


def base_fields(incident: IncidentInput) -> list[FormField]:
    org = incident.organization
    fields = [
        FormField(label="신고 구분", value="보완 신고" if incident.is_supplement else "최초 신고"),
        FormField(label="회사(기관) 이름", value=org.name, required=True),
        FormField(label="서비스", value=join_or_none([org.service_name or "", org.service_url or ""], " · ")),
    ]
    if incident.is_supplement:
        # 보완 신고는 최초 신고와 이어져야 합니다. 접수번호는 제출처에서 받은 값을 사람이 적습니다
        fields.insert(1, FormField(label="최초 신고 접수번호·일시", value=None,
                                   hint="보완 신고임을 밝히고 최초 신고 때 받은 접수번호나 신고 일시를 적으세요"))
    return fields


def boho_type(incident: IncidentInput) -> str:
    """보호나라 신고 화면의 유형(랜섬웨어·디도스·그 밖의 해킹) 중 고를 것."""
    picked = [legal.BOHO_TYPE_LABEL[t] for t in incident.incident_types if t in legal.BOHO_TYPE_LABEL]
    return " · ".join(dict.fromkeys(picked)) or legal.BOHO_TYPE_DEFAULT


def user_notice(incident: IncidentInput, cause: str | None) -> list[str]:
    """이용자 통지 5개 항목(시행령 제58조의9). 모르는 칸은 '확인 중'으로 두고 확인되는 대로 다시 알립니다."""
    org = incident.organization
    contact = join_or_none([org.department or "", org.contact_phone or "", org.contact_email or ""], " · ")
    when = fmt_time(incident.occurred_at) or "확인 중"
    return [
        f"① 발생 일시·원인·피해 내용: {when} / 원인 {cause or '확인 중'} / {incident.damage or '피해 내용 확인 중'}",
        f"② 대응 현황: {(actions_text(incident) or '조치 중').replace(chr(10), ' / ')}",
        "③ 이렇게 해 주세요: 저희 서비스와 같은 비밀번호를 쓰는 곳이 있다면 바꾸고, 저희를 사칭한 문자·이메일의 링크를 열지 마세요.",
        "④ 피해 구제: 피해가 생기셨다면 아래 담당 부서로 알려 주세요. 확인 후 구제 방법을 안내해 드립니다.",
        f"⑤ 문의·피해 구제 담당: {contact or '(담당 부서·연락처 작성 필요)'}",
        "추가로 확인되는 내용은 바로 다시 알려 드리겠습니다. 불편을 드려 죄송합니다.",
    ]


# ── 침해사고 신고 (24시간) ──


def build_incident_report(req: FilingRequest, now: datetime) -> Report:
    incident = req.incident
    d = deadline("침해사고 신고 기한", legal.INCIDENT_BASIS, incident.discovered_at, legal.INCIDENT_HOURS, now)

    cause = incident.cause
    cause_auto = False
    if not cause and (suggested := cause_from_findings(incident, req.findings)):
        cause, cause_auto = suggested, True

    basic = base_fields(incident)
    what = [
        FormField(
            label="발생 일시",
            value=fmt_time(incident.occurred_at),
            required=True,
            hint="정확히 모르면 추정 시각을 적고 '추정'이라고 쓰세요",
        ),
        FormField(label="알게 된 일시", value=fmt_time(incident.discovered_at), required=True),
        FormField(
            label="사고 유형",
            value=join_or_none([legal.INCIDENT_TYPE_LABEL[t] for t in incident.incident_types]),
        ),
        FormField(label="보호나라 신고 유형", value=boho_type(incident), auto=True,
                  hint="보호나라 신고하기 화면에서 고를 유형입니다(랜섬웨어 / 디도스 / 그 밖의 해킹)"),
        FormField(label="사고 개요", value=incident.summary),
        FormField(
            label="원인",
            value=cause,
            required=True,
            auto=cause_auto,
            hint="원인 추정입니다. 확인되면 고쳐 적으세요"
            if cause_auto
            else "모르면 '조사 중'이라고 적고 확인 후 보완 신고",
        ),
        FormField(
            label="피해 내용", value=incident.damage, required=True, hint="어떤 시스템·데이터가 어떻게 영향을 받았는지"
        ),
        FormField(label="피해 시스템", value=join_or_none(incident.affected_systems)),
    ]
    response = [
        FormField(label="현재 상태", value=legal.INCIDENT_STATUS_LABEL[incident.status]),
        FormField(label="조치 사항", value=actions_text(incident), required=True, hint="시각과 함께 한 일을 순서대로"),
    ]
    contact = contact_fields(incident)

    missing = (
        missing_labels(basic, "기본 · ")
        + missing_labels(what, "① · ")
        + missing_labels(response, "② · ")
        + missing_labels(contact, "③ · ")
    )
    sections = [
        Section(
            heading="기한",
            paragraphs=[
                f"알게 된 때({fmt_time(incident.discovered_at)})부터 24시간 이내인 {fmt_time(d.due_at)}까지 신고해야 합니다.",
                "모르는 칸이 있어도 기한 안에 먼저 신고하고, 추가로 확인한 내용은 확인한 때부터 24시간 이내에 보완 신고하세요.",
            ],
        ),
        Section(heading="기본 정보", fields=basic),
        Section(heading="① 발생 일시 · 원인 · 피해 내용", fields=what),
        Section(heading="② 대응 현황", fields=response),
        Section(heading="③ 대응 담당 부서 · 연락처", fields=contact),
        Section(
            heading="이용자 통지문 초안",
            paragraphs=[
                "이용자 정보가 유출·변조·훼손됐거나 그럴 가능성이 있거나 서비스가 2시간 이상 멈췄다면 이용자에게 지체 없이 알립니다"
                "(정보통신망법 제48조의3 제4항 · 시행령 제58조의9, 2026-10-01 시행). 원인을 아직 모르면 아는 항목부터 먼저 알리세요.",
            ],
            cards=[Card(title=f"[{incident.organization.name or '저희 서비스'}] 보안 사고를 알려 드립니다",
                        paragraphs=user_notice(incident, cause))],
        ),
        Section(
            heading="신고 전후로 꼭 할 일",
            bullets=[
                "의심되는 서버·계정은 네트워크에서 분리하거나 접속을 막아 피해가 번지지 않게 하세요.",
                "접속 기록(로그)과 관련 파일은 지우거나 고치지 말고 그대로 보관하세요. 원인 분석의 증거입니다.",
                "노출된 비밀번호·API 키는 새로 발급하고 이전 값은 폐기하세요.",
                "개인정보가 빠져나갔거나 위조·변조·훼손(랜섬웨어 등)됐다면 개인정보 유출 신고(72시간)도 따로 확인하세요.",
                legal.INCIDENT_USER_NOTICE_NOTE + ".",
                legal.INCIDENT_RELIEF_REPORT_NOTE + ".",
                legal.INCIDENT_SCAN_NOTE + ".",
                legal.INCIDENT_FINE_NOTE + ".",
            ],
        ),
    ]
    return Report(
        kind="incident_24h",
        title="침해사고 신고서 초안",
        subtitle=" · ".join(x for x in (incident.organization.name, "KISA 제출용") if x),
        generated_at=now,
        status=status_badge(missing, d.overdue),
        deadline=d,
        sections=sections,
        missing=missing,
        submit_to=legal.INCIDENT_SUBMIT_TO,
        disclaimer=legal.DISCLAIMER,
    )


# ── 개인정보 유출 신고 (72시간) ──


def suggested_mitigations(pi: PersonalInfoBreach) -> list[str]:
    text = " ".join(pi.items).lower()
    found = [tip for keys, tip in legal.SUBJECT_MITIGATIONS if any(k.lower() in text for k in keys)]
    return found or ["출처가 분명하지 않은 연락에 개인정보나 인증번호를 알려 주지 마세요."]


def scale_text(pi: PersonalInfoBreach) -> str | None:
    if pi.affected_count is None:
        return None
    return f"약 {pi.affected_count:,}명 (추정)" if pi.count_is_estimate else f"{pi.affected_count:,}명"


def build_privacy_report(req: FilingRequest, now: datetime) -> Report:
    incident = req.incident
    pi = incident.personal_info or PersonalInfoBreach(leaked="suspected")
    need = privacy_need(incident, now)
    d = deadline("개인정보 유출 신고 기한", legal.PRIVACY_BASIS, incident.discovered_at, legal.PRIVACY_HOURS, now)

    mitigations, mitigations_auto = pi.subject_mitigations, False
    if not mitigations:
        mitigations, mitigations_auto = suggested_mitigations(pi), True
    relief = pi.relief_procedure or legal.DEFAULT_RELIEF
    report_contact = pi.damage_report_contact or join_or_none(
        [incident.organization.department or "", incident.organization.contact_phone or ""], " · "
    )

    if pi.subjects_notified:
        notified = "통지함" + "".join(f" · {x}" for x in (fmt_time(pi.notified_at), pi.notify_method) if x)
    else:
        notified = "아직 통지하지 않음"
    # 경위(무슨 일이 어떻게)를 알면 칸을 채우고, 발생 시점만 모르면 '확인 중'으로 남겨 먼저 신고할 수 있게 합니다
    has_story = bool(incident.summary or incident.cause)
    timeline = join_or_none(
        [
            f"발생: {fmt_time(incident.occurred_at) or '확인 중'}",
            f"인지: {fmt_time(incident.discovered_at)}",
            incident.summary or "",
            f"원인: {incident.cause}" if incident.cause else "",
        ],
        "\n",
    )

    basic = base_fields(incident)
    form = [
        FormField(label="정보주체 통지 여부", value=notified, required=True),
        FormField(label="유출된 개인정보 항목", value=join_or_none(pi.items), required=True,
                  hint=("'등'으로 묶지 말고 항목을 하나씩 적으세요(예: 이름, 이메일, 휴대전화번호). 뭉뚱그린 기재는 위반 사례로 지적됩니다"
                        if any(x.strip().endswith("등") or x.strip() == "등" for x in pi.items) else None)),
        FormField(label="유출 규모", value=scale_text(pi), required=True),
        FormField(
            label="유출 시점과 경위",
            value=timeline if has_story else None,
            required=True,
            hint=(
                "발생 시점이 확인되면 보완해 추가 신고하세요"
                if has_story and not incident.occurred_at
                else "언제, 어떤 경로로 빠져나갔는지. 모르면 확인된 내용까지만 적고 먼저 신고"
            ),
        ),
        FormField(label="피해 최소화 대책·조치 및 결과", value=actions_text(incident), required=True),
        FormField(
            label="정보주체가 할 수 있는 피해 최소화 방법",
            value="\n".join(mitigations),
            required=True,
            auto=mitigations_auto,
            hint="유출 항목에 맞춰 제안한 문장입니다. 확인 후 고쳐 쓰세요" if mitigations_auto else None,
        ),
        FormField(label="피해 구제 절차", value=relief, required=True, auto=pi.relief_procedure is None),
        *contact_fields(incident),
    ]
    missing = missing_labels(basic, "기본 · ") + missing_labels(form, "신고서 · ")

    preliminary = []
    if not pi.items or not has_story or not incident.occurred_at:
        # 시행령 제40조 제2항: 유출 항목·시점과 경위를 모르면 확인된 내용으로 먼저 신고
        preliminary.append(
            "유출 항목이나 시점·경위를 아직 모르면, 유출 사실과 지금까지 확인한 내용으로 먼저 신고하고 "
            "추가로 확인되는 대로 바로 추가 신고하세요. 기한을 넘기는 것보다 낫습니다."
        )

    org = incident.organization.name or "저희 회사"
    suspected = pi.leaked == "suspected"
    # 확인 전이면 '유출 가능성' 통지로 씁니다 (시행령 제39조의2, 2026-09-11 시행)
    notice_title = f"[{org}] 개인정보 유출{' 가능성' if suspected else ' 사실'}을 알려 드립니다"
    notice = [
        f"유출된 항목: {join_or_none(pi.items) or '(확인 중)'}",
        f"유출 시점과 경위: {incident.summary or '(확인 중)'}"
        + (f" (발생 {fmt_time(incident.occurred_at)})" if incident.occurred_at else ""),
        "이렇게 해 주세요: " + " ".join(mitigations),
        f"저희가 한 조치: {actions_text(incident) or '(작성 필요)'}".replace("\n", " / "),
        f"피해 구제: {relief}",
        legal.NOTICE_DISPUTE,
        f"문의·피해 신고: {report_contact or '(담당 부서·연락처 작성 필요)'}",
        ("유출이 확인되면 다시 알려 드리고, 유출이 아닌 것으로 확인되면 그 사실도 바로 알려 드리겠습니다. 불편과 걱정을 드려 죄송합니다."
         if suspected else "불편과 걱정을 드려 죄송합니다. 추가로 확인되는 내용은 바로 알려 드리겠습니다."),
    ]

    if need.required:
        status = status_badge(missing, d.overdue)
    else:
        status = Badge(text="신고 대상 아닐 수 있음 · 통지는 필요", tone="info")

    sections = [
        Section(heading="신고 대상인지", bullets=need.reasons),
        Section(
            heading="기한",
            paragraphs=[
                f"알게 된 때({fmt_time(incident.discovered_at)})부터 72시간 이내인 {fmt_time(d.due_at)}까지 신고해야 합니다.",
                *preliminary,
            ],
        ),
        Section(heading="기본 정보", fields=basic),
        Section(heading="유출신고서 항목", fields=form),
        Section(
            heading="정보주체 통지문 초안",
            paragraphs=[
                f"유출된 분들께 보낼 안내문입니다. 알게 된 때부터 {legal.SUBJECT_NOTICE_HOURS}시간 이내에 이메일·문자 등으로 알리고, "
                "연락이 닿지 않는 분이 있으면 홈페이지에 30일 이상 게시하세요.",
                *([legal.POSSIBILITY_NOTICE_NOTE + "."] if suspected else []),
            ],
            cards=[Card(title=notice_title, paragraphs=notice)],
        ),
        Section(
            heading="꼭 할 일",
            bullets=[
                "유출 경로(취약점·계정)를 먼저 막고, 빠져나간 데이터가 공개된 곳이 있으면 삭제를 요청하세요.",
                "비밀번호가 유출됐다면 해당 회원의 비밀번호를 초기화하고 재설정을 안내하세요.",
                "외부 해킹이 원인이면 침해사고 신고(24시간)도 따로 해야 합니다.",
                legal.LEAK_SCOPE_NOTE + ".",
                legal.PRIVACY_FINE_NOTE + ".",
            ],
        ),
    ]
    return Report(
        kind="privacy_72h",
        title="개인정보 유출 신고서 초안",
        subtitle=" · ".join(x for x in (incident.organization.name, "개인정보보호위원회·KISA 제출용") if x),
        generated_at=now,
        status=status,
        deadline=d,
        sections=sections,
        # 신고 대상이 아니어도 스스로 신고하거나 나중에 대상이 될 수 있어 빈 칸은 그대로 알려 줍니다
        missing=missing,
        submit_to=legal.PRIVACY_SUBMIT_TO,
        disclaimer=legal.DISCLAIMER,
    )
