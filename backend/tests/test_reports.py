import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.llm.schemas import ExplainResult, Explanation, FixStep
from app.main import app
from app.reports import filing, plain, render
from app.reports.common import deadline, fmt_remaining, fmt_time
from app.reports.schemas import FilingRequest, IncidentInput, PlainReportRequest
from app.routers.reports import get_now
from tests.conftest import FAKE_OPENAI_KEY, FIXTURES

KST = timezone(timedelta(hours=9))
NOW = datetime(2026, 10, 31, 10, 0, tzinfo=KST)


def findings_data() -> list[dict]:
    return json.loads((FIXTURES / "findings.json").read_text(encoding="utf-8"))


def explanation(fingerprint: str, **overrides) -> dict:
    data = Explanation(
        fingerprint=fingerprint,
        variant="D",
        summary="브라우저 코드에 관리자 키가 들어 있습니다.",
        why_risky="누구나 고객 정보를 모두 볼 수 있습니다.",
        priority="now",
        fix_steps=[FixStep(title="키 새로 발급하기", detail="Supabase 대시보드에서 새 키를 발급합니다.")],
        ai_fix_prompt="src/lib/supabase.ts 4줄의 키를 서버 전용 환경 변수로 옮겨 주세요.",
        false_positive_suspect=False,
        attack_scenario="공격자가 브라우저 개발자 도구에서 키를 꺼내 고객 표 전체를 조회합니다.",
        red_verdict="pass",
        model="qwen3.8-27b",
        prompt_version="test",
        latency_ms=1,
        completion_tokens=1,
    ).model_dump()
    data.update(overrides)
    return ExplainResult(fingerprint=fingerprint, status="done", explanation=data).model_dump()


def plain_request(findings: list[dict] | None = None, results: list[dict] | None = None, **scan) -> PlainReportRequest:
    return PlainReportRequest.model_validate(
        {
            "scan": {
                "site_name": "데모 쇼핑몰",
                "site_url": "https://demo.shop",
                "scanned_at": "2026-10-31T09:00:00+09:00",
                "detected_at": "2026-10-30T09:00:00+09:00",
                **scan,
            },
            "findings": findings_data() if findings is None else findings,
            "explain_results": results or [],
        }
    )


def incident(**overrides) -> dict:
    data = {
        "organization": {
            "name": "데모커머스",
            "service_name": "데모 쇼핑몰",
            "department": "운영팀",
            "contact_name": "담당자",
            "contact_phone": "02-000-0000",
        },
        "discovered_at": "2026-10-31T08:00:00+09:00",
        "occurred_at": "2026-10-30T23:10:00+09:00",
        "incident_types": ["hacking"],
        "summary": "유출된 관리자 키로 고객 표 전체가 조회되었습니다.",
        "cause": "브라우저 코드에 들어간 관리자 키",
        "damage": "고객 표 조회",
        "actions_taken": [{"at": "2026-10-31T08:30:00+09:00", "action": "키 폐기 후 재발급"}],
    }
    data.update(overrides)
    return data


def breach(**overrides) -> dict:
    data = {
        "leaked": "confirmed",
        "affected_count": 1520,
        "items": ["이름", "이메일", "비밀번호(해시)"],
        "external_unauthorized_access": True,
    }
    data.update(overrides)
    return data


def section(report, heading):
    return next(s for s in report.sections if s.heading == heading)


def field(section_, label):
    return next(f for f in section_.fields if f.label == label)


# ── 기한 ──


def test_deadline_counts_down_and_flags_overdue():
    start = datetime(2026, 10, 31, 8, 0, tzinfo=KST)

    d = deadline("x", "y", start, 24, now=start + timedelta(hours=23, minutes=59, seconds=30))
    assert (d.remaining_minutes, d.overdue) == (0, False)  # 30초 남았으면 아직 기한 안

    d = deadline("x", "y", start, 24, now=start + timedelta(hours=24, seconds=1))
    assert d.overdue and d.remaining_minutes == -1
    assert fmt_remaining(-125) == "2시간 5분 지남"


