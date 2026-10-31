"""Bounded, temporary jobs for the legacy demo API; #26 retains durable authenticated jobs.

This queue exists only while LLM_JOBS_ENABLED=false. A restart loses its results.
The public demo must retain its proxy authentication; this is not per-user storage.
"""
import asyncio
import logging
import time
import uuid
from collections import OrderedDict

from fastapi import HTTPException

log = logging.getLogger(__name__)


class PreviewJobs:
    def __init__(self, *, capacity=15, running=6, kept=50, timeout=900, ttl=1800):
        self.capacity, self.kept, self.timeout, self.ttl = capacity, kept, timeout, ttl
        self.jobs = OrderedDict()
        self.tasks = set()
        self.slots = asyncio.Semaphore(running)

    def _prune(self):
        finished = [key for key, job in self.jobs.items() if job["finished"] is not None]
        for key in finished:
            if time.monotonic() - self.jobs[key]["finished"] >= self.ttl:
                del self.jobs[key]
        finished = [key for key, job in self.jobs.items() if job["finished"] is not None]
        for key in finished[:max(0, len(finished) - self.kept)]:
            del self.jobs[key]

    def submit(self, work):
        self._prune()
        if sum(job["finished"] is None for job in self.jobs.values()) >= self.capacity:
            raise HTTPException(429, detail={"code": "LLM_QUEUE_FULL", "message": "AI 해석 대기열이 가득 찼습니다. 잠시 후 다시 시도해 주세요."})
        key = uuid.uuid4().hex
        self.jobs[key] = {"job_id": key, "status": "queued", "result": None, "error": None, "finished": None}
        task = asyncio.create_task(self._run(key, work))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return {"job_id": key, "status": "queued"}

    async def _run(self, key, work):
        job = self.jobs[key]
        try:
            # The deadline includes waiting for a GPU slot.
            async with asyncio.timeout(self.timeout):
                async with self.slots:
                    job["status"] = "running"
                    result = await work()
                    job["result"] = result.model_dump(mode="json")
                    job["status"] = "done"
        except TimeoutError:
            job.update(status="failed", error={"code": "LLM_JOB_TIMEOUT", "message": "AI 해석 제한 시간을 초과했습니다."})
        except HTTPException as exc:
            job.update(status="failed", error=exc.detail)
        except asyncio.CancelledError:
            job.update(status="failed", error={"code": "LLM_JOB_CANCELLED", "message": "서버 종료로 해석이 중단됐습니다."})
            raise
        except Exception:
            log.exception("Temporary LLM job failed: %s", key)
            job.update(status="failed", error={"code": "LLM_JOB_ERROR", "message": "AI 해석 중 오류가 발생했습니다."})
        finally:
            job["finished"] = time.monotonic()
            self._prune()

    def get(self, key):
        self._prune()
        if key not in self.jobs:
            raise HTTPException(404, detail={"code": "LLM_JOB_NOT_FOUND", "message": "해석 작업이 만료됐거나 서버가 재시작됐습니다. 다시 검사해 주세요."})
        return {name: value for name, value in self.jobs[key].items() if name != "finished"}

    async def aclose(self):
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
