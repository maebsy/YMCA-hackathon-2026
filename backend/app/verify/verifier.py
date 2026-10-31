"""Before/After 실검증 오케스트레이션.

1. 대상 소스를 사본 두 벌로 복사 (before / after)
2. after 사본에 Blue의 수정(patch)을 적용
3. 샌드박스에서 각각 probe 실행 (공격 재생 + 기능 테스트)
4. 공격별로 '수정 전 성공 → 수정 후 차단' + '테스트 통과'를 확인해 판정

판정: verified(검증됨) / not_reproduced(오탐 후보) / fix_failed(수정 미흡) / error(실행 실패)
"""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from .sandbox import SandboxError, pick_sandbox
from .schemas import AttackOutcome, TestOutcome, VerifyRequest, VerifyResult


def _attack_cfg(attacks) -> list[dict]:
    out = []
    for a in attacks:
        if not a.runtime or not a.request:
            continue
        out.append({
            "id": a.id,
            "runtime": True,
            "request": a.request.model_dump(exclude_none=True),
            "success_when": a.success_when,
        })
    return out


def _apply_patch(after_dir: Path, patch) -> None:
    for rel, content in (patch.files or {}).items():
        target = (after_dir / rel).resolve()
        if after_dir.resolve() not in target.parents and target != after_dir.resolve():
            raise SandboxError(f"수정 경로가 대상 폴더를 벗어납니다: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _probe_cfg(req: VerifyRequest, cfg_attacks: list[dict]) -> dict:
    return {
        "attacks": cfg_attacks,
        "port": 3100,
        "startCmd": req.start_cmd,
        "testCmd": req.test_cmd,
        "runTests": req.run_tests,
        "startTimeoutMs": 20000,
    }


def verify(req: VerifyRequest, *, trusted: bool = False) -> VerifyResult:
    """trusted=True 는 우리 데모 과녁 전용(Docker 없으면 Local 허용). 사용자 저장소는 trusted=False → Docker 필수."""
    started = time.monotonic()
    repo = Path(req.repo_dir).resolve()
    if not repo.is_dir():
        return VerifyResult(status="error", message=f"대상 폴더가 없습니다: {repo}")

    runtime_attacks = [a for a in req.attacks if a.runtime and a.request]
    if not runtime_attacks:
        return VerifyResult(status="error", message="런타임 공격이 정의된 항목이 없습니다.")

    cfg_attacks = _attack_cfg(runtime_attacks)
    try:
        sandbox = pick_sandbox(trusted)
    except SandboxError as exc:
        return VerifyResult(status="error", message=str(exc))

    with TemporaryDirectory() as tmp:
        before_dir = Path(tmp) / "before"
        after_dir = Path(tmp) / "after"
        ignore = shutil.ignore_patterns(".git")
        shutil.copytree(repo, before_dir, ignore=ignore)
        shutil.copytree(repo, after_dir, ignore=ignore)
        try:
            _apply_patch(after_dir, req.patch)
            before = sandbox.run(before_dir, _probe_cfg(req, cfg_attacks))
            after = sandbox.run(after_dir, _probe_cfg(req, cfg_attacks))
        except SandboxError as exc:
            return VerifyResult(status="error", sandbox=sandbox.name, message=str(exc),
                                duration_sec=round(time.monotonic() - started, 2))

    if not before.get("reachable"):
        return VerifyResult(status="error", sandbox=sandbox.name,
                            message=f"수정 전 앱이 뜨지 않았습니다: {before.get('appError', '')[:200]}",
                            duration_sec=round(time.monotonic() - started, 2))

    b_map = {r["id"]: r for r in before.get("attacks", [])}
    a_map = {r["id"]: r for r in after.get("attacks", [])}
    outcomes: list[AttackOutcome] = []
    for a in runtime_attacks:
        b = b_map.get(a.id, {})
        af = a_map.get(a.id, {})
        b_ok, a_ok = bool(b.get("succeeded")), bool(af.get("succeeded"))
        verdict = "not_reproduced" if not b_ok else ("fix_failed" if a_ok else "verified")
        outcomes.append(AttackOutcome(
            id=a.id, before_succeeded=b_ok, after_succeeded=a_ok,
            before_status=b.get("status"), after_status=af.get("status"),
            before_evidence=b.get("evidence"), after_evidence=af.get("evidence"),
            verdict=verdict,
        ))

    before_tests = TestOutcome(**before.get("tests", {}))
    after_tests = TestOutcome(**after.get("tests", {}))

    verdicts = {o.verdict for o in outcomes}
    tests_broken = req.run_tests and after_tests.ok is False
    if "fix_failed" in verdicts or tests_broken:
        status, msg = "fix_failed", "수정 후에도 공격이 통하거나 기능 테스트가 깨졌습니다."
    elif verdicts == {"verified"} and not tests_broken:
        status, msg = "verified", "모든 공격이 수정 후 차단되고 기능 테스트를 통과했습니다."
    elif "not_reproduced" in verdicts:
        status, msg = "not_reproduced", "수정 전 공격이 재현되지 않았습니다(오탐 후보)."
    else:
        status, msg = "verified", "검증 완료."

    return VerifyResult(
        status=status, message=msg, sandbox=sandbox.name, attacks=outcomes,
        before_tests=before_tests, after_tests=after_tests,
        duration_sec=round(time.monotonic() - started, 2),
    )
