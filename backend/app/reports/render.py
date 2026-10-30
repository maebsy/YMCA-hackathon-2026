"""`Report`를 마크다운과 인쇄용 HTML로 바꿉니다.

- 마크다운: 이슈·메일·노션에 붙여 넣기용
- HTML: 외부 파일 없이 한 장으로 열리는 문서. 브라우저에서 인쇄하면 A4 PDF가 됩니다 (신고서 첨부·보관용)
"""

from html import escape

from app.reports.common import deadline_sentence, fmt_time
from app.reports.schemas import Badge, Card, FormField, Report, Section

TONE_MARK = {"danger": "🔴", "warning": "🟠", "ok": "🟢", "info": "🔵", "muted": "⚪"}

# ── 마크다운 ──


def _md_value(field: FormField) -> str:
    if not field.value:
        return "**(작성 필요)**" if field.required else "-"
    value = field.value.replace("\n", "<br>")
    return f"{value} _(제안값, 확인 필요)_" if field.auto else value


def _md_fields(fields: list[FormField]) -> list[str]:
    if not fields:
        return []
    lines = ["| 항목 | 내용 |", "|---|---|"]
    for f in fields:
        label = f"{f.label} *" if f.required else f.label
        lines.append(f"| {label} | {_md_value(f).replace('|', '｜')} |")
    return lines + [""]


def _md_badges(badges: list[Badge]) -> str:
    return " ".join(f"`{TONE_MARK[b.tone]} {b.text}`" for b in badges)


def _md_card(card: Card) -> list[str]:
    lines = [f"### {card.title}", ""]
    if card.badges:
        lines += [_md_badges(card.badges), ""]
    for p in card.paragraphs:
        lines += [p, ""]
    if card.steps:
        lines += ["**고치는 방법**", ""] + [f"{i}. {s}" for i, s in enumerate(card.steps, 1)] + [""]
    lines += _md_fields(card.fields)
    return lines


def _md_section(section: Section) -> list[str]:
    lines = [f"## {section.heading}", ""]
    for p in section.paragraphs:
        lines += [p, ""]
    lines += _md_fields(section.fields)
    if section.steps:
        lines += [f"{i}. {s}" for i, s in enumerate(section.steps, 1)] + [""]
    if section.bullets:
        lines += [f"- {b}" for b in section.bullets] + [""]
    for card in section.cards:
        lines += _md_card(card)
    return lines


def to_markdown(report: Report) -> str:
    lines = [f"# {report.title}", ""]
    if report.subtitle:
        lines += [report.subtitle, ""]
    lines += [f"**상태** {TONE_MARK[report.status.tone]} {report.status.text} · 작성 {fmt_time(report.generated_at)}"]
    if report.deadline:
        lines += [f"**{report.deadline.label}** {deadline_sentence(report.deadline)} ({report.deadline.basis})"]
    lines.append("")
    if report.missing:
        lines += ["> **제출 전에 채울 칸**: " + ", ".join(report.missing), ""]
    for section in report.sections:
        lines += _md_section(section)
    if report.submit_to:
        lines += ["## 제출처", ""] + [f"- {s}" for s in report.submit_to] + [""]
    if report.disclaimer:
        lines += [f"> {report.disclaimer}", ""]
    return "\n".join(lines).rstrip() + "\n"


# ── HTML ──

_CSS = """
:root{--fg:#14202b;--muted:#5b6b7a;--line:#d5dde3;--bg:#fff;--soft:#f3f6f8;
--danger:#b4232c;--danger-bg:#fbe4e4;--warning:#9a5b00;--warning-bg:#fdf0d8;--ok:#0a7a52;--ok-bg:#dcf3e8;
--info:#1d5fa8;--info-bg:#e1ecf8;--muted-bg:#eceff2}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.65 "Pretendard","Noto Sans KR","Apple SD Gothic Neo","Malgun Gothic",system-ui,sans-serif;word-break:keep-all;overflow-wrap:anywhere}
main{max-width:860px;margin:0 auto;padding:40px 20px 64px}
h1{font-size:26px;line-height:1.3;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 16px}
.meta{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;padding:14px 16px;border:1px solid var(--line);border-radius:8px;background:var(--soft)}
.meta .due{font-weight:700}
.missing{margin:16px 0 0;padding:12px 16px;border-left:4px solid var(--warning);background:var(--warning-bg);border-radius:6px}
h2{font-size:19px;margin:32px 0 10px;padding-bottom:6px;border-bottom:2px solid var(--fg)}
h3{font-size:16px;margin:0 0 8px}
p{margin:0 0 10px}
table{width:100%;border-collapse:collapse;margin:6px 0 12px}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{width:32%;background:var(--soft);font-weight:600}
td .need{color:var(--danger);font-weight:700}
td .auto{display:inline-block;margin-top:4px;font-size:12px;color:var(--info)}
.hint{display:block;margin-top:2px;font-size:12px;color:var(--muted)}
.req{color:var(--danger)}
.card{border:1px solid var(--line);border-radius:8px;padding:16px;margin:0 0 12px;break-inside:avoid}
.badges{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 10px}
.badge{display:inline-block;padding:2px 9px;border-radius:999px;font-size:12.5px;font-weight:600}
.danger{color:var(--danger);background:var(--danger-bg)}.warning{color:var(--warning);background:var(--warning-bg)}
.ok{color:var(--ok);background:var(--ok-bg)}.info{color:var(--info);background:var(--info-bg)}.muted{color:var(--muted);background:var(--muted-bg)}
ol,ul{margin:0 0 12px;padding-left:22px}li{margin:3px 0}
.submit{padding:12px 16px;border:1px solid var(--line);border-radius:8px}
.disclaimer{margin-top:24px;font-size:13px;color:var(--muted)}
.copy{white-space:pre-wrap;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:13px}
@page{size:A4;margin:14mm}
@media print{main{padding:0;max-width:none}.card,table,tr{break-inside:avoid}h2{break-after:avoid}}
"""


