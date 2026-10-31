import asyncio
import time

import pytest
from fastapi import HTTPException
from pydantic import BaseModel

from app.llm.preview_jobs import PreviewJobs
from tests.test_api import api, sample_findings  # noqa: F401
from tests.conftest import blue_draft


class Result(BaseModel):
    value: str = "done"


@pytest.mark.anyio
async def test_capacity_and_running_jobs_survive_completed_eviction():
    queue = PreviewJobs(capacity=2, running=2, kept=0)
    gate = asyncio.Event()
    async def slow():
        await gate.wait()
        return Result()
    async def fast():
        return Result()
    first = queue.submit(slow)["job_id"]
    queue.submit(fast)
    with pytest.raises(HTTPException) as exc:
        queue.submit(fast)
    assert exc.value.status_code == 429
    await asyncio.sleep(0)
    assert queue.get(first)["status"] == "running"
    assert len(queue.jobs) == 1
    await queue.aclose()
    assert not queue.tasks


@pytest.mark.anyio
async def test_deadline_includes_waiting_and_jobs_expire():
    queue = PreviewJobs(timeout=0.02, running=1)
    async def slow():
        await asyncio.Event().wait()
    ids = [queue.submit(slow)["job_id"] for _ in range(2)]
    await asyncio.gather(*list(queue.tasks))
    assert all(queue.get(key)["error"]["code"] == "LLM_JOB_TIMEOUT" for key in ids)
    queue.ttl = 0
    with pytest.raises(HTTPException) as exc:
        queue.get(ids[0])
    assert exc.value.status_code == 404


def test_http_accepts_then_returns_completed_result(api, fake_vllm):
    fake_vllm.queue("BlueDraft", blue_draft())
    response = api.post("/api/llm/explain/tasks", json={"findings": sample_findings(1), "mode":"blue"})
    assert response.status_code == 202
    job_id = response.json()["job_id"]
    for _ in range(100):
        result = api.get("/api/llm/explain/tasks/" + job_id).json()
        if result["status"] in ("done", "failed"):
            break
        time.sleep(0.01)
    assert result["status"] == "done"
    assert result["result"]["results"][0]["status"] == "done"
    assert api.get("/api/llm/explain/tasks/missing").status_code == 404


def test_job_does_not_turn_gpu_failure_into_success(api, fake_vllm):
    fake_vllm.queue("BlueDraft", 503, 503, 503)
    job = api.post("/api/llm/explain/tasks", json={"findings": sample_findings(1), "mode":"blue"}).json()
    for _ in range(100):
        result = api.get("/api/llm/explain/tasks/" + job["job_id"]).json()
        if result["status"] == "failed":
            break
        time.sleep(0.01)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "LLM_UNAVAILABLE"
