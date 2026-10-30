"""OS·사용 환경별 대응 가이드: 검증된 명령 템플릿.

명령은 LLM 이 만들지 않습니다. 탐지 결과(분류·패키지·lockfile·규칙)와 사용자 환경으로 여기서 만들고,
Blue 는 "아래 Windows 명령을 실행하세요"처럼 가리키기만 합니다. 모델이 지어낸 명령을 비개발자가 그대로 실행하는 일을 막습니다.

- Windows 는 기본 설치된 Windows PowerShell 5.1 에서도 되는 문법만 씁니다 (&&·rm -rf 대신 줄 나눔·Remove-Item)
- 비밀값은 명령에 넣지 않습니다. 자리표시자만 넣고 편집기로 채우게 합니다 (터미널 기록에 남지 않게)
- 명령 주입 방어 (두 겹): 경로·패키지·버전은 탐지 결과(=검사한 저장소·API 입력)에서 오므로 믿지 않습니다.
  ① 허용 문자에 맞을 때만 명령을 만들고, 아니면 명령 없이 손으로 하는 안내로 내려보냅니다
  ② 그래도 모든 값을 OS별로 인용합니다 (bash·zsh 는 shlex.quote, PowerShell 은 작은따옴표)
"""

import re
import shlex

from app.llm.schemas import (
    CommandBlock,
    FindingInput,
    GuideAction,
    PackageManager,
    RemediationGuide,
    TargetOS,
    UserEnvironment,
)

ALL_OS: tuple[TargetOS, ...] = ("windows", "macos", "linux")
_SHELL = {"windows": "powershell", "macos": "zsh", "linux": "bash"}
_PLACEHOLDER = "<새로 발급한 값>"

_LOCKFILES: list[tuple[re.Pattern[str], PackageManager]] = [
    (re.compile(r"(^|/)(package-lock|npm-shrinkwrap)\.json$"), "npm"),
    (re.compile(r"(^|/)pnpm-lock\.yaml$"), "pnpm"),
    (re.compile(r"(^|/)yarn\.lock$"), "yarn"),
    (re.compile(r"(^|/)bun\.lockb?$"), "bun"),
    (re.compile(r"(^|/)uv\.lock$"), "uv"),
    (re.compile(r"(^|/)poetry\.lock$"), "poetry"),
    (re.compile(r"(^|/)(requirements[^/]*\.txt|Pipfile\.lock)$"), "pip"),
    (re.compile(r"(^|/)composer\.lock$"), "composer"),
    (re.compile(r"(^|/)Gemfile\.lock$"), "bundler"),
    (re.compile(r"(^|/)go\.(sum|mod)$"), "go"),
    (re.compile(r"(^|/)Cargo\.lock$"), "cargo"),
]
_ECOSYSTEM: dict[str, PackageManager] = {
    "npm": "npm", "PyPI": "pip", "Packagist": "composer", "RubyGems": "bundler", "Go": "go", "crates.io": "cargo",
}  # fmt: skip

# 키를 폐기·재발급하는 곳 (규칙 ID·제목·코드에 이 낱말이 있으면)
_KEY_CONSOLES = [
    ("supabase", "Supabase", "https://supabase.com/dashboard/project/_/settings/api-keys"),
    ("stripe", "Stripe", "https://dashboard.stripe.com/apikeys"),
    ("openai", "OpenAI", "https://platform.openai.com/api-keys"),
    ("anthropic", "Anthropic", "https://console.anthropic.com/settings/keys"),
    ("github", "GitHub", "https://github.com/settings/tokens"),
    ("aws", "AWS", "https://console.aws.amazon.com/iam/home#/security_credentials"),
    ("akia", "AWS", "https://console.aws.amazon.com/iam/home#/security_credentials"),
    ("google", "Google Cloud", "https://console.cloud.google.com/apis/credentials"),
    ("firebase", "Google Cloud", "https://console.cloud.google.com/apis/credentials"),
    ("slack", "Slack", "https://api.slack.com/apps"),
    ("sendgrid", "SendGrid", "https://app.sendgrid.com/settings/api_keys"),
    ("twilio", "Twilio", "https://console.twilio.com/"),
]
_HOSTING_ENV = {
    "vercel": (["vercel env add {name} production"], "https://vercel.com/docs/environment-variables"),
    "cloudflare": (["npx wrangler secret put {name}"], "https://developers.cloudflare.com/workers/configuration/secrets/"),
    "netlify": ([], "https://docs.netlify.com/environment-variables/overview/"),
    "supabase": ([], "https://supabase.com/docs/guides/functions/secrets"),
    "render": ([], "https://render.com/docs/configure-environment-variables"),
    "railway": ([], "https://docs.railway.com/guides/variables"),
}
_CREATE_TABLE = re.compile(
    r'create\s+table\s+(?:if\s+not\s+exists\s+)?(?:"?public"?\.)?"?([A-Za-z_][A-Za-z0-9_]*)"?', re.IGNORECASE
)