def test_fmt_time_uses_korea_time():
    assert fmt_time(datetime(2026, 10, 31, 0, 0, tzinfo=timezone.utc)) == "2026-10-31(토) 09:00"


# ── 비전공자 리포트 ──


def test_plain_report_orders_urgent_first_and_uses_explanation():
    results = [explanation("demo-secret-supabase-service-role")]
    report = plain.build_plain_report(plain_request(results=results), NOW)

    assert report.kind == "plain"
    assert report.status.text == "위험"
    cards = section(report, "고칠 것 자세히").cards
    # 지금 바로(now) 4건이 먼저, XSS(medium)는 뒤
    assert cards[-1].title == "사용자가 쓴 후기를 HTML로 그대로 화면에 넣음"
    secret = next(c for c in cards if c.title.startswith("브라우저 코드에 관리자 키"))
    assert {b.text for b in secret.badges} >= {"지금 바로", "매우 위험", "공격 검증 통과"}
    assert any(p.startswith("공격자는 이렇게 노릴 수 있어요") for p in secret.paragraphs)
    assert field(secret, "AI 코딩툴에 붙여 넣을 지시").value.startswith("src/lib/supabase.ts")
    # 해석이 없는 건도 심각도로 우선순위를 정하고 안내 문구를 보여 줍니다
    sqli = next(c for c in cards if "SQL" in c.title)
    assert "설명 준비 중" in {b.text for b in sqli.badges}
    assert report.deadline.remaining_minutes == 47 * 60


def test_plain_report_puts_false_positive_last_and_flags_manual_review():
    results = [
        explanation("demo-secret-supabase-service-role", false_positive_suspect=True, false_positive_reason="예시 키"),
        explanation(
            "demo-code-sqli-orders",
            summary="주문 조회가 SQL 주입에 열려 있음",
            needs_manual_review=True,
            red_verdict="bypass",
        ),
    ]
    report = plain.build_plain_report(plain_request(results=results), NOW)

    cards = section(report, "고칠 것 자세히").cards
    assert cards[-1].title.startswith("브라우저 코드에 관리자 키")
    assert "오탐일 수 있음" in {b.text for b in cards[-1].badges}
    sqli = next(c for c in cards if c.title.startswith("주문 조회"))
    assert "사람 확인 필요" in {b.text for b in sqli.badges}
    # 오탐 의심은 '지금 바로 할 일'에 넣지 않습니다
    assert not any("관리자 키" in s for s in section(report, "지금 바로 할 일").steps)


def test_plain_report_becomes_completion_report_and_stops_timer():
    findings = [{**f, "status": "code_resolved"} for f in findings_data()]
    report = plain.build_plain_report(plain_request(findings=findings, resolved_at="2026-10-31T09:30:00+09:00"), NOW)

    assert report.title == "데모 쇼핑몰 보안 조치 완료 리포트"
    assert report.status.text == "완료"
    assert report.deadline.stopped_at.isoformat() == "2026-10-31T09:30:00+09:00"
    assert not report.deadline.overdue
    assert len(section(report, "해결된 것").bullets) == 5
    assert all(s.heading != "고칠 것 자세히" for s in report.sections)


def test_plain_report_out_of_scope_needs_recheck_not_completion():
    findings = [{**findings_data()[0], "status": "out_of_scope"}]
    report = plain.build_plain_report(plain_request(findings=findings), NOW)

    assert report.status.text == "다시 검사 필요"
    assert report.deadline.stopped_at is None


def dep(fp: str, cve: str, severity: str = "high") -> dict:
    return {
        "fingerprint": fp,
        "tool": "osv",
        "category": "dependency",
        "rule_id": cve,
        "title": f"lodash 취약점 {cve}",
        "severity": severity,
        "file_path": "package-lock.json",
        "package_name": "lodash",
        "package_ecosystem": "npm",
        "installed_version": "4.17.15",
        "fixed_version": "4.17.21",
        "refs": {"cve": [cve]},
    }