def _e(text: str | None) -> str:
    return escape(text or "").replace("\n", "<br>")


def _h_badge(b: Badge) -> str:
    return f'<span class="badge {b.tone}">{_e(b.text)}</span>'


def _h_fields(fields: list[FormField]) -> str:
    if not fields:
        return ""
    rows = []
    for f in fields:
        label = _e(f.label) + (' <span class="req">*</span>' if f.required else "")
        hint = f'<span class="hint">{_e(f.hint)}</span>' if f.hint else ""
        if f.value:
            css = ' class="copy"' if f.label.startswith("AI 코딩툴") else ""
            value = f"<div{css}>{_e(f.value)}</div>"
            if f.auto:
                value += '<span class="auto">서비스가 제안한 값 · 제출 전 확인</span>'
        else:
            value = '<span class="need">작성 필요</span>' if f.required else "-"
        rows.append(f"<tr><th>{label}{hint}</th><td>{value}</td></tr>")
    return "<table>" + "".join(rows) + "</table>"


def _h_list(items: list[str], ordered: bool) -> str:
    if not items:
        return ""
    tag = "ol" if ordered else "ul"
    return f"<{tag}>" + "".join(f"<li>{_e(i)}</li>" for i in items) + f"</{tag}>"


def _h_card(card: Card) -> str:
    badges = f'<div class="badges">{"".join(_h_badge(b) for b in card.badges)}</div>' if card.badges else ""
    paragraphs = "".join(f"<p>{_e(p)}</p>" for p in card.paragraphs)
    steps = f"<p><strong>고치는 방법</strong></p>{_h_list(card.steps, True)}" if card.steps else ""
    return f'<div class="card"><h3>{_e(card.title)}</h3>{badges}{paragraphs}{steps}{_h_fields(card.fields)}</div>'


def _h_section(s: Section) -> str:
    return (
        f"<section><h2>{_e(s.heading)}</h2>"
        + "".join(f"<p>{_e(p)}</p>" for p in s.paragraphs)
        + _h_fields(s.fields)
        + _h_list(s.steps, True)
        + _h_list(s.bullets, False)
        + "".join(_h_card(c) for c in s.cards)
        + "</section>"
    )


def to_html(report: Report) -> str:
    meta = [_h_badge(report.status), f"<span>작성 {_e(fmt_time(report.generated_at))}</span>"]
    if d := report.deadline:
        meta.append(f'<span class="due">{_e(d.label)}: {_e(deadline_sentence(d))}</span>')
        meta.append(f'<span class="hint">{_e(d.basis)}</span>')
    missing = (
        f'<div class="missing"><strong>제출 전에 채울 칸</strong><br>{_e(", ".join(report.missing))}</div>'
        if report.missing
        else ""
    )
    submit = (
        f'<section><h2>제출처</h2><div class="submit">{_h_list(report.submit_to, False)}</div></section>'
        if report.submit_to
        else ""
    )
    disclaimer = f'<p class="disclaimer">{_e(report.disclaimer)}</p>' if report.disclaimer else ""
    subtitle = f'<p class="sub">{_e(report.subtitle)}</p>' if report.subtitle else ""
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{_e(report.title)}</title><style>{_CSS}</style></head><body><main>"
        f"<h1>{_e(report.title)}</h1>{subtitle}"
        f'<div class="meta">{"".join(meta)}</div>{missing}'
        + "".join(_h_section(s) for s in report.sections)
        + submit
        + disclaimer
        + "</main></body></html>"
    )
