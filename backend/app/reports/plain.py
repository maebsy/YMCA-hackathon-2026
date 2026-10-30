"""비전공자용 점검 리포트 (④ 대응 안내 · ⑤ 완료 리포트).

LLM을 다시 부르지 않습니다. 이미 Red–Blue를 거친 해석(`ExplainResult`)과 탐지 결과를 사람이 읽는 순서로
다시 배치합니다. 그래서 몇 번을 만들어도 같은 입력이면 같은 리포트가 나오고 GPU를 쓰지 않습니다.

읽는 순서: 한눈에 보기 → 지금 바로 할 일 → 고칠 것 자세히 → 검사하지 못한 영역 → 다시 검사·해결된 것
→ 용어 풀이 → 다음 단계

- 같은 패키지의 의존성 취약점을 한 번에 설명한 결과(`covers`, #27)는 카드 하나로 묶어 보여 줍니다.
- 검사하지 못한 영역(`not_checked`)이나 다시 검사가 필요한 항목이 있으면 "완료"·"안전" 문구를 쓰지 않습니다(#28).
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from app.llm.prompts import redact_secrets
from app.llm.schemas import Explanation, FindingInput, Priority, Severity
from app.reports.common import deadline, deadline_sentence, fmt_time
from app.reports.legal import SERVICE_FIX_HOURS
from app.reports.schemas import Badge, Card, FormField, PlainReportRequest, Report, Section

State = Literal["open", "recheck", "resolved"]

SEVERITY_LABEL: dict[Severity, tuple[str, str]] = {
    "critical": ("매우 위험", "danger"),
    "high": ("위험", "danger"),
    "medium": ("주의", "warning"),
    "low": ("낮음", "info"),
    "info": ("참고", "muted"),
    "unknown": ("확인 필요", "muted"),
}
PRIORITY_LABEL: dict[Priority, tuple[str, str]] = {
    "now": ("지금 바로", "danger"),
    "soon": ("이번 주 안에", "warning"),
    "later": ("여유 있을 때", "info"),
}
# 보안엔진 coverage 의 도구 이름 → 사람이 읽는 검사 이름
TOOL_LABEL = {
    "osv": "외부 부품(라이브러리) 검사",
    "semgrep": "코드 검사",
    "gitleaks": "비밀키 검사",
    "config": "설정 검사",
}
CATEGORY_LABEL = {
    "secret": "비밀키 노출",
    "code": "코드",
    "dependency": "외부 부품(라이브러리)",
    "config": "설정",
}
PRIORITY_ORDER = {"now": 0, "soon": 1, "later": 2}
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5}

# 리포트에 나온 문제에 맞춰 용어 풀이를 붙입니다. CWE 번호나 제목의 단어로 고릅니다
GLOSSARY: list[tuple[tuple[str, ...], str, str]] = [
    (
        ("CWE-89", "SQL"),
        "SQL 주입",
        "주소창이나 입력칸에 넣은 글자가 데이터베이스 명령으로 실행되는 문제입니다. 남의 정보를 꺼내 갈 수 있습니다.",
    ),
    (
        ("CWE-79", "XSS"),
        "XSS(스크립트 끼워 넣기)",
        "다른 사람이 쓴 글에 숨겨 둔 코드가 방문자 화면에서 실행되는 문제입니다. 로그인 정보를 빼앗길 수 있습니다.",
    ),
    (
        ("CWE-798", "CWE-321", "service_role", "API 키", "비밀키"),
        "비밀키",
        "서비스에 들어가는 열쇠 같은 값입니다. 코드나 화면에 드러나면 누구나 그 열쇠로 들어올 수 있어 바로 바꿔야 합니다.",
    ),
    (
        ("CWE-284", "CWE-285", "CWE-639", "CWE-862", "권한"),
        "접근 권한 확인 누락",
        "로그인했는지, 본인 것인지 확인하지 않아 남의 정보나 관리자 기능에 들어갈 수 있는 문제입니다.",
    ),
    (
        ("RLS",),
        "RLS(행 단위 접근 제한)",
        "데이터베이스 표에서 사람마다 자기 줄만 볼 수 있게 막는 장치입니다. 꺼져 있으면 열쇠 하나로 모든 줄을 볼 수 있습니다.",
    ),
    (("CWE-22",), "경로 조작", "파일 이름을 바꿔 넣어 서버의 다른 파일을 열어 보는 공격입니다."),
    (("CWE-78",), "명령어 주입", "입력값이 서버의 명령으로 실행되는 문제입니다. 서버를 통째로 빼앗길 수 있습니다."),
    (("CWE-918", "SSRF"), "SSRF", "우리 서버가 공격자 대신 내부 주소로 요청을 보내게 만드는 문제입니다."),
    (("CWE-352", "CSRF"), "CSRF", "로그인한 사람이 모르는 사이에 다른 사이트를 통해 요청이 보내지는 문제입니다."),
    (
        ("CVE-",),
        "CVE 번호",
        "전 세계에 공개된 취약점에 붙는 일련번호입니다. 같은 번호로 검색하면 고친 버전을 찾을 수 있습니다.",
    ),
]


@dataclass
class Item:
    finding: FindingInput
    explanation: Explanation | None
    state: State
    # 같은 설명으로 함께 해결되는 다른 탐지 결과 (패키지 단위 묶음)
    members: list[FindingInput] = field(default_factory=list)

    @property
    def priority(self) -> Priority:
        if self.explanation:
            return self.explanation.priority
        # 해석이 아직 없으면 심각도로 대신 정합니다
        return {"critical": "now", "high": "now", "medium": "soon"}.get(self.finding.severity, "later")

    @property
    def title(self) -> str:
        text = self.explanation.summary if self.explanation else self.finding.title
        return redact_secrets(text) or self.finding.rule_id

    def sort_key(self) -> tuple:
        fp = bool(self.explanation and self.explanation.false_positive_suspect)
        return (fp, PRIORITY_ORDER[self.priority], SEVERITY_ORDER[self.finding.severity], self.finding.fingerprint)


def finding_state(finding: FindingInput) -> State:
    """LLM 단계의 건너뛰기 규칙(pipeline.skip_reason)과 같은 기준입니다."""
    if finding.status == "code_resolved" or (finding.status is None and finding.change == "resolved"):
        return "resolved"
    # 확인하지 못한 항목은 "지금 문제 있음"으로도 "해결됨"으로도 보여 주면 안 됩니다
    if finding.status == "out_of_scope" or (finding.status is None and finding.change == "unverifiable"):
        return "recheck"
    return "open"


def location(finding: FindingInput) -> str | None:
    if finding.package_name:
        version = f" {finding.installed_version}" if finding.installed_version else ""
        return f"{finding.package_name}{version}"
    if not finding.file_path:
        return None
    if finding.start_line and finding.end_line and finding.end_line != finding.start_line:
        return f"{finding.file_path} {finding.start_line}~{finding.end_line}줄"
    if finding.start_line:
        return f"{finding.file_path} {finding.start_line}줄"
    return finding.file_path


def verification_badge(explanation: Explanation | None) -> Badge | None:
    if explanation is None:
        return Badge(text="설명 준비 중", tone="muted")
    if explanation.false_positive_suspect:
        return Badge(text="오탐일 수 있음", tone="muted")
    if explanation.variant == "D":
        if explanation.needs_manual_review:
            return Badge(text="사람 확인 필요", tone="warning")
        return Badge(text="공격 검증 통과", tone="ok")
    return None


def finding_card(item: Item) -> Card:
    f, e = item.finding, item.explanation
    sev_text, sev_tone = SEVERITY_LABEL[f.severity]
    pri_text, pri_tone = PRIORITY_LABEL[item.priority]
    badges = [Badge(text=pri_text, tone=pri_tone), Badge(text=sev_text, tone=sev_tone)]
    badges.append(Badge(text=CATEGORY_LABEL[f.category], tone="info"))
    if badge := verification_badge(e):
        badges.append(badge)

    paragraphs: list[str] = []
    steps: list[str] = []
    fields: list[FormField] = []
    if e:
        paragraphs.append(e.why_risky)
        if e.attack_scenario:
            paragraphs.append(f"공격자는 이렇게 노릴 수 있어요: {e.attack_scenario}")
        if e.false_positive_suspect and e.false_positive_reason:
            paragraphs.append(f"오탐일 수 있는 이유: {e.false_positive_reason}")
        if e.needs_manual_review:
            paragraphs.append(
                "아래 고치는 방법을 공격 관점에서 끝까지 통과시키지 못했습니다. 적용한 뒤 개발자나 보안 담당자에게 한 번 더 봐 달라고 하세요."
            )
        steps = [f"{s.title} — {s.detail}" for s in e.fix_steps]
    else:
        paragraphs.append(
            "쉬운 설명을 아직 만들지 못했습니다. 아래 정보를 개발자에게 전달하거나 잠시 후 리포트를 다시 만들어 주세요."
        )
        if f.what:
            paragraphs.append(redact_secrets(f.what))
        # 엔진 힌트가 "규칙 설명(what)을 보라"는 내부용 문장이면 위 설명과 겹치므로 넣지 않습니다
        if f.fix_hint and f.fix_hint.text and "(what)" not in f.fix_hint.text:
            steps.append(redact_secrets(f.fix_hint.text))

    if f.fix_hint and f.fix_hint.command:
        fields.append(FormField(label="실행할 명령", value=f.fix_hint.command))
    if loc := location(f):
        fields.append(FormField(label="위치", value=loc))
    if item.members:
        listed = [
            f"{redact_secrets(m.title)}" + (f" ({', '.join(m.refs.cve)})" if m.refs.cve else "")
            for m in [f, *item.members]
        ]
        fields.append(
            FormField(
                label="함께 해결되는 문제",
                value=f"{len(listed)}건\n"
                + "\n".join(f"- {x}" for x in listed[:15])
                + (f"\n- 외 {len(listed) - 15}건" if len(listed) > 15 else ""),
                hint="같은 부품을 한 번 업그레이드하면 함께 고쳐집니다",
            )
        )
    refs = list(dict.fromkeys(r for m in [f, *item.members] for r in m.refs.cve + m.refs.cwe))
    if refs:
        fields.append(FormField(label="관련 번호", value=", ".join(refs[:20])))
    if e and e.ai_fix_prompt:
        fields.append(
            FormField(
                label="AI 코딩툴에 붙여 넣을 지시",
                value=e.ai_fix_prompt,
                hint="Cursor·Claude Code·Codex 대화창에 그대로 붙여 넣으세요",
            )
        )
    return Card(
        title=item.title, badges=badges, paragraphs=[redact_secrets(p) for p in paragraphs], fields=fields, steps=steps
    )


def _glossary_hit(key: str, refs: set[str], text: str) -> bool:
    # 번호는 정확히 같아야 합니다. 부분 일치로 보면 CWE-79(XSS)가 CWE-798(비밀키)에 걸립니다
    if key == "CVE-":
        return any(r.startswith("CVE-") for r in refs)
    if key.startswith("CWE-"):
        return key in refs
    return key.lower() in text


def glossary_for(items: list[Item]) -> list[str]:
    refs = {r.upper() for i in items for r in (*i.finding.refs.cwe, *i.finding.refs.cve)}
    text = " ".join(f"{i.finding.title} {i.finding.rule_id}" for i in items).lower()
    return [f"{term}: {meaning}" for keys, term, meaning in GLOSSARY if any(_glossary_hit(k, refs, text) for k in keys)]


def build_items(req: PlainReportRequest) -> list[Item]:
    """탐지 결과에 해석을 붙입니다. 패키지 단위 해석(covers)이 덮는 결과들은 카드 하나로 묶습니다."""
    explained: dict[str, tuple[str, Explanation]] = {}
    for r in req.explain_results:
        if r.status == "done" and r.explanation:
            for fp in {r.fingerprint, *r.covers}:
                explained[fp] = (r.fingerprint, r.explanation)

    items: list[Item] = []
    groups: dict[str, Item] = {}
    for f in req.findings:
        state = finding_state(f)
        group_key, explanation = explained.get(f.fingerprint, (None, None))
        # 묶음 해석은 아직 열린 결과에만 씁니다. 해결·재검사 항목은 각자 따로 보여 줍니다
        if explanation and group_key != f.fingerprint and state == "open":
            if group := groups.get(group_key):
                # 가장 위험한 결과를 대표로 두고 나머지는 members 로
                if SEVERITY_ORDER[f.severity] < SEVERITY_ORDER[group.finding.severity]:
                    group.members.append(group.finding)
                    group.finding = f
                else:
                    group.members.append(f)
                continue
            groups[group_key] = Item(f, explanation, state)
            items.append(groups[group_key])
            continue
        items.append(Item(f, explanation, state))
    return items


# 보안엔진 메시지 "종료 코드 127 (사람이 읽는 이유): 도구 원문 로그" 에서 이유만 꺼냅니다
_ENGINE_REASON = re.compile(r"^종료 코드 -?\d+ \((?P<reason>.+?)\)(?::|$)")


def friendly_reason(raw: str) -> str:
    text = (redact_secrets(raw.strip()) or "").splitlines()[0] if raw.strip() else ""
    if m := _ENGINE_REASON.match(text):
        return m.group("reason")
    # 도구 원문에는 서버의 임시 경로가 섞일 수 있어 경로처럼 보이는 부분을 지웁니다
    text = re.sub(r"(?:[A-Za-z]:)?[/\\][^\s:]+", "(경로)", text)
    return text[:200] or "도구가 결과를 내지 못했습니다"


def not_checked_lines(req: PlainReportRequest) -> list[str]:
    lines = []
    for nc in req.scan.not_checked:
        label = TOOL_LABEL.get(nc.tool, nc.tool)
        category = CATEGORY_LABEL.get(nc.category or "", "")
        head = f"{label}" + (f" ({category})" if category and category not in label else "")
        lines.append(f"{head}: {friendly_reason(nc.reason)}")
    return lines


def build_plain_report(req: PlainReportRequest, now: datetime) -> Report:
    items = build_items(req)
    open_items = sorted((i for i in items if i.state == "open"), key=Item.sort_key)
    recheck = [i for i in items if i.state == "recheck"]
    resolved = [i for i in items if i.state == "resolved"]
    unchecked = not_checked_lines(req)
    now_items = [
        i for i in open_items if i.priority == "now" and not (i.explanation and i.explanation.false_positive_suspect)
    ]
    # 검사하지 못한 영역이 있으면 문제가 0건이어도 "완료"라고 하지 않습니다 (#28)
    completed = not open_items and not recheck and not unchecked

    scan = req.scan
    site = scan.site_name
    timer = None
    if scan.detected_at:
        stopped = (scan.resolved_at or scan.scanned_at) if completed else None
        timer = deadline("72시간 해결 타이머", "72hours 서비스 기준", scan.detected_at, SERVICE_FIX_HOURS, now, stopped)

    # ── 상태 한 줄 ──
    if completed:
        status = Badge(text="완료", tone="ok")
        verdict = "확인한 문제가 모두 해결되었습니다. 재검사에서도 다시 나오지 않았습니다."
    elif now_items:
        status = Badge(text="위험", tone="danger")
        verdict = (
            f"지금 바로 고쳐야 할 문제가 {len(now_items)}건 있습니다. 오늘 안에 아래 '지금 바로 할 일'부터 처리하세요."
        )
    elif open_items:
        status = Badge(text="주의", tone="warning")
        verdict = f"급하지는 않지만 고쳐야 할 문제가 {len(open_items)}건 있습니다."
    else:
        status = Badge(text="다시 검사 필요", tone="warning")
        verdict = "찾은 문제는 없지만, 이번 검사에서 확인하지 못한 부분이 있어 안전하다고 말할 수 없습니다. 다시 검사해 주세요."

    counts = {p: sum(1 for i in open_items if i.priority == p) for p in PRIORITY_ORDER}
    overview = Section(
        heading="한눈에 보기",
        paragraphs=[verdict],
        fields=[
            FormField(label="점검한 곳", value=" · ".join(x for x in (site, scan.site_url, scan.repo) if x)),
            FormField(label="검사 시각", value=fmt_time(scan.scanned_at)),
            FormField(
                label="고칠 것",
                value=f"{len(open_items)}건 (지금 바로 {counts['now']} · 이번 주 {counts['soon']} · 여유 {counts['later']})",
            ),
            FormField(label="해결됨", value=f"{len(resolved)}건"),
            FormField(label="다시 검사 필요", value=f"{len(recheck)}건"),
        ],
    )
    if unchecked:
        overview.fields.append(FormField(label="검사하지 못한 영역", value=f"{len(unchecked)}곳 (아래 참고)"))
    if timer:
        overview.fields.append(FormField(label="72시간 타이머", value=deadline_sentence(timer)))
    sections = [overview]

    if now_items:
        sections.append(
            Section(
                heading="지금 바로 할 일",
                paragraphs=[
                    "위에서부터 순서대로 하세요. 하나씩 고칠 때마다 다시 검사하면 진행 상황이 바로 반영됩니다."
                ],
                steps=[
                    f"{i.title}" + (f" → {i.explanation.fix_steps[0].title}" if i.explanation else "")
                    for i in now_items
                ],
            )
        )

    if open_items:
        sections.append(
            Section(
                heading="고칠 것 자세히",
                paragraphs=[
                    "급한 순서로 정리했습니다. '공격 검증 통과'는 고치는 방법을 공격자 관점에서 다시 시험해 막히는 것을 확인했다는 뜻입니다."
                ],
                cards=[finding_card(i) for i in open_items],
            )
        )

    if unchecked:
        sections.append(
            Section(
                heading="이번에 검사하지 못한 영역",
                paragraphs=[
                    "아래 영역은 이번 검사에서 확인하지 못했습니다. 문제가 없다는 뜻이 아니니, 원인을 해결한 뒤 다시 검사해 주세요."
                ],
                bullets=unchecked,
            )
        )
    if recheck:
        sections.append(
            Section(
                heading="다시 검사가 필요한 것",
                paragraphs=[
                    "검사 도구가 이번에는 확인하지 못한 항목입니다. 문제가 있다는 뜻은 아니지만, 다시 검사해야 결과를 알 수 있습니다."
                ],
                bullets=[redact_secrets(i.finding.title) for i in recheck],
            )
        )
    if resolved:
        sections.append(Section(heading="해결된 것", bullets=[redact_secrets(i.finding.title) for i in resolved]))

    if terms := glossary_for(open_items + recheck):
        sections.append(Section(heading="용어 풀이", bullets=terms))

    sections.append(next_steps(open_items, completed, bool(unchecked or recheck)))

    if completed:
        title, subtitle = f"{site} 보안 조치 완료 리포트", "발견한 문제를 모두 고치고 재검사로 확인했습니다."
    else:
        title, subtitle = f"{site} 보안 점검 리포트", "개발자가 아니어도 읽을 수 있게 정리했습니다."
    return Report(
        kind="plain",
        title=title,
        subtitle=subtitle,
        generated_at=now,
        status=status,
        deadline=timer,
        sections=sections,
    )


def next_steps(open_items: list[Item], completed: bool, needs_rescan: bool = False) -> Section:
    if completed:
        return Section(
            heading="앞으로",
            bullets=[
                "매일 자동 검사는 계속됩니다. 새 취약점이 공개되면 이메일로 알려 드립니다.",
                "코드를 고치거나 새 기능을 넣은 뒤에는 한 번 더 검사해 주세요.",
            ],
        )
    if not open_items:
        # 고칠 것은 없고 확인만 남은 경우: 원인을 풀고 다시 검사하는 것이 다음 할 일입니다
        steps = [
            "'이번에 검사하지 못한 영역'의 이유를 확인하세요. 잠금 파일(package-lock.json 등)이 없거나 검사 도구가 실패한 경우가 많습니다.",
            "원인을 해결한 뒤 대시보드에서 '다시 검사'를 누르세요.",
            "모든 영역이 확인되면 완료 리포트가 만들어지고 72시간 타이머가 멈춥니다.",
        ]
        return Section(heading="다음 단계", steps=steps)
    steps = [
        "'지금 바로 할 일'을 위에서부터 처리하세요. 'AI 코딩툴에 붙여 넣을 지시'를 복사해 쓰면 빠릅니다.",
        "고친 뒤 대시보드에서 '다시 검사'를 누르세요. 해결된 항목은 자동으로 '해결된 것'으로 옮겨집니다.",
        "모두 해결되면 완료 리포트가 만들어지고 72시간 타이머가 멈춥니다.",
    ]
    bullets = []
    if needs_rescan:
        bullets.append(
            "검사하지 못한 영역이나 다시 검사가 필요한 항목이 있습니다. 모두 확인되어야 완료 리포트가 만들어집니다."
        )
    # 비밀키가 이미 공개 저장소·브라우저에 나갔다면 누군가 이미 썼을 수 있습니다. 신고 판단으로 이어지게 안내합니다
    if any(i.finding.category == "secret" for i in open_items):
        bullets.append(
            "비밀키는 고치기 전에 이미 누군가 썼을 수 있습니다. 해당 서비스의 접속 기록을 확인하고, 모르는 접속이나 "
            "데이터 조회 흔적이 있으면 '신고 도우미'를 여세요. 침해사고는 알게 된 때부터 24시간, 개인정보 유출은 72시간 안에 신고해야 합니다."
        )
    return Section(heading="다음 단계", steps=steps, bullets=bullets)