def test_package_explanation_covers_grouped_findings_in_one_card():
    # #27: 같은 패키지 취약점 3건을 한 번에 설명한 결과(covers)는 카드 하나로 묶습니다
    findings = [
        dep("d1", "CVE-2020-8203"),
        dep("d2", "CVE-2021-23337", "critical"),
        dep("d3", "CVE-2020-28500", "medium"),
    ]
    pkg = explanation("pkg:npm:lodash:package-lock.json", summary="lodash를 4.17.21로 올리세요", priority="soon")
    pkg["covers"] = ["d1", "d2", "d3"]
    report = plain.build_plain_report(plain_request(findings=findings, results=[pkg]), NOW)

    cards = section(report, "고칠 것 자세히").cards
    assert len(cards) == 1
    card = cards[0]
    assert card.title == "lodash를 4.17.21로 올리세요"
    assert "매우 위험" in {b.text for b in card.badges}  # 묶음 중 가장 위험한 심각도
    together = field(card, "함께 해결되는 문제")
    assert together.value.startswith("3건")
    assert "CVE-2021-23337" in field(card, "관련 번호").value
    assert field(section(report, "한눈에 보기"), "고칠 것").value.startswith("1건")


def test_not_checked_area_blocks_completion_and_safe_wording():
    # #28: 문제가 0건이어도 검사하지 못한 영역이 있으면 완료·안전이라고 하지 않습니다
    findings = [{**f, "status": "code_resolved"} for f in findings_data()]
    req = plain_request(
        findings=findings,
        not_checked=[
            {"tool": "osv", "category": "dependency", "reason": "취약점 DB에 접속하지 못했습니다.\n자세한 로그..."}
        ],
    )
    report = plain.build_plain_report(req, NOW)

    assert report.status.text == "다시 검사 필요"
    assert "완료" not in report.title
    assert report.deadline.stopped_at is None
    assert "안전하다고 말할 수 없습니다" in section(report, "한눈에 보기").paragraphs[0]
    area = section(report, "이번에 검사하지 못한 영역")
    assert area.bullets == ["외부 부품(라이브러리) 검사: 취약점 DB에 접속하지 못했습니다."]
    assert field(section(report, "한눈에 보기"), "검사하지 못한 영역").value.startswith("1곳")
    assert section(report, "다음 단계").steps[0].startswith("'이번에 검사하지 못한 영역'")


@pytest.mark.parametrize(
    ("raw", "shown"),
    [
        (
            "종료 코드 127 (취약점 DB에 접속하지 못했습니다. 인터넷 연결을 확인하세요.): Scanning dir /tmp/site",
            "취약점 DB에 접속하지 못했습니다. 인터넷 연결을 확인하세요.",
        ),
        ("lockfile not found in /srv/scans/abc/repo", "lockfile not found in (경로)"),
        ("", "도구가 결과를 내지 못했습니다"),
        # #34 리뷰 2: URL과 낱말 속 슬래시는 그대로 둡니다
        ("could not reach https://api.osv.dev/v1/querybatch", "could not reach https://api.osv.dev/v1/querybatch"),
        ("OSV/NVD 데이터베이스 응답 없음", "OSV/NVD 데이터베이스 응답 없음"),
        ("timeout C:\\Users\\me\\AppData\\Local\\Temp\\scan", "timeout (경로)"),
        ("ENOENT /home/ncloud/apps/72hours/x and /var/lib/y", "ENOENT (경로) and (경로)"),
    ],
    ids=["engine-format", "raw-path", "empty", "url-kept", "word-slash-kept", "windows-path", "two-paths"],
)
def test_not_checked_reason_is_friendly_and_hides_server_paths(raw, shown):
    assert plain.friendly_reason(raw) == shown


