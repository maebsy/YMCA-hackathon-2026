"""문맥 분석 1단계: 코드 위치·내용에서 규칙으로 뽑는 신호.

LLM 판단(ContextAnalysis)의 힌트로 넘기고, LLM 을 쓰지 않거나 실패했을 때는 이 신호만으로 판단합니다.
신호는 겉모양(경로·키워드) 기준이라 확신도는 낮게 둡니다.
"""

import re
from dataclasses import asdict, dataclass

from app.llm.schemas import ContextAnalysis, FindingInput

_TEST = re.compile(r"(^|/)(tests?|__tests__|spec|e2e|cypress|playwright)(/|$)|\.(test|spec)\.[a-z]+$", re.IGNORECASE)
_EXAMPLE = re.compile(r"(^|/)(examples?|samples?|demo|docs?|fixtures?|mocks?|storybook|stories)(/|$)", re.IGNORECASE)
_PUBLIC_DIR = re.compile(r"(^|/)(public|static|dist|build|out|\.next/static)(/|$)", re.IGNORECASE)
_SERVER_ROUTE = re.compile(
    r"(^|/)(app/.+/route\.[jt]s|pages/api/|api/|server/|routes?/|controllers?/|functions/|supabase/functions/)"
    r"|(^|/)(server|app|main|index)\.(js|ts|py|php)$|\.php$",
    re.IGNORECASE,
)
_CLIENT_PATH = re.compile(r"(^|/)(components?|hooks|pages|app|src/lib|lib|client)(/|$).*\.(jsx|tsx|vue|svelte)$|\.(jsx|tsx|vue|svelte)$", re.IGNORECASE)
_MIGRATION = re.compile(r"(^|/)(migrations?|supabase/migrations|prisma|schema)(/|$)|\.sql$", re.IGNORECASE)
_CONFIG = re.compile(r"(^|/)(\.env[^/]*|.*\.config\.[cm]?[jt]s|docker-compose\.ya?ml|compose\.ya?ml|vercel\.json|netlify\.toml|firebase\.json)$", re.IGNORECASE)
_LOCKFILE = re.compile(r"(package-lock\.json|pnpm-lock\.yaml|yarn\.lock|bun\.lockb?|requirements[^/]*\.txt|poetry\.lock|uv\.lock|Pipfile\.lock|composer\.lock|Gemfile\.lock|go\.sum|Cargo\.lock)$")
# 'use client' 파일이나 그 파일이 import 하는 모듈은 브라우저 번들에 들어갑니다 (주변 코드 설명에 있어도 신호로 봄)
_USE_CLIENT = re.compile(r"""['"]use client['"]""")
# 빌드 때 브라우저 코드에 그대로 박히는 환경 변수 접두어
_PUBLIC_ENV = re.compile(r"\b(NEXT_PUBLIC_|VITE_|REACT_APP_|PUBLIC_|EXPO_PUBLIC_)[A-Z0-9_]+")
_USE_SERVER = re.compile(r"""^\s*['"]use server['"]""", re.MULTILINE)
_REQUEST_INPUT = re.compile(r"req\.(query|body|params)|searchParams|request\.(args|form|json|get_json)|\$_(GET|POST|REQUEST)|params\[", re.IGNORECASE)
_AUTH_CHECK = re.compile(r"getServerSession|auth\(\)|getUser\(|requireAuth|isAuthenticated|@login_required|verify(Token|Jwt)|session\.user|middleware", re.IGNORECASE)
_PERSONAL = re.compile(r"\b(email|phone|address|name|birth|ssn|resident|customer|user|member|order)s?\b", re.IGNORECASE)
_PAYMENT = re.compile(r"\b(card|payment|billing|stripe|toss|iamport|portone|invoice)\b", re.IGNORECASE)


@dataclass(frozen=True)
class ContextSignals:
    test_or_example: bool
    browser_code: bool  # 'use client', .tsx 컴포넌트, public/ 정적 파일
    server_route: bool  # API 경로·서버 파일
    migration_or_schema: bool
    config_file: bool
    lockfile: bool
    third_party: bool
    likely_public_key: bool
    suppressed: bool  # 숨김 주석·설정으로 경고를 가리려 함
    takes_request_input: bool
    has_auth_check: bool
    mentions_personal_data: bool
    mentions_payment: bool

    def as_hints(self) -> list[str]:
        return [name for name, on in asdict(self).items() if on]


def collect_signals(finding: FindingInput) -> ContextSignals:
    path = (finding.file_path or "").replace("\\", "/")
    code = "\n".join(filter(None, [finding.snippet, finding.context]))
    flags = {f.flag for f in finding.flags}
    browser = bool(_USE_CLIENT.search(code) or _PUBLIC_ENV.search(code) or _PUBLIC_DIR.search(path)) or (
        bool(_CLIENT_PATH.search(path)) and not _USE_SERVER.search(code) and not _SERVER_ROUTE.search(path)
    )
    return ContextSignals(
        test_or_example=bool(_TEST.search(path) or _EXAMPLE.search(path)),
        browser_code=browser,
        server_route=bool(_SERVER_ROUTE.search(path)) and not browser,
        migration_or_schema=bool(_MIGRATION.search(path)),
        config_file=bool(_CONFIG.search(path)),
        lockfile=bool(_LOCKFILE.search(path)) or finding.category == "dependency",
        third_party="third_party_code" in flags or "/node_modules/" in f"/{path}" or "/vendor/" in f"/{path}",
        likely_public_key="likely_public_key" in flags,
        suppressed=bool(flags & {"suppressed_by_comment", "ignored_by_config"}),
        takes_request_input=bool(_REQUEST_INPUT.search(code)),
        has_auth_check=bool(_AUTH_CHECK.search(code)),
        mentions_personal_data=bool(_PERSONAL.search(code)),
        mentions_payment=bool(_PAYMENT.search(code)),
    )


def analysis_from_signals(finding: FindingInput, signals: ContextSignals) -> ContextAnalysis:
    """LLM 없이 규칙 신호만으로 내리는 판단. 확신도는 항상 low."""
    if signals.test_or_example or signals.third_party:
        runtime, exposure = "test", "not_deployed"
    elif finding.category == "dependency" or signals.lockfile:
        runtime, exposure = "dependency", "unknown"
    elif signals.migration_or_schema:
        runtime, exposure = "database", "public" if finding.category == "config" else "unknown"
    elif signals.browser_code:
        runtime, exposure = "browser", "public"
    elif signals.server_route:
        runtime, exposure = "server", "authenticated" if signals.has_auth_check else "public"
    elif signals.config_file:
        runtime, exposure = "config", "unknown"
    else:
        runtime, exposure = "unknown", "unknown"

    data: list = []
    if finding.category == "secret":
        data.append("credentials")
    if signals.mentions_payment:
        data.append("payment")
    if signals.mentions_personal_data:
        data.append("personal")
    if not data:
        data.append("unknown")

    not_deployed = exposure == "not_deployed"
    reachable = "no" if not_deployed else "yes" if (signals.takes_request_input or finding.category == "secret") else "unknown"
    return ContextAnalysis(
        runtime=runtime,
        exposure=exposure,
        reachable=reachable,
        data_at_risk=data[:3],
        attacker_needs=[],
        evidence=[f"규칙 신호: {', '.join(signals.as_hints()) or '없음'}"],
        vex_status="not_affected" if not_deployed else "under_investigation",
        vex_justification="vulnerable_code_not_in_execute_path" if not_deployed else None,
        confidence="low",
    )