# 명령에 넣어도 되는 값. 맨 앞 '-' 는 막습니다 (옵션으로 해석되는 인자 주입 방지)
_SAFE_PATH = re.compile(r"^(?!-)[A-Za-z0-9._/@+-]+$")
_SAFE_PACKAGE = re.compile(r"^(?!-)[@A-Za-z0-9._/~:+-]+$")
_SAFE_VERSION = re.compile(r"^v?[0-9A-Za-z.+~-]+$")
# PowerShell 에서 따옴표 없이 둬도 되는 인자. '@이름' 처럼 '/' 없이 끝나는 인자는 splatting($이름)으로 해석돼
# 소리 없이 사라집니다 (PowerShell 5.1 에서 확인). '@scope/pkg' 는 괜찮지만 '@' 로 시작하면 일관되게 인용합니다
_PS_BARE = re.compile(r"^[A-Za-z0-9._/:=+~-][A-Za-z0-9._/:=+~@-]*$")


def safe_path(value: str | None) -> str | None:
    if value and _SAFE_PATH.match(value) and ".." not in value.split("/"):
        return value
    return None


def safe_package(value: str | None) -> str | None:
    return value if value and _SAFE_PACKAGE.match(value) else None


def safe_version(value: str | None) -> str | None:
    return value if value and _SAFE_VERSION.match(value) else None


def quote(os_: TargetOS, value: str) -> str:
    """셸 인자 하나로 인용합니다. 허용 문자 검사를 통과한 값에도 적용하는 두 번째 방어선입니다."""
    if os_ == "windows":
        return value if _PS_BARE.match(value) else "'" + value.replace("'", "''") + "'"
    return shlex.quote(value)


def detect_package_manager(finding: FindingInput) -> PackageManager | None:
    path = (finding.file_path or (finding.fix_hint.lockfile if finding.fix_hint else "") or "").replace("\\", "/")
    for pattern, manager in _LOCKFILES:
        if pattern.search(path):
            return manager
    return _ECOSYSTEM.get(finding.package_ecosystem or "")


def build_guide(finding: FindingInput, environment: UserEnvironment | None = None) -> RemediationGuide:
    env = environment or UserEnvironment()
    oses = [env.os] if env.os else list(ALL_OS)
    manager = env.package_manager or detect_package_manager(finding)
    actions: list[GuideAction] = []
    if finding.category == "dependency":
        actions += _dependency(finding, manager, oses)
    elif finding.category == "secret":
        actions += _secret(finding, env, oses)
    elif finding.category == "config" and _is_rls(finding):
        actions += _rls(finding)
    else:
        actions.append(_work_branch(finding, oses))
    actions.append(_rescan())
    return RemediationGuide(environment=env, package_manager=manager, actions=actions)


def _blocks(oses: list[TargetOS], lines_for) -> list[CommandBlock]:
    """lines_for(os) 가 None 이나 빈 목록이면 그 OS 블록은 만들지 않습니다."""
    return [CommandBlock(os=o, shell=_SHELL[o], lines=lines) for o in oses if (lines := lines_for(o))]


def _same(lines: list[str]):
    return lambda _os: lines


# ── 의존성 ──


def _python(os_: TargetOS) -> str:
    # Windows 는 python 명령이 스토어 안내로 연결되는 경우가 있어 py 런처를 씁니다
    return "py" if os_ == "windows" else "python3"


