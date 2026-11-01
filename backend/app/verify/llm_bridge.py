"""Red·Blue 출력 → 실검증 입력 연결 (#97).

- Red  : 탐지 결과와 대상 파일을 보고 로컬 앱에 그대로 재생할 HTTP 요청과 성공 판정 규칙을 냅니다 → `AttackSpec`
- Blue : 같은 파일에 걸린 탐지 결과들을 고칠 '이 부분을 → 이렇게' 편집 목록을 냅니다. 서버가 원본에 적용해
         **파일 전체 내용**을 만듭니다 → `Patch.files`. (파일 전체를 모델이 다시 쓰면 L4에서 길이 한도에 잘리고 느립니다)
- `verify_findings`: 위 두 출력을 만들어 `verify()`로 샌드박스에서 수정 전·후를 실제로 실행합니다.

모델 출력은 그대로 믿지 않습니다. 공격 경로는 앱 안 경로(`/...`)만, 수정은 입력으로 준 파일에만 허용하고
형식이 어긋난 항목은 이유와 함께 건너뜁니다(`skipped`). 소스는 우리 GPU 서버의 로컬 모델에만 보냅니다.
"""
from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import parse_qsl

from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from app.llm import prompts
from app.llm.client import LLMClient, Sampling
from app.llm.schemas import FindingInput

from .schemas import AttackSpec, HttpRequest, Patch, VerifyRequest, VerifyResult
from .verifier import verify

# 문맥 12K 토큰 안에서 파일 전체를 모델에 보여 줘야 하므로 원본 크기를 제한합니다
MAX_SOURCE_CHARS = 9000
RED_ATTACK_SAMPLING = Sampling(temperature=0.2, max_tokens=1200)
BLUE_PATCH_SAMPLING = Sampling(temperature=0.2, max_tokens=2000)

_PATH = re.compile(r"^/(?!/)[^\s\\]{0,399}$")


# ── 모델이 만드는 JSON (strict 스키마라 dict 대신 이름·값 목록을 씁니다) ──


class Param(BaseModel):
    name: str = Field(max_length=100)
    value: str = Field(max_length=400)


class RedAttackDraft(BaseModel):
    reproducible: bool = Field(description="HTTP 요청 한 번으로 재현할 수 없으면 false")
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"]
    path: str = Field(max_length=400, description="앱 안 경로. /로 시작, 호스트·스킴 없이")
    query: list[Param] = Field(max_length=8)
    body: str = Field(max_length=2000, description="본문이 없으면 빈 문자열")
    content_type: Literal["none", "application/json", "application/x-www-form-urlencoded"]
    success_rule: Literal["json_array_len_gte", "body_contains", "status_eq"]
    success_value: str = Field(max_length=200)
    reason: str = Field(max_length=400, description="이 요청이 취약점을 증명하는 이유 (한국어 한두 문장)")


class RedAttackPlan(BaseModel):
    attack: RedAttackDraft


class Edit(BaseModel):
    start_line: int = Field(description="바꿀 첫 줄 번호 (입력 파일에 붙은 번호)")
    end_line: int = Field(description="바꿀 마지막 줄 번호 (한 줄이면 start_line과 같음)")
    replace: str = Field(max_length=2500, description="그 줄들을 대신할 새 코드 (줄 번호 없이)")


class BluePatch(BaseModel):
    file_path: str = Field(max_length=500)
    edits: list[Edit] = Field(min_length=1, max_length=10)
    summary: str = Field(max_length=400)


# ── 결과 ──


class Skipped(BaseModel):
    fingerprint: str
    stage: Literal["red", "blue", "input"]
    reason: str


class VerificationPlan(BaseModel):
    attacks: list[AttackSpec] = Field(default_factory=list)
    patch: Patch = Field(default_factory=Patch)
    # 공격 id → 탐지 결과 fingerprint (화면에서 공격 결과를 탐지 결과에 다시 붙일 때)
    attack_fingerprints: dict[str, str] = Field(default_factory=dict)
    red_reasons: dict[str, str] = Field(default_factory=dict)
    patch_summaries: dict[str, str] = Field(default_factory=dict)
    skipped: list[Skipped] = Field(default_factory=list)