def test_long_engine_message_is_clipped_not_rejected(api):
    # #34 리뷰 1: 엔진은 도구 오류를 개수 제한 없이 이어 붙입니다. 1,000자를 넘어도 422 대신 잘라서 받습니다
    reason = "; ".join(f"Opengrep fatal error {i}: " + "x" * 200 for i in range(8))
    assert len(reason) > 1000
    body = plain_request().model_dump(mode="json")
    body["scan"]["not_checked"] = [{"tool": "semgrep" * 10, "category": "code" * 20, "reason": reason}]

    resp = api.post("/api/reports/plain", json=body)

    assert resp.status_code == 200
    area = next(s for s in resp.json()["sections"] if s["heading"] == "이번에 검사하지 못한 영역")
    assert area["bullets"][0].count("Opengrep fatal error") >= 1


def test_unverifiable_change_is_recheck_not_open():
    findings = [{**findings_data()[0], "change": "unverifiable"}]
    report = plain.build_plain_report(plain_request(findings=findings), NOW)

    assert report.status.text == "다시 검사 필요"
    assert section(report, "다시 검사가 필요한 것").bullets


def test_api_accepts_engine_not_checked_as_is(api):
    body = plain_request().model_dump(mode="json")
    body["scan"]["not_checked"] = [{"tool": "semgrep", "category": "code", "reason": "시간 초과"}]

    md = api.post("/api/reports/plain?format=markdown", json=body).text
    assert "## 이번에 검사하지 못한 영역" in md
    assert "- 코드 검사: 시간 초과" in md


def test_glossary_matches_exact_cwe_only():
    # CWE-798(비밀키)만 있을 때 CWE-79(XSS) 풀이가 붙으면 안 됩니다
    report = plain.build_plain_report(plain_request(findings=findings_data()[:1]), NOW)

    terms = section(report, "용어 풀이").bullets
    assert any(t.startswith("비밀키") for t in terms)
    assert not any(t.startswith("XSS") for t in terms)


def test_plain_report_never_leaks_secrets():
    leaky = {**findings_data()[0], "title": f"키 노출 {FAKE_OPENAI_KEY}"}
    report = plain.build_plain_report(plain_request(findings=[leaky]), NOW)

    assert FAKE_OPENAI_KEY not in report.model_dump_json()
    assert FAKE_OPENAI_KEY not in render.to_html(report)


def test_html_escapes_user_text():
    hostile = {**findings_data()[0], "title": "<script>alert(1)</script>"}
    html = render.to_html(plain.build_plain_report(plain_request(findings=[hostile], site_name="<b>몰</b>"), NOW))

    assert "<script>alert(1)" not in html
    assert "&lt;script&gt;" in html
    assert "<b>몰</b>" not in html


# ── 신고 필요 여부 ──


@pytest.mark.parametrize(
    ("overrides", "required"),
    [
        ({"incident_types": ["hacking"]}, True),
        ({"incident_types": ["malware", "data_leak"]}, True),
        ({"incident_types": ["data_leak"]}, False),
        ({"incident_types": ["data_leak"], "personal_info": breach(external_unauthorized_access=True)}, True),
    ],
    ids=["hacking", "malware", "leak-by-mistake", "leak-by-external-access"],
)
def test_assess_incident(overrides, required):
    need = filing.incident_need(IncidentInput.model_validate(incident(**overrides)), NOW)

    assert need.required is required
    assert (need.deadline is not None) is required