def _upgrade_lines(manager: PackageManager | None, pkg: str, ver: str, os_: TargetOS) -> list[str] | None:
    def q(value: str) -> str:
        return quote(os_, value)

    return {
        "npm": [f"npm install {q(f'{pkg}@{ver}')}"],
        "pnpm": [f"pnpm add {q(f'{pkg}@{ver}')}"],
        "yarn": [f"yarn add {q(f'{pkg}@{ver}')}"],
        "bun": [f"bun add {q(f'{pkg}@{ver}')}"],
        "pip": [f"{_python(os_)} -m pip install {q(f'{pkg}>={ver}')}"],
        "uv": [f"uv add {q(f'{pkg}>={ver}')}"],
        "poetry": [f"poetry add {q(f'{pkg}@^{ver}')}"],
        "composer": [f"composer require {q(f'{pkg}:^{ver}')}"],
        "bundler": [f"bundle update {q(pkg)}"],
        "go": [f"go get {q(pkg + '@v' + ver.lstrip('v'))}", "go mod tidy"],
        "cargo": [f"cargo update -p {q(pkg)} --precise {q(ver)}"],
    }.get(manager or "")


def _verify_lines(manager: PackageManager | None, pkg: str, os_: TargetOS) -> list[str] | None:
    p = quote(os_, pkg)
    return {
        "npm": [f"npm ls {p}"],
        "pnpm": [f"pnpm why {p}"],
        "yarn": [f"yarn why {p}"],
        "bun": ["bun pm ls"],
        "pip": [f"{_python(os_)} -m pip show {p}"],
        "uv": [f"uv pip show {p}"],
        "poetry": [f"poetry show {p}"],
        "composer": [f"composer show {p}"],
        "bundler": [f"bundle info {p}"],
        "go": [f"go list -m {p}"],
        "cargo": [f"cargo tree -i {p}"],
    }.get(manager or "")


def _dependency(finding: FindingInput, manager, oses) -> list[GuideAction]:
    raw_pkg = finding.package_name or (finding.fix_hint.package if finding.fix_hint else None)
    raw_ver = finding.fixed_version or (finding.fix_hint.target_version if finding.fix_hint else None)
    if not raw_pkg:
        return []
    pkg, ver = safe_package(raw_pkg), safe_version(raw_ver)
    if not pkg or (raw_ver and not ver):
        # 명령에 넣기 위험한 글자가 있으면 명령을 만들지 않습니다 (명령 주입 방지)
        return [
            GuideAction(
                id="upgrade_dependency_manual",
                title="패키지 업그레이드 (직접)",
                why="패키지 이름이나 버전에 명령에 쓰기 어려운 글자가 있어 실행 명령을 만들지 않았습니다",
                manual_steps=["패키지 관리자 화면이나 설정 파일에서 이 패키지를 고친 버전으로 올립니다"],
            )
        ]
    if not ver:
        return [
            GuideAction(
                id="no_fixed_version",
                title=f"{pkg}: 아직 고친 버전이 없습니다",
                why="업그레이드로는 해결할 수 없습니다",
                manual_steps=[
                    "같은 기능을 하는 다른 패키지로 바꿀 수 있는지 확인합니다",
                    "바꿀 수 없다면 취약한 기능을 쓰지 않도록 코드를 고칩니다 (AI 코딩툴 지시문 참고)",
                ],
            )
        ]
    manual = []
    if manager == "pip":
        manual.append(f"requirements.txt 의 {pkg} 버전도 {ver} 이상으로 고칩니다")
    if manager == "bundler":
        manual.append(f"Gemfile 의 {pkg} 버전 조건이 {ver} 를 허용하는지 확인합니다")
    if manager is None:
        manual.append(f"사용하는 패키지 관리자로 {pkg} 를 {ver} 이상으로 올립니다 (lockfile 을 찾지 못했습니다)")
    raw_lockfile = finding.file_path or (finding.fix_hint.lockfile if finding.fix_hint else None)
    lockfile = safe_path(raw_lockfile)
    actions = [
        GuideAction(
            id="upgrade_dependency",
            title=f"{pkg} 를 {ver} 이상으로 올리기",
            why="고쳐진 버전으로 올리면 이 취약점이 사라집니다",
            commands=_blocks(oses, lambda o: _upgrade_lines(manager, pkg, ver, o)),
            manual_steps=manual,
        ),
        GuideAction(
            id="verify_dependency",
            title="설치된 버전 확인",
            why=f"{ver} 이상이 설치됐는지 확인합니다",
            commands=_blocks(oses, lambda o: _verify_lines(manager, pkg, o)),
        ),
    ]
    if raw_lockfile and manager:
        why = "lockfile 을 올리지 않으면 배포 서버는 예전 버전을 다시 설치합니다"
        if lockfile:
            message = f"fix(deps): upgrade {pkg} to {ver}"
            action = GuideAction(
                id="commit_lockfile",
                title="lockfile 함께 커밋",
                why=why,
                commands=_blocks(
                    oses, lambda o: [f"git add {quote(o, lockfile)}", f"git commit -m {quote(o, message)}"]
                ),
            )
        else:
            action = GuideAction(
                id="commit_lockfile",
                title="lockfile 함께 커밋 (직접)",
                why=why + ". 경로에 명령에 쓰기 어려운 글자가 있어 실행 명령을 만들지 않았습니다",
                manual_steps=["Git 화면(GitHub Desktop·VS Code 등)에서 바뀐 lockfile 을 골라 커밋합니다"],
            )
        actions.append(action)
    return actions


