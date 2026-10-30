from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response
from pydantic import BaseModel, ConfigDict

from app.explain_jobs.auth import UserDep
from app.explain_jobs.store import JobStore, NotFound, ScanNotReady

router = APIRouter(tags=["explanation-jobs"])


def get_store(request: Request) -> JobStore:
    return request.app.state.job_store


StoreDep = Annotated[JobStore, Depends(get_store)]
ScanId = Annotated[int, Path(gt=0)]


class EnqueueRequest(BaseModel):
    # Only the scan ID in the URL is accepted; forbid a hidden arbitrary-prompt API.
    model_config = ConfigDict(extra="forbid")


@router.post("/scans/{scan_id}/explanations", status_code=202)
def enqueue(scan_id: ScanId, body: EnqueueRequest, user: UserDep, store: StoreDep, response: Response):
    try:
        ids = store.enqueue(scan_id, user)
    except NotFound:
        raise HTTPException(404, "SCAN_NOT_FOUND") from None
    except ScanNotReady:
        raise HTTPException(409, "SCAN_NOT_READY") from None
    response.headers["Cache-Control"] = "no-store"
    response.headers["Location"] = f"/api/scans/{scan_id}/explanations"
    return {"scan_id": scan_id, "queued_job_ids": ids, "poll_after_seconds": 2}


@router.get("/scans/{scan_id}/explanations")
def results(scan_id: ScanId, user: UserDep, store: StoreDep, response: Response,
            after_id: Annotated[int, Query(ge=0)] = 0,
            limit: Annotated[int, Query(ge=1, le=50)] = 50):
    try:
        result = store.list_results(scan_id, user, after_id, limit)
    except NotFound:
        raise HTTPException(404, "SCAN_NOT_FOUND") from None
    response.headers["Cache-Control"] = "no-store"
    return result
