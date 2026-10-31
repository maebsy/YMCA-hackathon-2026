"""엔진 전체에서 같이 쓰는 상수와 옵션.

출력 JSON의 값(상태 이름, 위험도 등)은 전부 여기서 정한다.
백엔드·프론트·LLM 담당은 이 파일과 schema/scan_result.schema.json만 보면 된다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

SCHEMA_VERSION = "1.0"
ENGINE_NAME = "security_engine"
ENGINE_VERSION = "0.1.0"

# ---------------------------------------------------------------- 도구
# osv: 외부 부품 / semgrep: 코드 검사기(Opengrep 우선) / gitleaks: 비밀값 / config: 자체 설정 검사기(엔진 내장)
TOOLS = ("osv", "semgrep", "gitleaks", "config")
CATEGORY_BY_TOOL = {"osv": "dependency", "semgrep": "code", "gitleaks": "secret", "config": "config"}

# 도구 실행 결과 (coverage.<tool>.status)
TOOL_OK = "ok"                        # 정상 실행
TOOL_NOT_INSTALLED = "not_installed"  # 컴퓨터에 도구가 없음
TOOL_NO_TARGET = "no_target"          # 검사할 대상이 없음 (예: lockfile 없음)
TOOL_ERROR = "error"                  # 실행 실패 (네트워크, 시간 초과 등)
TOOL_SKIPPED = "skipped"              # 옵션으로 끔

# ---------------------------------------------------------------- 위험도
SEVERITIES = ("critical", "high", "medium", "low", "unknown")
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}  # 숫자가 작을수록 위험

# ---------------------------------------------------------------- 결과 상태 4가지 (finding.status)
CODE_ISSUE = "code_issue"
CODE_RESOLVED = "code_resolved"
RUNTIME_CHECK = "runtime_check_needed"
OUT_OF_SCOPE = "out_of_scope"
STATUSES = (CODE_ISSUE, CODE_RESOLVED, RUNTIME_CHECK, OUT_OF_SCOPE)
STATUS_LABEL_KO = {
    CODE_ISSUE: "코드에서 문제 확인",
    CODE_RESOLVED: "코드에서 해결 확인",
    RUNTIME_CHECK: "운영 환경 확인 필요",
    OUT_OF_SCOPE: "현재 검사 범위 밖",
}

# ---------------------------------------------------------------- 이전 검사와 비교 (finding.change)
NEW = "new"                    # 이번에 처음 나옴
PERSISTING = "persisting"      # 지난번에도 있었고 아직 있음
RESOLVED = "resolved"          # 지난번엔 있었는데 이번엔 없음 (도구는 정상 실행됨)
UNVERIFIABLE = "unverifiable"  # 지난번엔 있었는데 이번엔 도구가 못 돌아서 확인 불가
CHANGES = (NEW, PERSISTING, RESOLVED, UNVERIFIABLE)

# ---------------------------------------------------------------- 꼼수·주의 표시 (finding.flags)
FLAG_SUPPRESSED_COMMENT = "suppressed_by_comment"  # nosemgrep, gitleaks:allow 주석으로 숨기려 함
FLAG_IGNORED_BY_CONFIG = "ignored_by_config"       # osv-scanner.toml 등 설정 파일로 무시하려 함
FLAG_FILE_REMOVED = "file_removed"                 # 해결됐지만 파일 자체가 사라짐 (기능 삭제 의심)
FLAG_LOCKFILE_REMOVED = "lockfile_removed"         # lockfile을 지워서 검사를 피함
FLAG_ROTATE_SECRET = "rotate_secret"               # 코드에서 지워도 키 폐기·재발급 필요
FLAG_LIKELY_PUBLIC_KEY = "likely_public_key"       # 원래 공개해도 되는 키로 보임 (검색 전용 키, reCAPTCHA siteKey 등)
FLAG_THIRD_PARTY = "third_party_code"              # 외부 라이브러리 파일 (직접 고치기보다 업데이트)

# 공개용 키를 뜻하는 이름 (gitleaks가 찾은 줄에 이 말이 있으면 위험도를 낮춘다. 숨기지는 않음)
PUBLIC_KEY_HINT = (
    r"(?i)(search[_-]?only|site[_-]?key|publishable|public[_-]?(api[_-]?)?key|anon[_-]?key"
    r"|NEXT_PUBLIC_|VITE_|REACT_APP_|\bpk_(live|test)_|measurement[_-]?id|application[_-]?id)"
)
# 외부 라이브러리로 보이는 경로 (폴더 이름 또는 파일 이름)
THIRD_PARTY_HINT = (
    r"(?i)(^|/)(plugins?|vendors?|libs?|third[_-]?party|bower_components|assets/js/vendor)/"
    r"|(^|/)(jquery|bootstrap|lodash|moment|popper|swiper|lightbox|magnific)[\w.\-]*\.js$"
)

# Semgrep 기본 제외 폴더 (빌드 결과물, 외부 부품)
SEMGREP_EXCLUDES = (
    "node_modules", ".git", "dist", "build", ".next", ".nuxt", "out", "_site",
    "vendor", "coverage", ".venv", "venv", "__pycache__", "*.min.js", "*.map",
)

BUILTIN_RULES_DIR = Path(__file__).resolve().parent / "rules"


@dataclass
class ScanOptions:
    """scan()의 세부 설정. 기본값 그대로 써도 된다."""

    tools: tuple[str, ...] = TOOLS
    # 코드 검사(Opengrep/Semgrep)는 우리 규칙(rules/)만 기본으로 쓴다 → 유료 서비스 가능 구성 (2026-10-31 팀 차트 기준).
    # Semgrep 레지스트리 룰셋(예: ("p/default",))은 'Semgrep Rules License'(SaaS 제공 불가)라 내부 비교·검증 때만 켠다.
    # 접속 실패 시 자동으로 우리 규칙만으로 다시 돌리고 coverage.semgrep.message에 남긴다.
    semgrep_registry: tuple[str, ...] = ()
    semgrep_extra_configs: tuple[str, ...] = ()  # 추가 규칙 파일·폴더 경로
    osv_offline: bool = False  # True면 미리 받아둔 OSV DB만 사용 (--offline-vulnerabilities)
    osv_recheck: bool = True   # 추천 업그레이드 버전을 OSV에 다시 조회해 남은 취약점 확인 (#109, 오프라인이면 생략)
    timeout_sec: int = 600     # 도구 하나당 최대 실행 시간
    context_lines: int = 3     # 증거 코드 앞뒤로 몇 줄 보여줄지
    include_raw: bool = False  # True면 각 finding에 스캐너 원본(raw)을 붙임 (비밀값은 가림)
    extra_env: dict[str, str] = field(default_factory=dict)  # 도구 실행 시 추가 환경 변수