class BridgeResult(BaseModel):
    plan: VerificationPlan
    result: VerifyResult | None = None


# ── 프롬프트 ──

RED_ATTACK_SYSTEM = """\
너는 72hours의 Red다. 탐지 결과가 실제로 악용되는지 **로컬 샌드박스에서 실행해 확인할** HTTP 요청 하나를 만든다.
- 앱은 127.0.0.1에서 돈다. path는 앱 안 경로만 쓴다(/로 시작, http:// 같은 호스트·스킴 금지).
- 파일의 실제 라우트와 파라미터 이름을 그대로 쓴다. 없는 경로를 지어내지 않는다.
- 성공 판정(success_rule)은 '취약한 코드에서는 참, 고친 코드에서는 거짓'이 되도록 고른다.
  - json_array_len_gte:N  응답이 JSON 배열이고 길이 N 이상 (예: 조건 우회로 여러 행 노출)
  - body_contains:문자열   응답 본문에 그 문자열이 그대로 있음 (예: 이스케이프 안 된 <script> 반사)
  - status_eq:N           HTTP 상태 코드가 N
- 정상 사용으로도 참이 되는 판정(예: 결과 1건이면 성공)은 쓰지 않는다.
- 파괴적 요청(삭제·대량 생성)과 외부로 나가는 요청은 만들지 않는다.
- 하드코딩 키·오래된 의존성처럼 HTTP 한 번으로 재현할 수 없으면 reproducible=false 로 둔다.
- reason은 한국어 한두 문장. JSON만 출력한다."""

BLUE_PATCH_SYSTEM = """\
너는 72hours의 Blue다. 탐지된 취약점을 고칠 편집 목록(edits)을 출력한다.
- file_path는 입력에 준 경로를 그대로 쓴다.
- 입력 파일의 각 줄 앞에는 `번호| `가 붙어 있다. 각 편집은 바꿀 줄 범위(start_line~end_line)와
  그 줄들을 대신할 새 코드(replace)다. replace에는 줄 번호를 넣지 않는다. 파일 전체를 다시 쓰지 않는다.
- 편집끼리 줄 범위가 겹치지 않게 한다.
- replace는 범위 안의 **모든 줄**을 대신한다. 범위에 넣은 줄은 바꾸지 않더라도 replace에 다시 써야 한다
  (예: 입력값 줄과 응답을 보내는 줄을 함께 범위에 넣었다면 두 줄 모두 replace에 있어야 한다).
- 취약점과 관련된 줄만 최소한으로 고친다. 라우트·응답 형식·정상 동작·내보내기(export)는 바꾸지 않는다.
- 사용자 입력을 지우거나 고정 문자열로 바꾸는 것은 수정이 아니다. 화면에 보이던 값은 이스케이프해서 계속 보이게 하고,
  쿼리에 쓰이던 값은 매개변수로 넘겨 계속 쓰이게 한다.
- 새 패키지를 추가하지 않는다. 언어 기본 기능과 이미 쓰는 라이브러리로 고친다.
  (예: SQL은 자리표시자(?)와 매개변수, HTML 출력은 이스케이프, 비밀값은 환경변수)
- 따옴표 종류나 공백만 바꾸는 것은 수정이 아니다. 예시(Node.js/Express, 한 줄씩 바꾸면 된다):
  · SQL: db.query("... WHERE id = " + id)  →  db.query("... WHERE id = ?", id)
  · HTML 출력: const q = req.query.q || "";  →
    const q = String(req.query.q || "").replace(/[&<>"']/g, (c) => "&#" + c.charCodeAt(0) + ";");
    (특수문자를 숫자 엔티티로 바꾼다. 따옴표 종류를 바꿔도 문법이 깨지지 않는 형태이니 이 형태를 그대로 쓴다)
- 한 줄만 고치면 되면 start_line과 end_line을 같은 줄로 둔다. 응답을 보내는 줄(res.send, res.json)은 범위에 넣지 않는다.
- 코드 블록 표시(```)를 넣지 않는다. summary는 무엇을 고쳤는지 한국어 한두 문장. JSON만 출력한다."""