@pytest.mark.parametrize(
    ("pi", "required"),
    [
        (None, False),
        (breach(leaked="none"), False),
        (breach(affected_count=999, external_unauthorized_access=False), False),
        (breach(affected_count=1000, external_unauthorized_access=False), True),
        (breach(affected_count=3, external_unauthorized_access=False, includes_unique_id=True), True),
        (breach(affected_count=3, external_unauthorized_access=False, includes_sensitive=True), True),
        (breach(affected_count=3), True),
        (breach(recovered_low_risk=True), False),
    ],
    ids=["no-pi", "none", "999", "1000", "unique-id", "sensitive", "external", "recovered"],
)
def test_assess_privacy_thresholds(pi, required):
    need = filing.privacy_need(IncidentInput.model_validate(incident(personal_info=pi)), NOW)

    assert need.required is required
    if pi and pi["leaked"] != "none":
        # 신고 대상이 아니어도 정보주체 통지는 필요합니다
        assert any("정보주체" in r for r in need.reasons)


def test_assess_unknown_count_asks_to_check():
    pi = breach(affected_count=None, external_unauthorized_access=False)
    need = filing.privacy_need(IncidentInput.model_validate(incident(personal_info=pi)), NOW)

    assert not need.required
    assert any("1천명 이상인지 먼저 확인" in r for r in need.reasons)


# ── 침해사고 신고서 (24시간) ──


def test_incident_report_complete():
    report = filing.build_incident_report(FilingRequest(incident=incident()), NOW)

    assert report.kind == "incident_24h"
    assert report.missing == []
    assert report.status.text == "제출 준비 완료"
    assert report.deadline.due_at == datetime(2026, 11, 1, 8, 0, tzinfo=KST)
    assert report.deadline.remaining_minutes == 22 * 60
    assert [s.heading for s in report.sections][2:5] == [
        "① 발생 일시 · 원인 · 피해 내용",
        "② 대응 현황",
        "③ 대응 담당 부서 · 연락처",
    ]
    assert any("boho.or.kr" in s for s in report.submit_to)


def test_incident_report_lists_missing_and_suggests_cause_from_findings():
    req = FilingRequest.model_validate(
        {
            "incident": incident(
                occurred_at=None,
                cause=None,
                damage=None,
                organization={"name": "데모커머스"},
                related_fingerprints=["demo-secret-supabase-service-role"],
            ),
            "findings": findings_data(),
        }
    )
    report = filing.build_incident_report(req, NOW)

    assert "① · 발생 일시" in report.missing
    assert "① · 피해 내용" in report.missing
    assert "③ · 연락처(전화)" in report.missing
    assert "① · 원인" not in report.missing  # 탐지 결과로 제안했으므로
    cause = field(section(report, "① 발생 일시 · 원인 · 피해 내용"), "원인")
    assert cause.auto and "src/lib/supabase.ts 4줄" in cause.value
    assert report.status.tone == "warning"


def test_incident_report_overdue():
    late = NOW + timedelta(hours=30)
    report = filing.build_incident_report(FilingRequest(incident=incident()), late)

    assert report.deadline.overdue
    assert report.status.text == "기한 지남 · 즉시 신고"


def test_filing_legal_notes_follow_official_guidance_checked_2026_10_31():
    # KISA 보호나라: 24시간 안에 신고하지 않거나 늦으면 제76조 5천만원 이하 과태료 (위반 횟수별 금액 없음)
    incident_report = filing.build_incident_report(FilingRequest(incident=incident()), NOW)
    todo = section(incident_report, "신고 전후로 꼭 할 일").bullets
    assert any("5천만 원 이하 과태료" in b and "제76조" in b for b in todo)
    assert not any("750만" in b or "1,500만" in b for b in todo)
    assert any("위조·변조·훼손" in b for b in todo)
    # 개인정보보호위원회 2026-09-10 보도자료: 위조·변조·훼손 포함, 가능성 통지 신설, 분쟁조정·손해배상 통지 항목 추가
    req = FilingRequest.model_validate({"incident": incident(personal_info=breach())})
    privacy_report = filing.build_privacy_report(req, NOW)
    assert any("유출 가능성" in b and "위조·변조·훼손" in b for b in section(privacy_report, "꼭 할 일").bullets)
    notice = section(privacy_report, "정보주체 통지문 초안").cards[0].paragraphs
    assert any(p.startswith("분쟁조정·손해배상:") for p in notice)