# ── 비밀값 ──


def _env_name(finding: FindingInput) -> str:
    name = re.sub(r"[^A-Za-z0-9]+", "_", finding.rule_id).strip("_").upper()
    if not re.match(r"^[A-Z_]", name):
        name = f"SECRET_{name}"
    return name[:60] or "SECRET_KEY"


def _secret(finding: FindingInput, env: UserEnvironment, oses) -> list[GuideAction]:
    text = " ".join(filter(None, [finding.rule_id, finding.title, finding.snippet])).lower()
    consoles = {label: url for key, label, url in _KEY_CONSOLES if key in text}
    name = _env_name(finding)
    actions = [
        GuideAction(
            id="rotate_secret",
            title="노출된 키 폐기하고 새로 발급",
            why="이미 노출된 키는 코드에서 지워도 누군가 가져갔을 수 있습니다. 가장 먼저 해야 합니다",
            manual_steps=[
                f"{' · '.join(consoles) or '해당 서비스'} 대시보드에서 노출된 키를 폐기(삭제)합니다",
                "새 키를 발급합니다. 새 키는 코드에 쓰지 않고 다음 단계의 환경 변수로 넣습니다",
            ],
            links=list(dict.fromkeys(consoles.values())),
        ),
        GuideAction(
            id="move_to_env",
            title=f"키를 환경 변수 {name} 로 옮기기",
            why="키를 코드 밖(.env)에 두고 .gitignore 로 저장소에 올라가지 않게 합니다",
            commands=_blocks(
                oses,
                lambda o: [
                    f"Add-Content -Path .env -Value '{name}={_PLACEHOLDER}'",
                    "if (-not (Select-String -Path .gitignore -Pattern '^\\.env$' -Quiet -ErrorAction SilentlyContinue)) "
                    "{ Add-Content -Path .gitignore -Value '.env' }",
                ]
                if o == "windows"
                else [
                    f"echo '{name}={_PLACEHOLDER}' >> .env",
                    "grep -qxF '.env' .gitignore 2>/dev/null || echo '.env' >> .gitignore",
                ],
            ),
            manual_steps=[
                f".env 파일을 편집기로 열어 {_PLACEHOLDER} 자리에 새 키를 붙여 넣습니다 (터미널에 키를 직접 치면 기록에 남습니다)",
                f"코드에서는 환경 변수 {name} 를 읽게 바꿉니다. NEXT_PUBLIC_·VITE_ 같은 접두어를 붙이면 브라우저에 그대로 실리니 붙이지 않습니다",
            ],
        ),
    ]
    if env.hosting and env.hosting in _HOSTING_ENV:
        lines, doc = _HOSTING_ENV[env.hosting]
        actions.append(
            GuideAction(
                id="hosting_env",
                title=f"{env.hosting} 배포 환경에도 새 키 등록",
                why="배포된 사이트는 내 PC 의 .env 를 읽지 않습니다",
                commands=_blocks(oses, _same([line.format(name=name) for line in lines])),
                manual_steps=[] if lines else [f"{env.hosting} 대시보드의 환경 변수 설정에서 {name} 를 새 키로 등록합니다"],
                links=[doc],
            )
        )
    path = (finding.file_path or "").replace("\\", "/")
    if re.search(r"(^|/)\.env(\.[\w.-]+)?$", path) and not path.endswith(".example"):
        tracked = safe_path(path)
        actions.append(
            GuideAction(
                id="stop_tracking_env",
                title=".env 파일을 저장소에서 빼기",
                why="파일은 PC 에 남기고 Git 추적만 멈춥니다",
                commands=_blocks(
                    oses,
                    lambda o: [f"git rm --cached {quote(o, tracked)}", f"git commit -m {quote(o, 'chore: stop tracking env file')}"]
                    if tracked
                    else None,
                ),
                manual_steps=[]
                if tracked
                else ["경로에 명령에 쓰기 어려운 글자가 있어 실행 명령을 만들지 않았습니다. Git 화면에서 이 파일의 추적을 해제합니다"],
            )
        )
    actions.append(
        GuideAction(
            id="purge_history",
            title="(선택) Git 기록에서도 지우기",
            why="공개 저장소였다면 예전 커밋에 키가 남아 있습니다. 키를 재발급했다면 꼭 필요하지는 않습니다",
            commands=_blocks(
                oses,
                lambda o: {
                    "windows": ["py -m pip install --user git-filter-repo"],
                    "macos": ["brew install git-filter-repo"],
                    "linux": ["python3 -m pip install --user git-filter-repo"],
                }[o],
            ),
            manual_steps=["설치한 뒤 GitHub 안내에 따라 기록을 지우고, 함께 작업하는 사람에게 다시 clone 하라고 알립니다"],
            links=[
                "https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository"
            ],
            optional=True,
        )
    )
    return actions