def _source_block(path: str, source: str) -> str:
    return f'<file path="{path}">\n{source}\n</file>'


def red_attack_messages(finding: FindingInput, path: str, source: str) -> list[dict]:
    content = f"<finding>\n{prompts.render_finding(finding)}\n</finding>\n\n{_source_block(path, source)}"
    return [{"role": "system", "content": RED_ATTACK_SYSTEM}, {"role": "user", "content": content}]


def _numbered(source: str) -> str:
    return "\n".join(f"{n:>4}| {line}" for n, line in enumerate(source.splitlines(), 1))


def blue_patch_messages(findings: list[FindingInput], path: str, source: str) -> list[dict]:
    blocks = "\n".join(f"<finding>\n{prompts.render_finding(f)}\n</finding>" for f in findings)
    content = (f"{blocks}\n\n{_source_block(path, _numbered(source))}\n\n"
               f"위 탐지 결과를 모두 고치는 {path} 편집 목록을 출력하세요.")
    return [{"role": "system", "content": BLUE_PATCH_SYSTEM}, {"role": "user", "content": content}]


# ── 모델 출력 검사·변환 ──


def _success_when(rule: str, value: str) -> str | None:
    value = value.strip()
    if rule == "json_array_len_gte":
        return f"{rule}:{int(value)}" if value.isdigit() and int(value) >= 1 else None
    if rule == "status_eq":
        return f"{rule}:{int(value)}" if value.isdigit() and 100 <= int(value) <= 599 else None
    return f"{rule}:{value}" if value else None


def to_attack_spec(draft: RedAttackDraft, attack_id: str, finding: FindingInput) -> AttackSpec | str:
    """모델의 공격 초안을 실검증 형식으로 바꿉니다. 받을 수 없으면 이유(str)를 돌려줍니다."""
    if not draft.reproducible:
        return "Red가 HTTP 요청으로 재현할 수 없다고 판단했습니다."
    path = draft.path.strip()
    if "://" in path or not _PATH.match(path):
        return f"공격 경로가 앱 안 경로(/...)가 아닙니다: {path[:80]!r}"
    success = _success_when(draft.success_rule, draft.success_value)
    if not success:
        return f"성공 판정 값이 올바르지 않습니다: {draft.success_rule}:{draft.success_value[:40]!r}"
    if any(not p.name.strip() for p in draft.query):
        return "쿼리 파라미터 이름이 비어 있습니다."
    # 모델이 쿼리를 path 에도 붙여 쓰는 경우가 있습니다. 그대로 두면 파라미터가 두 번 가서 값이 배열이 됩니다
    path, _, inline = path.partition("?")
    query = {k: v for k, v in parse_qsl(inline, keep_blank_values=True)}
    query.update({p.name: p.value for p in draft.query})
    body = draft.body or None
    # 본문이 없는 요청에 Content-Type 을 붙이지 않습니다
    headers = {"Content-Type": draft.content_type} if body and draft.content_type != "none" else {}
    return AttackSpec(
        id=attack_id,
        cwe=finding.refs.cwe[0] if finding.refs.cwe else None,
        rule_id=finding.rule_id,
        runtime=True,
        request=HttpRequest(method=draft.method, path=path, query=query, headers=headers, body=body),
        success_when=success,
        note=draft.reason,
    )


_HEAD = re.compile(r"\s*((?:const|let|var|return)?\s*[\w.$]+)\s*(?:=|\()")


def _similar(a: str, b: str) -> bool:
    """같은 줄을 고친 것으로 보이는지: 글자가 많이 겹치거나, 같은 변수에 대입·같은 함수 호출로 시작하면 같은 줄로 봅니다
    (예: `const q = req.query.q || ""` → `const q = String(...).replace(...)`)."""
    if difflib.SequenceMatcher(None, a.strip(), b.strip()).ratio() >= 0.6:
        return True
    ha, hb = _HEAD.match(a), _HEAD.match(b)
    return bool(ha and hb and ha.group(1).split() == hb.group(1).split())


