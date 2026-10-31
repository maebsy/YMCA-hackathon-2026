"""Red–Blue 실검증 입력·출력 규격.

핵심 아이디어: AI가 "고쳤다"고 말하는 대신, 샌드박스에서 **수정 전 공격이 성공하고 수정 후 공격이 실패하며
기능 테스트는 통과**하는 것을 실제로 실행해 확인합니다(Before/After). 반복 질의가 아니라 실행 결과가 근거입니다.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# success_when 문법: 공격 응답이 '성공(취약)'인지 판정하는 규칙 (probe.mjs 와 동일)
#   json_array_len_gte:N  응답이 JSON 배열이고 길이 N 이상 (예: 전체 행 노출)
#   body_contains:STR     응답 본문에 STR 포함 (예: 이스케이프 안 된 <script>)
#   status_eq:N           HTTP 상태 코드가 N


class HttpRequest(BaseModel):
    method: Literal["GET", "POST", "PUT", "DELETE", "PATCH"] = "GET"
    path: str = Field(min_length=1, max_length=400)
    query: dict[str, str] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: str | None = None


class AttackSpec(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    cwe: str | None = None
    rule_id: str | None = None
    runtime: bool = True  # False면 정적 탐지만, 런타임 공격 없음
    request: HttpRequest | None = None
    baseline: HttpRequest | None = None  # 정상 요청 (기능이 살아 있는지 비교용)
    success_when: str | None = None
    note: str | None = None


class Patch(BaseModel):
    """Blue가 제안한 수정. files = {파일 경로: 수정된 전체 내용}. 샌드박스가 수정본 사본에 적용합니다."""

    files: dict[str, str] = Field(default_factory=dict)


class VerifyRequest(BaseModel):
    repo_dir: str = Field(description="검사 대상 소스 폴더(샌드박스가 사본을 만들어 격리 실행)")
    attacks: list[AttackSpec] = Field(min_length=1, max_length=50)
    patch: Patch = Field(default_factory=Patch)
    # 앱 실행·테스트 명령 (사용자 저장소면 package.json 에서 추정, 데모는 기본값)
    start_cmd: list[str] = Field(default_factory=lambda: ["npm", "start"])
    test_cmd: list[str] = Field(default_factory=lambda: ["npm", "test"])
    run_tests: bool = True


class AttackOutcome(BaseModel):
    id: str
    before_succeeded: bool  # 수정 전 공격이 성공했나 (취약 재현)
    after_succeeded: bool  # 수정 후에도 공격이 성공하나 (실패면 차단됨)
    before_status: int | None = None
    after_status: int | None = None
    before_evidence: str | None = None
    after_evidence: str | None = None
    # verified: 전→성공, 후→차단 / not_reproduced: 전→실패(오탐 후보) / fix_failed: 후→여전히 성공
    verdict: Literal["verified", "not_reproduced", "fix_failed"]


class TestOutcome(BaseModel):
    ok: bool | None = None
    passed: int | None = None
    failed: int | None = None


class Isolation(BaseModel):
    """probe가 샌드박스 안에서 직접 읽은 격리 상태 (외부 요청 없이 확인). 수정 전·후 실행 모두 만족해야 True."""

    network_isolated: bool | None = None  # 루프백 외 네트워크 장치 없음
    non_root: bool | None = None  # root 아님
    caps_dropped: bool | None = None  # 리눅스 특수 권한 0
    no_new_privs: bool | None = None  # 권한 상승 금지

    @property
    def confirmed(self) -> bool:
        return all(v is True for v in (self.network_isolated, self.non_root, self.caps_dropped, self.no_new_privs))


class VerifyResult(BaseModel):
    # verified: 모든 런타임 공격이 차단되고 기능 테스트 통과
    # not_reproduced: 수정 전 공격이 재현되지 않음 → 오탐 후보
    # fix_failed: 수정 후에도 공격이 통하거나 테스트가 깨짐
    # error: 샌드박스 실행 실패 (앱이 안 뜸 등)
    status: Literal["verified", "not_reproduced", "fix_failed", "error"]
    message: str = ""
    sandbox: Literal["docker", "local"] = "docker"
    isolation: Isolation = Field(default_factory=Isolation)
    isolation_confirmed: bool = False  # 네 항목이 수정 전·후 모두 True
    attacks: list[AttackOutcome] = Field(default_factory=list)
    before_tests: TestOutcome = Field(default_factory=TestOutcome)
    after_tests: TestOutcome = Field(default_factory=TestOutcome)
    duration_sec: float = 0.0