# ── 설정 (Supabase RLS) ──


def _is_rls(finding: FindingInput) -> bool:
    return "rls" in f"{finding.rule_id} {finding.title}".lower()


def _rls(finding: FindingInput) -> list[GuideAction]:
    tables = list(dict.fromkeys(_CREATE_TABLE.findall(finding.snippet or "")))
    sql = [f"alter table public.{t} enable row level security;" for t in tables] or [
        "alter table public.<테이블 이름> enable row level security;"
    ]
    return [
        GuideAction(
            id="enable_rls",
            title="RLS(행 단위 접근 제한) 켜기",
            why="RLS 가 꺼진 테이블은 공개용 anon 키만으로 누구나 읽고 쓸 수 있습니다",
            manual_steps=[
                "Supabase 대시보드 → SQL Editor 에서 아래 SQL 을 실행합니다 (OS 와 무관)",
                *sql,
                "RLS 를 켜면 정책이 없는 테이블은 아무도 읽지 못합니다. 사이트에서 필요한 조회만 허용하는 정책을 추가합니다",
            ],
            links=["https://supabase.com/docs/guides/database/postgres/row-level-security"],
        )
    ]


# ── 코드 ──


def _work_branch(finding: FindingInput, oses) -> GuideAction:
    slug = re.sub(r"[^a-z0-9]+", "-", finding.rule_id.lower()).strip("-")
    if len(slug) > 40:
        slug = slug[:40].rsplit("-", 1)[0]  # 낱말 중간에서 자르지 않습니다
    slug = slug or "security"
    return GuideAction(
        id="work_branch",
        title="(선택) 고치기 전에 작업 브랜치 만들기",
        why="AI 코딩툴이 고친 결과가 마음에 들지 않으면 쉽게 되돌릴 수 있습니다",
        commands=_blocks(oses, _same([f"git switch -c fix/{slug}"])),
        optional=True,
    )


def _rescan() -> GuideAction:
    return GuideAction(
        id="rescan",
        title="다시 검사해 해결 확인",
        why="고친 뒤 다시 검사해야 '해결'로 확인되고 72시간 타이머가 멈춥니다",
        manual_steps=["변경을 저장소에 올린 뒤 대시보드에서 '다시 검사'를 누릅니다"],
    )