def normalize_edits(patch: BluePatch, original: str) -> list[Edit]:
    """모델이 자주 내는 형식 실수를 서버가 바로잡습니다.

    - 범위를 크게 잡고 앞쪽 줄만 다시 쓴 경우(예: 51~52줄 범위에 51줄 고친 것만 씀): 빠진 뒤쪽 원래 줄을 그대로 붙입니다.
      운영에서 응답 줄(res.send)이 사라져 앱이 멈추는 수정본이 거의 매번 나왔습니다. 돌려준 줄이 범위 앞쪽 줄과
      비슷할 때만(고친 것으로 보일 때만) 붙이고, 줄을 정말 지우려는 듯한 편집은 그대로 둡니다.
    - 따옴표·공백만 바꾼 편집은 수정이 아니므로 적용하지 않습니다.
    """
    lines = original.splitlines()
    fixed: list[Edit] = []
    for edit in patch.edits:
        if not 1 <= edit.start_line <= edit.end_line <= len(lines):
            fixed.append(edit)  # 범위 오류는 to_patch_content 가 이유와 함께 거절합니다
            continue
        span = lines[edit.start_line - 1:edit.end_line]
        new = edit.replace.splitlines()
        if 0 < len(new) < len(span) and all(_similar(n, o) for n, o in zip(new, span)):
            edit = Edit(start_line=edit.start_line, end_line=edit.end_line,
                        replace="\n".join([*new, *span[len(new):]]))
        if _same_code("\n".join(span), edit.replace):
            continue
        fixed.append(edit)
    return fixed


def to_patch_content(patch: BluePatch, path: str, original: str) -> tuple[str | None, str]:
    """줄 범위 편집을 원본에 적용해 (수정된 전체 내용, '') 또는 받을 수 없으면 (None, 이유)를 돌려줍니다.

    범위가 파일 밖이거나 서로 겹치면 어디를 고칠지 모호하므로 전체를 거절합니다(일부만 적용하지 않음).
    """
    if PurePosixPath(patch.file_path.strip().lstrip("./")) != PurePosixPath(path):
        return None, f"입력에 없는 파일을 고치려 했습니다: {patch.file_path[:80]!r}"
    lines = original.splitlines(keepends=True)
    edits = sorted(normalize_edits(patch, original), key=lambda e: e.start_line)
    if not edits:
        return None, "모든 편집이 따옴표·공백만 바꿔 실제로 고친 곳이 없습니다. 취약한 줄을 실제로 고치세요."
    for i, edit in enumerate(edits, 1):
        if not 1 <= edit.start_line <= edit.end_line <= len(lines):
            return None, f"{i}번째 편집의 줄 범위 {edit.start_line}~{edit.end_line}가 파일(1~{len(lines)}줄) 밖입니다."
        if i > 1 and edit.start_line <= edits[i - 2].end_line:
            return None, f"편집 줄 범위가 겹칩니다: {edits[i - 2].start_line}~{edits[i - 2].end_line}, {edit.start_line}~{edit.end_line}."
    for edit in reversed(edits):  # 뒤에서부터 바꿔야 앞 줄 번호가 밀리지 않습니다
        start, end = edit.start_line - 1, edit.end_line
        lines[start:end] = _replacement(edit.replace, lines[start], lines[end - 1])
    content = "".join(lines)
    if content == original:
        return None, "편집을 적용해도 원본과 같습니다. 취약한 줄을 실제로 고치세요."
    return content, ""


_LINE_NO = re.compile(r"^\s*\d+\| ?")


