"""실검증 작업 대기열: 접수 → 작업 번호 → 조회 (검사 API와 같은 방식).

실검증은 수정 전·후로 앱을 두 번 띄우고 기능 테스트까지 돌려 수십 초~수 분 걸립니다. 요청을 붙잡고 기다리면
프록시·터널의 응답 제한(Cloudflare 약 100초)에 걸리므로 작업 번호를 먼저 돌려줍니다.

- 결과는 메모리에만 둡니다. 서버를 다시 켜면 사라지고, 같은 데모 과녁으로 다시 실행하면 됩니다.
- 한 번에 1건만 실행합니다. LocalSandbox는 데모 앱을 고정 포트(3100)로 띄워서 두 건이 겹치면 서로 방해합니다.
- 작업은 맡긴 사용자만 조회합니다 (로그인을 끈 서버에서는 모두 None이라 작업 번호를 아는 사람이 조회).
- 실행 시간 제한은 샌드박스의 프로세스 제한 시간이 맡습니다. 여기서 따로 끊으면 스레드는 계속 도는데
  자리만 비어 다음 작업이 같은 포트로 겹쳐 뜨기 때문입니다.
"""
import asyncio
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Callable

from fastapi import HTTPException
from fastapi.concurrency import run_in_threadpool

from .schemas import VerifyResult

log = logging.getLogger(__name__)


class VerifyJobs:
    def __init__(self, *, capacity: int = 3, running: int = 1, kept: int = 20, ttl: int = 1800):
        self.capacity, self.kept, self.ttl = capacity, kept, ttl
        self.jobs: OrderedDict[str, dict] = OrderedDict()
        self.tasks: set[asyncio.Task] = set()
        self.slots = asyncio.Semaphore(running)

    def _prune(self) -> None:
        now = time.monotonic()
        finished = [k for k, job in self.jobs.items() if job["finished"] is not None]
        for k in finished:
            if now - self.jobs[k]["finished"] >= self.ttl:
                del self.jobs[k]
        finished = [k for k, job in self.jobs.items() if job["finished"] is not None]
        for k in finished[:max(0, len(finished) - self.kept)]:
            del self.jobs[k]

    def submit(self, work: Callable[[], VerifyResult], *, owner=None, extra: dict | None = None) -> dict:
        """work는 스레드에서 도는 동기 함수입니다(verify()가 subprocess를 기다리므로). extra는 조회 응답에 그대로 붙입니다."""
        self._prune()
        if sum(job["finished"] is None for job in self.jobs.values()) >= self.capacity:
            raise HTTPException(429, detail={"code": "VERIFY_QUEUE_FULL",
                                             "message": "실검증이 이미 돌고 있습니다. 1~2분 뒤 다시 시도해 주세요."},
                                headers={"Retry-After": "60"})
        key = uuid.uuid4().hex
        self.jobs[key] = {"job_id": key, "status": "queued", "result": None, "error": None,
                          **(extra or {}), "owner": owner, "finished": None}
        task = asyncio.create_task(self._run(key, work))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return {"job_id": key, "status": "queued"}

    async def _run(self, key: str, work: Callable[[], VerifyResult]) -> None:
        job = self.jobs[key]
        try:
            async with self.slots:
                job["status"] = "running"
                result = await run_in_threadpool(work)
                job["result"] = result.model_dump(mode="json")
                job["status"] = "done"
        except asyncio.CancelledError:
            job.update(status="failed", error={"code": "VERIFY_INTERRUPTED",
                                               "message": "서버가 중단되어 실검증이 멈췄습니다. 다시 실행해 주세요."})
            raise
        except Exception as exc:
            # 예외 원문에는 서버 경로가 섞일 수 있어 화면에는 고정 문구만 보냅니다
            log.warning("verify job %s failed: %s", key, type(exc).__name__)
            job.update(status="failed", error={"code": "VERIFY_ERROR",
                                               "message": "실검증 실행 중 오류가 났습니다. 서버 로그를 확인해 주세요."})
        finally:
            job["finished"] = time.monotonic()
            self._prune()

    def get(self, key: str, *, owner=None) -> dict:
        self._prune()
        job = self.jobs.get(key)
        if job is None or job["owner"] != owner:
            raise HTTPException(404, detail={"code": "VERIFY_JOB_NOT_FOUND",
                                             "message": "실검증 작업을 찾을 수 없습니다. 서버가 다시 켜졌다면 다시 실행해 주세요."})
        return {k: v for k, v in job.items() if k not in ("owner", "finished")}

    async def aclose(self) -> None:
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
