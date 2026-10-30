from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.reports import filing, plain, render
from app.reports.schemas import (
    AssessResponse,
    FilingRequest,
    IncidentInput,
    PlainReportRequest,
    Report,
    ReportFormat,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def get_now() -> datetime:
    # 테스트에서 시각을 고정할 수 있게 의존성으로 둡니다
    return datetime.now(timezone.utc)


NowDep = Annotated[datetime, Depends(get_now)]
FormatQuery = Annotated[
    ReportFormat, Query(description="json: 화면용 구조, markdown: 붙여 넣기용, html: 인쇄·PDF 저장용")
]

# 세 형식을 같은 주소에서 내보내므로 OpenAPI 문서에 응답 형식을 함께 적습니다
_RESPONSES = {
    200: {
        "content": {
            "application/json": {},
            "text/markdown": {"schema": {"type": "string"}},
            "text/html": {"schema": {"type": "string"}},
        }
    }
}


def respond(report: Report, fmt: ReportFormat):
    if fmt == "markdown":
        return PlainTextResponse(render.to_markdown(report), media_type="text/markdown; charset=utf-8")
    if fmt == "html":
        return HTMLResponse(render.to_html(report))
    return report


@router.post("/plain", response_model=Report, responses=_RESPONSES)
def plain_report(body: PlainReportRequest, now: NowDep, format: FormatQuery = "json"):
    """비전공자용 점검 리포트. 열린 문제가 없으면 완료 리포트가 되고 72시간 타이머가 멈춥니다.

    `explain_results`에는 `/api/llm/explain` 응답의 `results`를 그대로 넣으면 됩니다.
    """
    return respond(plain.build_plain_report(body, now), format)


@router.post("/assess", response_model=AssessResponse)
def assess(body: IncidentInput, now: NowDep):
    """사고 정보로 침해사고(24시간)·개인정보 유출(72시간) 신고가 필요한지와 기한을 알려 줍니다."""
    return filing.assess(body, now)


@router.post("/incident-24h", response_model=Report, responses=_RESPONSES)
def incident_report(body: FilingRequest, now: NowDep, format: FormatQuery = "json"):
    """KISA 침해사고 신고서 초안 (정보통신망법, 알게 된 때부터 24시간)."""
    return respond(filing.build_incident_report(body, now), format)


@router.post("/privacy-72h", response_model=Report, responses=_RESPONSES)
def privacy_report(body: FilingRequest, now: NowDep, format: FormatQuery = "json"):
    """개인정보 유출 신고서 초안과 정보주체 통지문 (개인정보 보호법, 알게 된 때부터 72시간)."""
    return respond(filing.build_privacy_report(body, now), format)