def _replacement(text: str, first: str, last: str) -> list[str]:
    """replace 를 줄 목록으로. 모델이 줄 번호를 따라 붙였으면 떼고, 들여쓰기를 빼먹었으면 원래 들여쓰기를 붙입니다."""
    body = text.splitlines()
    if body and all(_LINE_NO.match(line) for line in body if line.strip()):
        body = [_LINE_NO.sub("", line, count=1) for line in body]
    indent = re.match(r"[ \t]*", first).group(0)
    if indent and not any(line[:1] in (" ", "\t") for line in body if line.strip()):
        body = [indent + line if line.strip() else line for line in body]
    newline = "\n" if last.endswith("\n") else ""
    return [line + "\n" for line in body[:-1]] + ([body[-1] + newline] if body else [])


_JS_SUFFIXES = (".js", ".cjs", ".mjs")


def syntax_error(path: str, content: str) -> str | None:
    """수정본 JS 파일의 문법 오류. `node --check`는 파싱만 하고 코드를 실행하지 않습니다.
    JS가 아니거나 이 서버에 node가 없으면 None (샌드박스 실행에서 '수정 후 앱이 안 뜸'으로 걸러집니다)."""
    suffix = PurePosixPath(path).suffix
    node = shutil.which("node")
    if suffix not in _JS_SUFFIXES or not node:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        target = Path(tmp) / f"patched{suffix}"
        target.write_text(content, encoding="utf-8")
        try:
            r = subprocess.run([node, "--check", str(target)], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=15)
        except subprocess.TimeoutExpired:
            return None
    if r.returncode == 0:
        return None
    # 임시 경로 대신 원래 파일 이름으로, 모델이 고칠 수 있게 첫 몇 줄만 돌려줍니다
    detail = "\n".join(r.stderr.replace(str(target), path).strip().splitlines()[:6])
    return f"수정본에 문법 오류가 있습니다(코드가 중간에 잘렸거나 괄호가 맞지 않음): {detail[:500]}"


def blue_check(path: str, original: str):
    """chat_json 의 check: 편집을 적용할 수 없거나 수정본이 문법에 맞지 않으면 그 이유를 모델에게 돌려줘 한 번 더 받게 합니다."""
    def check(patch: BluePatch) -> list[str]:
        content, why = to_patch_content(patch, path, original)
        if content is None:
            return [why]
        broken = syntax_error(path, content)
        if broken:
            return [broken]
        # 서버가 바로잡은 뒤에도 남는 문제만 되묻습니다 (따옴표만 바꾼 편집은 알려 줘서 실제로 고치게 함)
        repaired = BluePatch(file_path=patch.file_path, edits=normalize_edits(patch, original) or patch.edits, summary=patch.summary)
        return _dropped_lines(repaired, original) + _cosmetic_edits(patch, original)
    return check


def _same_code(a: str, b: str) -> bool:
    """공백·따옴표 종류만 다르면 같은 코드로 봅니다 ('a' 와 "a")."""
    norm = lambda text: re.sub(r"\s+", "", text).replace("'", '"').replace("`", '"')  # noqa: E731
    return norm(a) == norm(b)


def _cosmetic_edits(patch: BluePatch, original: str) -> list[str]:
    """따옴표·공백만 바꾼 편집을 알려 줍니다. 서버 실행에서 Blue가 XSS를 고쳤다면서 `""` 를 `''` 로만 바꾼 일이 있었습니다."""
    lines = original.splitlines()
    problems = []
    for edit in patch.edits:
        before = "\n".join(lines[edit.start_line - 1:edit.end_line])
        replaced = "\n".join(lines[edit.start_line - 1:edit.start_line - 1 + max(1, len(edit.replace.splitlines()))])
        if _same_code(before, edit.replace) or (edit.replace.strip() and _same_code(replaced, edit.replace)):
            problems.append(f"{edit.start_line}~{edit.end_line}줄 편집은 따옴표·공백만 바뀌어 취약점이 그대로입니다. "
                            "SQL은 자리표시자와 매개변수로, HTML 출력은 특수문자(& < > \" ')를 이스케이프해서 실제로 막으세요.")
    return problems


