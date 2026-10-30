"""리포트들이 같이 쓰는 기한 계산과 표기."""

import math
from datetime import datetime, timedelta

from app.reports.legal import KST
from app.reports.schemas import Deadline, FormField


def fmt_time(value: datetime | None) -> str | None:
    """사람이 읽는 한국 시각. 예: 2026-10-31(토) 09:00"""
    if value is None:
        return None
    local = value.astimezone(KST)
    weekday = "월화수목금토일"[local.weekday()]
    return f"{local:%Y-%m-%d}({weekday}) {local:%H:%M}"


def fmt_remaining(minutes: int) -> str:
    """남은 시간. 음수면 지난 시간으로 읽습니다."""
    sign_over = minutes < 0
    minutes = abs(minutes)
    hours, mins = divmod(minutes, 60)
    text = f"{hours}시간 {mins}분" if hours else f"{mins}분"
    return f"{text} 지남" if sign_over else f"{text} 남음"


def deadline(
    label: str, basis: str, starts_at: datetime, hours: int, now: datetime, stopped_at: datetime | None = None
) -> Deadline:
    due_at = starts_at + timedelta(hours=hours)
    # 완료되어 멈춘 타이머는 멈춘 시각 기준으로 남은 시간을 셉니다
    reference = stopped_at or now
    # 1분이라도 남았으면 0분으로 반올림하지 않습니다 (기한을 넘긴 것처럼 보이면 안 됨)
    remaining = math.floor((due_at - reference).total_seconds() / 60)
    return Deadline(
        label=label,
        basis=basis,
        starts_at=starts_at,
        due_at=due_at,
        hours=hours,
        remaining_minutes=remaining,
        overdue=remaining < 0,
        stopped_at=stopped_at,
    )


def deadline_sentence(d: Deadline) -> str:
    if d.stopped_at:
        state = "기한 안에 완료" if not d.overdue else "기한을 넘겨 완료"
        return f"{fmt_time(d.stopped_at)}에 {state}했습니다 (기한 {fmt_time(d.due_at)})."
    return f"기한 {fmt_time(d.due_at)} · {fmt_remaining(d.remaining_minutes)}"


def missing_labels(fields: list[FormField], prefix: str = "") -> list[str]:
    return [f"{prefix}{f.label}" for f in fields if f.required and not f.value]


def join_or_none(items: list[str], sep: str = ", ") -> str | None:
    items = [i.strip() for i in items if i and i.strip()]
    return sep.join(items) if items else None