# ── 개인정보 유출 신고서 (72시간) ──


def test_privacy_report_fills_form_and_notice():
    req = FilingRequest.model_validate({"incident": incident(personal_info=breach(count_is_estimate=True))})
    report = filing.build_privacy_report(req, NOW)

    assert report.kind == "privacy_72h"
    assert report.deadline.due_at == datetime(2026, 11, 3, 8, 0, tzinfo=KST)
    form = section(report, "유출신고서 항목")
    assert field(form, "유출 규모").value == "약 1,520명 (추정)"
    assert field(form, "정보주체 통지 여부").value == "아직 통지하지 않음"
    tips = field(form, "정보주체가 할 수 있는 피해 최소화 방법")
    assert tips.auto and "비밀번호" in tips.value
    notice = section(report, "정보주체 통지문 초안").cards[0]
    assert notice.title == "[데모커머스] 개인정보 유출 사실을 알려 드립니다"
    assert any(p.startswith("문의·피해 신고: 운영팀") for p in notice.paragraphs)
    assert report.missing == []
    assert any("brss.pipc.go.kr" in s for s in report.submit_to)


def test_privacy_report_unknown_time_keeps_known_story_and_suggests_preliminary_filing():
    req = FilingRequest.model_validate({"incident": incident(occurred_at=None, personal_info=breach(items=[]))})
    report = filing.build_privacy_report(req, NOW)

    timeline = field(section(report, "유출신고서 항목"), "유출 시점과 경위")
    assert timeline.value.startswith("발생: 확인 중")
    assert report.missing == ["신고서 · 유출된 개인정보 항목"]
    assert any("먼저 신고" in p for p in section(report, "기한").paragraphs)


def test_privacy_report_not_required_still_reminds_notification():
    pi = breach(affected_count=12, external_unauthorized_access=False)
    report = filing.build_privacy_report(FilingRequest.model_validate({"incident": incident(personal_info=pi)}), NOW)

    assert report.status.tone == "info"
    assert "통지는 필요" in report.status.text


# ── #105: 2026년 9·10월 개정 법령 안내 ──
def test_subject_notice_deadline_is_72_hours_not_just_without_delay():
    need = filing.privacy_need(IncidentInput.model_validate(incident(personal_info=breach(affected_count=12, external_unauthorized_access=False))), NOW)

    notice = next(r for r in need.reasons if "정보주체" in r)
    assert "72시간 이내" in notice and "지체 없이" not in notice


def test_suspected_leak_mentions_possibility_notice():
    suspected = IncidentInput.model_validate(incident(personal_info=breach(leaked="suspected")))
    confirmed = IncidentInput.model_validate(incident(personal_info=breach(leaked="confirmed")))

    assert any("유출 가능성" in r and "제39조의2" in r for r in filing.privacy_need(suspected, NOW).reasons)
    assert not any("유출 가능성" in r for r in filing.privacy_need(confirmed, NOW).reasons)
    report = filing.build_privacy_report(FilingRequest.model_validate({"incident": incident(personal_info=breach(leaked="suspected"))}), NOW)
    notice_section = section(report, "정보주체 통지문 초안")
    assert any("유출 가능성" in p for p in notice_section.paragraphs)
    card = notice_section.cards[0]
    assert card.title.endswith("개인정보 유출 가능성을 알려 드립니다")
    assert "유출이 확인되면 다시 알려 드리고" in card.paragraphs[-1]  # 시행령 제39조의2 제2항: 확정 시 추가 통지