def _dropped_lines(patch: BluePatch, original: str) -> list[str]:
    """범위보다 적은 줄로 바꾼 편집을 알려 줍니다. 서버 실행에서 Blue가 입력값 줄과 응답 줄(res.send)을 함께 범위에
    넣고 입력값 줄만 돌려줘, 문법은 맞지만 응답이 사라진 수정본이 반복해서 나왔습니다(#111). 줄을 지우는 수정도 있을 수
    있으므로 한 번만 되묻고, 다시 받은 답은 그대로 씁니다(chat_json 은 두 번째 답의 check 문제를 기록만 함)."""
    lines = original.splitlines()
    problems = []
    for edit in patch.edits:
        kept = [x for x in lines[edit.start_line - 1:edit.end_line] if x.strip()]
        new = [x for x in edit.replace.splitlines() if x.strip()]
        if len(new) < len(kept):
            gone = [x.strip() for x in kept if x.strip() not in edit.replace][:3]
            problems.append(f"{edit.start_line}~{edit.end_line}줄({len(kept)}줄)을 {len(new)}줄로 바꿔 코드가 사라집니다: "
                            f"{gone}. 범위 안의 줄은 바꾸지 않더라도 replace에 모두 다시 쓰세요. 정말 지워야 하는 줄이면 그대로 두세요.")
    return problems


# ── 연결 ──


def _rel_path(finding: FindingInput) -> str | None:
    if not finding.file_path:
        return None
    rel = PurePosixPath(finding.file_path.replace("\\", "/").lstrip("./"))
    if rel.is_absolute() or ".." in rel.parts:
        return None
    return str(rel)


def _attack_id(index: int, finding: FindingInput) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", finding.rule_id.lower()).strip("-")[-40:] or "finding"
    return f"atk{index}-{slug}"


async def plan_verification(client: LLMClient, findings: list[FindingInput], repo_dir: str | Path) -> VerificationPlan:
    """탐지 결과들로 Red 공격과 Blue 수정본을 만듭니다. 같은 파일의 결과는 Blue가 한 번에 고칩니다."""
    repo = Path(repo_dir).resolve()
    plan = VerificationPlan()
    by_file: dict[str, list[FindingInput]] = {}
    sources: dict[str, str] = {}

    for f in findings:
        rel = _rel_path(f)
        target = (repo / rel).resolve() if rel else None
        if not rel or target is None or repo not in target.parents or not target.is_file():
            plan.skipped.append(Skipped(fingerprint=f.fingerprint, stage="input", reason="대상 파일을 찾을 수 없습니다."))
            continue
        if rel not in sources:
            text = target.read_text(encoding="utf-8", errors="replace")
            if len(text) > MAX_SOURCE_CHARS:
                plan.skipped.append(Skipped(fingerprint=f.fingerprint, stage="input",
                                            reason=f"파일이 {MAX_SOURCE_CHARS}자를 넘어 전체 수정본을 만들 수 없습니다."))
                continue
            sources[rel] = text
        by_file.setdefault(rel, []).append(f)

    index = 0
    for rel, group in by_file.items():
        source = sources[rel]
        for f in group:
            index += 1
            red = await client.chat_json(red_attack_messages(f, rel, source), RedAttackPlan, sampling=RED_ATTACK_SAMPLING)
            spec = to_attack_spec(red.data.attack, _attack_id(index, f), f)
            if isinstance(spec, str):
                plan.skipped.append(Skipped(fingerprint=f.fingerprint, stage="red", reason=spec))
                continue
            plan.attacks.append(spec)
            plan.attack_fingerprints[spec.id] = f.fingerprint
            plan.red_reasons[spec.id] = red.data.attack.reason
        blue = await client.chat_json(blue_patch_messages(group, rel, source), BluePatch, sampling=BLUE_PATCH_SAMPLING,
                                      check=blue_check(rel, source))
        content, why = to_patch_content(blue.data, rel, source)
        if content is not None:
            # 다시 받은 답도 문법이 깨져 있으면 실행하지 않고 건너뜁니다 (앱이 안 떠 '수정 실패'만 나오므로)
            broken = syntax_error(rel, content)
            if broken:
                content, why = None, broken
        if content is None:
            for f in group:
                plan.skipped.append(Skipped(fingerprint=f.fingerprint, stage="blue", reason=why))
            continue
        plan.patch.files[rel] = content
        plan.patch_summaries[rel] = blue.data.summary
    return plan


