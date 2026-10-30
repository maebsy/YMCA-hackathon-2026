"""사용자에게 보여 줄 문장의 기계 검사.

Qwen 계열은 한국어 답에 한자·중국어가 섞이는 일이 있어, 섞이면 다시 쓰게 합니다.
"""

import re

from app.llm.schemas import BlueDraft, FixStep, RedReview

_HAN = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_KANA = re.compile(r"[぀-ヿ]")
_HANGUL = re.compile(r"[가-힣]")
_CODE_FENCE = re.compile(r"```")


def foreign_script_count(text: str) -> int:
    """한자·가나 글자 수."""
    return len(_HAN.findall(text)) + len(_KANA.findall(text))


def hangul_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return len(_HANGUL.findall(text)) / len(letters)


def user_facing_text(item: BlueDraft | RedReview) -> str:
    if isinstance(item, BlueDraft):
        parts = [item.summary, item.why_risky, *(f"{s.title} {s.detail}" for s in item.fix_steps)]
        if item.false_positive_reason:
            parts.append(item.false_positive_reason)
    else:
        parts = [item.attack_scenario, *item.issues]
    return "\n".join(parts)


def _cut_off_fields(item: BlueDraft | RedReview) -> list[str]:
    """글자 수 한도까지 꽉 찬 항목. vLLM이 스키마 한도에서 문장 중간을 자른 것입니다."""
    if isinstance(item, BlueDraft):
        fields = [("summary", item.summary), ("why_risky", item.why_risky), ("ai_fix_prompt", item.ai_fix_prompt)]
        fields += [("fix_steps.detail", step.detail) for step in item.fix_steps]
        limits = {
            "summary": BlueDraft.model_fields["summary"],
            "why_risky": BlueDraft.model_fields["why_risky"],
            "ai_fix_prompt": BlueDraft.model_fields["ai_fix_prompt"],
            "fix_steps.detail": FixStep.model_fields["detail"],
        }
    else:
        fields = [("attack_scenario", item.attack_scenario)]
        limits = {"attack_scenario": RedReview.model_fields["attack_scenario"]}
    cut = []
    for name, value in fields:
        max_len = next((m.max_length for m in limits[name].metadata if hasattr(m, "max_length")), None)
        if max_len and len(value) >= max_len:
            cut.append(name)
    return cut


def problems(item: BlueDraft | RedReview) -> list[str]:
    """다시 쓰게 할 문제 목록. 비어 있으면 통과."""
    text = user_facing_text(item)
    found = []
    if cut := _cut_off_fields(item):
        found.append(f"{', '.join(sorted(set(cut)))} 항목이 너무 길어 중간에 잘렸습니다. 안내한 분량 안으로 줄여 쓰세요")
    if foreign_script_count(text):
        found.append("한자나 일본어가 섞여 있습니다. 한국어로만 다시 쓰세요")
    if isinstance(item, RedReview) and _CODE_FENCE.search(item.attack_scenario):
        found.append("attack_scenario에 코드를 넣지 마세요. 문장으로만 설명하세요")
    return found