def test_privacy_report_states_current_fines_and_leak_scope():
    report = filing.build_privacy_report(FilingRequest.model_validate({"incident": incident(personal_info=breach())}), NOW)
    todo = section(report, "꼭 할 일").bullets

    assert any("900만 원" in b and "1,800만 원" in b and "3,000만 원" in b for b in todo)
    assert not any("3,000만 원 이하 과태료" in b for b in todo)  # 예전 문구
    assert any("위조·변조·훼손" in b for b in todo)
    intro = section(report, "정보주체 통지문 초안").paragraphs[0]
    assert "72시간 이내" in intro and "30일" in intro


def test_incident_report_reminds_user_notification_duty():
    report = filing.build_incident_report(FilingRequest(incident=incident()), NOW)
    todo = section(report, "신고 전후로 꼭 할 일").bullets

    assert any("이용자" in b and "제58조의9" in b and "2시간" in b for b in todo)
    assert any("5천만 원 이하" in b for b in todo)  # 침해사고 미신고 과태료: KISA 안내 기준(#82)


# ── API ──


@pytest.fixture
def api():
    app.dependency_overrides[get_now] = lambda: NOW
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_api_plain_json_markdown_html(api):
    body = plain_request(results=[explanation("demo-secret-supabase-service-role")]).model_dump(mode="json")

    resp = api.post("/api/reports/plain", json=body)
    assert resp.status_code == 200
    assert resp.json()["status"]["text"] == "위험"

    md = api.post("/api/reports/plain?format=markdown", json=body)
    assert md.headers["content-type"].startswith("text/markdown")
    assert md.text.startswith("# 데모 쇼핑몰 보안 점검 리포트")

    html = api.post("/api/reports/plain?format=html", json=body)
    assert html.headers["content-type"].startswith("text/html")
    assert "<title>데모 쇼핑몰 보안 점검 리포트</title>" in html.text


def test_api_accepts_explain_response_results_as_is(api):
    # /api/llm/explain 응답의 results(건너뛴 항목 포함)를 그대로 넘겨도 됩니다
    results = [
        explanation("demo-secret-supabase-service-role"),
        {"fingerprint": "demo-code-xss-review", "status": "skipped", "reason": "코드에서 이미 해결된 항목입니다"},
    ]
    body = plain_request(results=results).model_dump(mode="json")

    assert api.post("/api/reports/plain", json=body).status_code == 200


def test_api_assess_and_filings(api):
    body = incident(personal_info=breach())

    needs = api.post("/api/reports/assess", json=body).json()["needs"]
    assert [(n["kind"], n["required"]) for n in needs] == [("incident_24h", True), ("privacy_72h", True)]

    inc = api.post("/api/reports/incident-24h?format=markdown", json={"incident": body})
    assert inc.status_code == 200 and "# 침해사고 신고서 초안" in inc.text

    pri = api.post("/api/reports/privacy-72h", json={"incident": body})
    assert pri.status_code == 200 and pri.json()["kind"] == "privacy_72h"


@pytest.mark.parametrize(
    ("path", "payload"),
    [
        ("/api/reports/assess", incident(discovered_at="2026-10-31T08:00:00")),  # 시간대 없음
        ("/api/reports/assess", incident(incident_types=["alien"])),
        ("/api/reports/incident-24h?format=pdf", {"incident": incident()}),
        ("/api/reports/privacy-72h", {"incident": incident(personal_info=breach(affected_count=-1))}),
    ],
    ids=["naive-time", "bad-type", "bad-format", "negative-count"],
)
def test_api_rejects_bad_requests(api, path, payload):
    assert api.post(path, json=payload).status_code == 422


def test_completed_next_steps_do_not_promise_unbuilt_alerts():
    # 매일 자동 검사·이메일 알림은 아직 구현되지 않았습니다. 완료 리포트가 이를 '된다'고 안내하면 안 됩니다
    from app.reports.plain import next_steps

    text = " ".join(next_steps([], completed=True).bullets)
    assert "알려 드립니다" not in text and "자동 검사는 계속" not in text
    assert "재검사" in text and "준비 중" in text
