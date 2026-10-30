"""Run separately: python -m app.explain_jobs.worker (never inside an HTTP background task)."""

import asyncio
import logging

from app.explain_jobs.config import job_settings
from app.explain_jobs.store import JobStore
from app.llm.schemas import FindingInput

log = logging.getLogger(__name__)


async def run_once(store, explainer, config=job_settings):
    await asyncio.to_thread(store.enqueue_ready)
    claim = await asyncio.to_thread(store.claim, config.llm_job_lease_s)
    if claim is None:
        return False
    task = None
    try:
        if claim.get("invalid_context"):
            raise ValueError("Invalid scanner context")
        finding = FindingInput.model_validate(claim["input"])
        task = asyncio.create_task(asyncio.wait_for(
            explainer.explain_many([finding], "red_blue"), timeout=config.llm_job_timeout_s,
        ))
        while True:
            done, _ = await asyncio.wait({task}, timeout=config.llm_job_lease_s / 3)
            if done:
                results = task.result()
                if len(results) != 1:
                    raise ValueError("Unexpected result count")
                await asyncio.to_thread(store.complete, claim, results[0])
                break
            if not await asyncio.to_thread(store.heartbeat, claim["id"], claim["token"], config.llm_job_lease_s):
                break  # Another worker owns the expired lease; never write its result.
    except TimeoutError:
        await asyncio.to_thread(store.fail, claim, "LLM_JOB_TIMEOUT")
    except Exception as exc:
        # No prompt, token, provider error body or connection string in logs/API errors.
        log.warning("LLM job failed (%s)", type(exc).__name__)
        await asyncio.to_thread(store.fail, claim, "LLM_JOB_FAILED")
    finally:
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    return True


async def main():
    if not job_settings.llm_jobs_enabled:
        raise RuntimeError("Set LLM_JOBS_ENABLED=true only after schema/auth deployment review")
    from app.db import engine
    from app.llm import create_explainer

    store = JobStore(engine)
    explainer = create_explainer()
    try:
        while True:
            try:
                worked = await run_once(store, explainer)
            except Exception as exc:
                log.warning("Queue unavailable (%s); committed jobs remain queued", type(exc).__name__)
                worked = False
            if not worked:
                await asyncio.sleep(job_settings.llm_job_poll_s)
    finally:
        await explainer.aclose()  # LLM 연결과 위협 정보(KEV·EPSS) 연결을 함께 닫음
        engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass  # The durable lease makes interrupted jobs recoverable on restart.
