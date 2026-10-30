"""OS·사용 환경별 대응 가이드 (#33)."""

import pytest

from app.llm.pipeline import Explainer
from app.llm.remediation import build_guide, detect_package_manager
from app.llm.schemas import FindingInput, UserEnvironment
from tests.conftest import blue_draft

pytestmark = pytest.mark.anyio


def dep(lockfile: str, ecosystem: str = "npm", target: str | None = "4.17.21", package: str = "lodash") -> FindingInput:
    return FindingInput(
        fingerprint="d1",
        tool="osv",
        category="dependency",
        rule_id="CVE-2021-23337",
        title="lodash 취약점",
        severity="high",
        file_path=lockfile,
        package_name=package,
        package_ecosystem=ecosystem,
        installed_version="4.17.15",
        fixed_version=target,
    )


def secret(path: str = "src/lib/supabase.ts", rule: str = "supabase-service-role-key") -> FindingInput:
    return FindingInput(
        fingerprint="s1", tool="gitleaks", category="secret", rule_id=rule, title="키 노출", severity="critical", file_path=path
    )


def action(guide, action_id):
    return next(a for a in guide.actions if a.id == action_id)


def lines(act, os_):
    return next(b.lines for b in act.commands if b.os == os_)


@pytest.mark.parametrize(
    ("lockfile", "ecosystem", "expected"),
    [
        ("package-lock.json", "npm", "npm"),
        ("web/pnpm-lock.yaml", "npm", "pnpm"),
        ("yarn.lock", "npm", "yarn"),
        ("bun.lockb", "npm", "bun"),
        ("requirements.txt", "PyPI", "pip"),
        ("uv.lock", "PyPI", "uv"),
        ("poetry.lock", "PyPI", "poetry"),
        ("composer.lock", "Packagist", "composer"),
        ("Gemfile.lock", "RubyGems", "bundler"),
        ("go.sum", "Go", "go"),
        ("Cargo.lock", "crates.io", "cargo"),
        ("unknown.lock", "PyPI", "pip"),  # 파일로 모르면 생태계로
    ],
)
def test_package_manager_detection(lockfile, ecosystem, expected):
    assert detect_package_manager(dep(lockfile, ecosystem)) == expected


def test_npm_upgrade_for_every_os():
    guide = build_guide(dep("package-lock.json"))

    up = action(guide, "upgrade_dependency")
    assert {b.os for b in up.commands} == {"windows", "macos", "linux"}
    assert {b.shell for b in up.commands} == {"powershell", "zsh", "bash"}
    assert lines(up, "windows") == ["npm install lodash@4.17.21"]
    assert lines(action(guide, "commit_lockfile"), "linux")[0] == "git add package-lock.json"


def test_pip_uses_py_launcher_on_windows():
    guide = build_guide(dep("requirements.txt", "PyPI", package="django", target="4.2.16"))

    up = action(guide, "upgrade_dependency")
    assert lines(up, "windows") == ['py -m pip install "django>=4.2.16"']
    assert lines(up, "macos") == ['python3 -m pip install "django>=4.2.16"']
    assert any("requirements.txt" in m for m in up.manual_steps)


def test_only_requested_os_is_built():
    guide = build_guide(dep("package-lock.json"), UserEnvironment(os="macos"))

    assert all(b.os == "macos" for a in guide.actions for b in a.commands)


def test_no_fixed_version_has_no_commands():
    guide = build_guide(dep("package-lock.json", target=None))

    assert guide.actions[0].id == "no_fixed_version"
    assert not guide.actions[0].commands


def test_secret_guide_rotates_first_with_console_link():
    guide = build_guide(secret())

    assert guide.actions[0].id == "rotate_secret"
    assert "https://supabase.com/dashboard/project/_/settings/api-keys" in guide.actions[0].links
    env = action(guide, "move_to_env")
    assert "SUPABASE_SERVICE_ROLE_KEY" in env.title
    assert action(guide, "purge_history").optional is True


def test_windows_commands_are_powershell_51_safe():
    guide = build_guide(secret(), UserEnvironment(os="windows"))

    script = "\n".join(line for a in guide.actions for b in a.commands for line in b.lines)
    for unix_only in ("rm -rf", "&&", "grep ", "echo '", "export ", "python3"):
        assert unix_only not in script, unix_only
    assert "Add-Content" in script and "Select-String" in script


def test_secret_values_never_appear_in_commands():
    guide = build_guide(secret())

    script = "\n".join(line for a in guide.actions for b in a.commands for line in b.lines)
    assert "<새로 발급한 값>" in script  # 자리표시자만, 실제 값은 편집기로


def test_hosting_specific_env_step():
    vercel = build_guide(secret(), UserEnvironment(os="linux", hosting="vercel"))
    netlify = build_guide(secret(), UserEnvironment(os="linux", hosting="netlify"))

    assert lines(action(vercel, "hosting_env"), "linux") == ["vercel env add SUPABASE_SERVICE_ROLE_KEY production"]
    assert not action(netlify, "hosting_env").commands and action(netlify, "hosting_env").manual_steps


def test_committed_env_file_is_untracked():
    guide = build_guide(secret(path=".env.local", rule="generic-api-key"))

    assert lines(action(guide, "stop_tracking_env"), "windows")[0] == "git rm --cached .env.local"


def test_rls_sql_uses_table_names_from_snippet():
    f = FindingInput(
        fingerprint="c1",
        tool="own-checker",
        category="config",
        rule_id="vibe.supabase.rls-disabled",
        title="RLS 꺼짐",
        severity="high",
        snippet="create table public.customers (id uuid);\ncreate table if not exists orders (id uuid);\ncreate table x; drop table y",
    )

    sql = action(build_guide(f), "enable_rls").manual_steps

    assert "alter table public.customers enable row level security;" in sql
    assert "alter table public.orders enable row level security;" in sql
    assert not any("drop" in s for s in sql)


def test_code_finding_gets_optional_branch_and_rescan():
    f = FindingInput(
        fingerprint="x", tool="semgrep", category="code", rule_id="vibe.nextjs.sql-injection-template-literal",
        title="SQL", severity="high",
    )  # fmt: skip

    guide = build_guide(f)

    branch = action(guide, "work_branch")
    assert branch.optional and lines(branch, "linux") == ["git switch -c fix/vibe-nextjs-sql-injection-template"]
    assert guide.actions[-1].id == "rescan"


async def test_environment_reaches_prompt_and_result(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft())

    result = await Explainer(fake_vllm.client()).blue(findings[3], environment=UserEnvironment(os="windows"))

    prompt = fake_vllm.calls("BlueDraft")[0]["messages"][-1]["content"]
    assert '<environment>\n{"os": "windows", "package_manager": "npm"}' in prompt
    assert "<actions>" in prompt and "upgrade_dependency" in prompt
    assert "npm install next@15.2.3" not in prompt  # 명령 자체는 모델에 넘기지 않음
    assert result.guide.environment.os == "windows"
    assert lines(action(result.guide, "upgrade_dependency"), "windows") == ["npm install next@15.2.3"]
