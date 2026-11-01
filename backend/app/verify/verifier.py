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
from .schemas import AttackOutcome, Isolation, TestOutcome, VerifyRequest, VerifyResult


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
        # symlinks=True: 저장소 안의 심볼릭 링크를 따라가지 않고 링크 자체만 복사합니다.
        # (따라가면 링크가 가리키는 서버 파일 내용이 사본·Docker 빌드 컨텍스트로 들어갈 수 있음)
        shutil.copytree(repo, before_dir, ignore=ignore, symlinks=True)
        shutil.copytree(repo, after_dir, ignore=ignore, symlinks=True)
        try:
            _apply_patch(after_dir, req.patch)
            before = sandbox.run(before_dir, _probe_cfg(req, cfg_attacks))
            after = sandbox.run(after_dir, _probe_cfg(req, cfg_attacks))
        except SandboxError as exc:
            return VerifyResult(status="error", sandbox=sandbox.name, message=str(exc),
                                duration_sec=round(time.monotonic() - started, 2))

    elapsed = lambda: round(time.monotonic() - started, 2)  # noqa: E731
    before_tests = TestOutcome(**before.get("tests", {}))
    after_tests = TestOutcome(**after.get("tests", {}))
    isolation = _merge_isolation(before.get("isolation"), after.get("isolation"))
    iso = {"isolation": isolation, "isolation_confirmed": isolation.confirmed}
    # 사용자 저장소는 '격리돼 있다'를 실행 결과로 확인해야만 판정을 내놓습니다 (코드상 옵션만으로는 부족).
    if not trusted and not isolation.confirmed:
        return VerifyResult(status="error", sandbox=sandbox.name,
                            message="샌드박스 격리를 확인하지 못해 실제검증 결과를 내지 않습니다: "
                                    + ", ".join(k for k, val in isolation.model_dump().items() if val is not True),
                            before_tests=before_tests, after_tests=after_tests, duration_sec=elapsed(), **iso)

    if not before.get("reachable"):
        return VerifyResult(status="error", sandbox=sandbox.name,
                            message=f"수정 전 앱이 뜨지 않았습니다: {before.get('appError', '')[:200]}",
                            before_tests=before_tests, after_tests=after_tests, duration_sec=elapsed(), **iso)
    # 수정본이 앱 시작을 깨뜨리면 공격 결과가 비어 '차단'처럼 보입니다. 이건 차단이 아니라 수정 실패입니다.
    if not after.get("reachable"):
        return VerifyResult(status="fix_failed", sandbox=sandbox.name,
                            message=f"수정 후 앱이 뜨지 않았습니다: {after.get('appError', '')[:200]}",
                            before_tests=before_tests, after_tests=after_tests, duration_sec=elapsed(), **iso)

    b_map = {r["id"]: r for r in before.get("attacks", [])}
    a_map = {r["id"]: r for r in after.get("attacks", [])}
    # 결과에 공격이 빠져 있으면 판정할 근거가 없습니다. 빠진 것을 '실패=차단'으로 세지 않습니다.
    missing = [a.id for a in runtime_attacks if a.id not in b_map or a.id not in a_map]
    if missing:
        return VerifyResult(status="error", sandbox=sandbox.name,
                            message=f"공격 결과가 비어 판정할 수 없습니다: {', '.join(missing)}",
                            before_tests=before_tests, after_tests=after_tests, duration_sec=elapsed(), **iso)

    outcomes: list[AttackOutcome] = []
    for a in runtime_attacks:
        b, af = b_map[a.id], a_map[a.id]
        b_ok, a_ok = bool(b.get("succeeded")), bool(af.get("succeeded"))
        verdict = "not_reproduced" if not b_ok else ("fix_failed" if a_ok else "verified")
        outcomes.append(AttackOutcome(
            id=a.id, before_succeeded=b_ok, after_succeeded=a_ok,
            before_status=b.get("status"), after_status=af.get("status"),
            before_evidence=b.get("evidence"), after_evidence=af.get("evidence"),
            verdict=verdict,
        ))

    verdicts = {o.verdict for o in outcomes}
    # 수정 전부터 실패하던 테스트는 수정본 탓이 아닙니다. '수정 후 새로 깨진' 경우만 실패로 봅니다.
    tests_broken = req.run_tests and after_tests.ok is False and before_tests.ok is not False
    tests_pre_broken = req.run_tests and before_tests.ok is False
    if "fix_failed" in verdicts or tests_broken:
        status, msg = "fix_failed", "수정 후에도 공격이 통하거나 기능 테스트가 새로 깨졌습니다."
    elif "not_reproduced" in verdicts:
        status, msg = "not_reproduced", "수정 전 공격이 재현되지 않았습니다(오탐 후보)."
    else:
        status, msg = "verified", "모든 공격이 수정 후 차단되고 기능 테스트를 통과했습니다."
        if tests_pre_broken:
            msg = "모든 공격이 수정 후 차단됐습니다. 기능 테스트는 수정 전부터 실패하고 있어 기능 보존은 확인하지 못했습니다."

    return VerifyResult(
        status=status, message=msg, sandbox=sandbox.name, attacks=outcomes,
        before_tests=before_tests, after_tests=after_tests, duration_sec=elapsed(), **iso,
    )


def _merge_isolation(before: dict | None, after: dict | None) -> Isolation:
    """수정 전·후 두 번의 실행에서 모두 True인 항목만 True. 어느 한쪽이라도 모르면(None) None."""
    keys = ("network_isolated", "non_root", "caps_dropped", "no_new_privs")
    out = {}
    for k in keys:
        vals = [(d or {}).get(k) for d in (before, after)]
        out[k] = False if False in vals else (True if all(x is True for x in vals) else None)
    return Isolation(**out)
