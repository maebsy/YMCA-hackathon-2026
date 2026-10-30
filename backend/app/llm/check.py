"""실제 vLLM으로 예시 탐지 결과를 돌려 형식·한국어·속도를 확인합니다. GPU 서버 검증과 C·D 평가 준비에 씁니다.

    cd backend
    python -m app.llm.check                       # Blue(C)와 Red–Blue(D) 둘 다
    python -m app.llm.check --mode blue --repeat 2

결과 전체는 outputs/llm-check-<시각>.json 에 저장합니다 (커밋되지 않는 폴더).
하나라도 실패하거나 한자가 섞이면 종료 코드 1을 돌려줍니다.
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

from app.config import ROOT_DIR
from app.llm import create_explainer
from app.llm.quality import foreign_script_count, hangul_ratio
from app.llm.schemas import FindingInput

DEFAULT_FINDINGS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "findings.json"


async def run(findings: list[FindingInput], modes: list[str], repeat: int) -> tuple[dict, bool]:
    explainer = create_explainer()
    report: dict = {"model": explainer.client.model, "runs": []}
    ok = True
    try:
        models = await explainer.client.health()
        print(f"서버 모델: {models}")
        for mode in modes:
            for i in range(repeat):
                started = time.perf_counter()
                results = await explainer.explain_many(findings, mode)
                wall_ms = int((time.perf_counter() - started) * 1000)
                ok &= summarize(mode, i, results, wall_ms)
                report["runs"].append(
                    {"mode": mode, "repeat": i, "wall_ms": wall_ms, "results": [r.model_dump() for r in results]}
                )
    finally:
        await explainer.client.aclose()
    return report, ok


def summarize(mode: str, repeat: int, results, wall_ms: int) -> bool:
    ok = True
    print(f"\n== {mode} #{repeat + 1}: {len(results)}건 동시, 전체 {wall_ms / 1000:.1f}초")
    latencies, tokens = [], 0
    for r in results:
        if r.status != "done":
            ok = False
            print(f"  ✗ {r.fingerprint}: {r.error_code} {r.error}")
            continue
        e = r.explanation
        text = "\n".join([e.summary, e.why_risky, *(s.detail for s in e.fix_steps), e.attack_scenario or ""])
        foreign = foreign_script_count(text)
        ok &= foreign == 0
        latencies.append(e.latency_ms)
        tokens += e.completion_tokens
        rounds = "→".join(x.verdict for x in e.red_rounds) or "-"
        mark = "✓" if foreign == 0 else "✗"
        print(
            f"  {mark} {r.fingerprint}: {e.latency_ms / 1000:.1f}초, {e.completion_tokens}토큰, 우선순위 {e.priority}, "
            f"Red {rounds}{' (수동 확인)' if e.needs_manual_review else ''}, 한글 {hangul_ratio(text):.0%}, 한자 {foreign}"
        )
        print(f"     {e.summary}")
    if latencies:
        print(
            f"  건당 지연 중앙값 {statistics.median(latencies) / 1000:.1f}초, 최대 {max(latencies) / 1000:.1f}초, "
            f"전체 처리량 {tokens / (wall_ms / 1000):.1f} 토큰/초"
        )
    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--findings", type=Path, default=DEFAULT_FINDINGS)
    parser.add_argument("--mode", choices=["blue", "red_blue", "both"], default="both")
    parser.add_argument("--repeat", type=int, default=1)
    args = parser.parse_args()

    findings = [FindingInput.model_validate(x) for x in json.loads(args.findings.read_text(encoding="utf-8"))]
    modes = ["blue", "red_blue"] if args.mode == "both" else [args.mode]
    report, ok = asyncio.run(run(findings, modes, args.repeat))

    out_dir = ROOT_DIR / "outputs"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / f"llm-check-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n결과 저장: {out}")
    print("통과" if ok else "실패한 항목이 있습니다")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