def run_feedback(result: VerifyResult) -> str | None:
    """샌드박스 실행 결과를 Blue에게 돌려줄 문장으로. 고칠 거리가 없으면(verified·error 등) None."""
    if result.status != "fix_failed":
        return None
    notes = []
    if result.message.startswith("수정 후 앱이"):
        notes.append("수정본을 적용한 앱이 시작되지 않거나 요청에 응답하지 않았습니다(시간 초과). 응답을 보내는 코드"
                     "(res.send, res.json, return 등)를 지우거나 빠뜨리지 않았는지 확인하세요. 편집 범위 안의 줄은 바꾸지 않더라도 모두 다시 쓰세요.")
    for attack in result.attacks:
        if attack.after_succeeded:
            evidence = (attack.after_evidence or "")[:200]
            notes.append(f"수정 후에도 '{attack.id}' 공격이 통했습니다(응답 일부: {evidence!r}). 이 취약점을 실제로 막으세요.")
    if result.after_tests.ok is False and result.before_tests.ok is not False:
        notes.append(f"수정 후 기능 테스트가 깨졌습니다(통과 {result.after_tests.passed}, 실패 {result.after_tests.failed}). "
                     "정상 동작·응답 형식은 바꾸지 마세요.")
    return " ".join(notes) or result.message


async def revise_patch(client: LLMClient, findings: list[FindingInput], repo_dir: str | Path, rel: str,
                       previous: str, feedback: str) -> tuple[str | None, str]:
    """실행 결과(feedback)를 붙여 Blue에게 원본 기준 편집을 다시 받습니다. (수정본, 요약 또는 거절 이유)"""
    source = (Path(repo_dir) / rel).read_text(encoding="utf-8", errors="replace")
    messages = blue_patch_messages(findings, rel, source)
    diff = "".join(difflib.unified_diff(source.splitlines(keepends=True), previous.splitlines(keepends=True), "a/" + rel, "b/" + rel, n=1))
    messages[-1]["content"] += (f"\n\n<previous_attempt>\n{diff[:2500]}\n</previous_attempt>\n"
                                f"<sandbox_result>\n{feedback[:1200]}\n</sandbox_result>\n"
                                "위 이전 수정을 격리 환경에서 실제로 실행한 결과입니다. 원본 파일 기준으로 편집 목록을 처음부터 다시 출력하세요.")
    blue = await client.chat_json(messages, BluePatch, sampling=BLUE_PATCH_SAMPLING, check=blue_check(rel, source))
    content, why = to_patch_content(blue.data, rel, source)
    if content is not None and (broken := syntax_error(rel, content)):
        content, why = None, broken
    return (content, blue.data.summary) if content is not None else (None, why)


async def verify_findings(client: LLMClient, findings: list[FindingInput], repo_dir: str | Path, *,
                          trusted: bool = False) -> BridgeResult:
    """Red 공격·Blue 수정본을 만들고 샌드박스에서 수정 전·후를 실행합니다. 사용자 저장소는 trusted=False(Docker 필수)."""
    plan = await plan_verification(client, findings, repo_dir)
    if not plan.attacks or not plan.patch.files:
        return BridgeResult(plan=plan)
    req = VerifyRequest(repo_dir=str(repo_dir), attacks=plan.attacks, patch=plan.patch)
    result = await run_in_threadpool(verify, req, trusted=trusted)
    return BridgeResult(plan=plan, result=result)


def plan_json(plan: VerificationPlan) -> str:
    """attacks.json 과 같은 모양으로 내보냅니다 (사람이 확인·재사용할 때)."""
    return json.dumps({"attacks": [a.model_dump(exclude_none=True) for a in plan.attacks]}, ensure_ascii=False, indent=2)
