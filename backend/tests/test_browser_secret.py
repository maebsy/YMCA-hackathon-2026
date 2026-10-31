"""#100: 브라우저로 전달되는 비밀값은 키 권한을 확인하기 전까지 사람 확인 대상입니다.

재현: Homebrew/formulae.brew.sh `_layouts/base.html` 의 Algolia 키를 gitleaks 가 찾았는데,
LLM 이 '환경 변수로 옮기기'를 안내하고 Red 가 pass, needs_manual_review=false 로 내보내
MCP 자동 전달 대상이 됐습니다. 키는 docsearch(... jsonify) 로 여전히 페이지에 박힙니다.
"""

from datetime import datetime, timezone

import pytest

from app.llm import prompts
from app.llm.context import collect_signals
from app.llm.pipeline import Explainer
from app.llm.schemas import BROWSER_SECRET_REVIEW, FindingInput
from app.reports import plain
from tests.conftest import blue_draft, red_review
from tests.test_reports import explanation, findings_data, plain_request


def secret(**overrides) -> FindingInput:
    base = {
        "fingerprint": "gitleaks-algolia",
        "tool": "gitleaks",
        "category": "secret",
        "rule_id": "generic-api-key",
        "title": "Detected a Generic API Key",
        "severity": "high",
        "file_path": "_layouts/base.html",
        "start_line": 3,
        "snippet": "  api_key: [가림]",
        "context": "<script>\n  docsearch({ ...{{ layout.algolia | jsonify }} });\n</script>",
    }
    return FindingInput.model_validate({**base, **overrides})


@pytest.mark.parametrize(
    "overrides",
    [
        {},  # 이슈 재현: Jekyll 레이아웃 + docsearch(jsonify)
        {"file_path": "_includes/search.html", "context": None},  # 템플릿 경로만으로
        {"file_path": "config/site.yml", "context": "{{ site.algolia | jsonify }}"},  # 템플릿 값이 페이지로
        {"file_path": "config/site.yml", "context": None, "flags": [{"flag": "likely_public_key", "note": ""}]},
    ],
)
def test_browser_delivered_secret_is_flagged(overrides):
    assert collect_signals(secret(**overrides)).browser_secret


def test_server_secret_is_not_browser_secret():
    f = secret(file_path="src/app/api/search/route.ts", snippet="const key = process.env.ALGOLIA_ADMIN_KEY", context=None)
    assert not collect_signals(f).browser_secret


def test_code_finding_in_template_is_not_browser_secret():
    f = secret(category="code", tool="semgrep", rule_id="xss")
    signals = collect_signals(f)
    assert signals.browser_code and not signals.browser_secret



@pytest.mark.anyio
async def test_red_pass_still_needs_manual_review_for_browser_key(fake_vllm):
    """Red 가 pass 여도 키 권한은 코드 밖에서 확인해야 하므로 MCP 자동 전달 조건(needs_manual_review=false)을 막습니다."""
    fake_vllm.queue("BlueDraft", blue_draft()).queue("RedReview", red_review("pass"))

    result = await Explainer(fake_vllm.client()).red_blue(secret())

    assert result.red_verdict == "pass"
    assert result.needs_manual_review is True
    assert result.manual_review_reason == BROWSER_SECRET_REVIEW


@pytest.mark.anyio
async def test_blue_only_browser_key_also_needs_manual_review(fake_vllm):
    fake_vllm.queue("BlueDraft", blue_draft())
    result = await Explainer(fake_vllm.client()).blue(secret())
    assert result.needs_manual_review is True


@pytest.mark.anyio
async def test_server_code_finding_unchanged(fake_vllm, findings):
    fake_vllm.queue("BlueDraft", blue_draft()).queue("RedReview", red_review("pass"))
    result = await Explainer(fake_vllm.client()).red_blue(findings[1])
    assert result.needs_manual_review is False and result.manual_review_reason is None


def test_prompts_reject_env_var_only_fix_for_browser_keys():
    assert "환경 변수나 설정 파일로 옮겨도" in prompts.BLUE_SYSTEM
    assert "허용 도메인" in prompts.BLUE_SYSTEM and "서버(API 경로)" in prompts.BLUE_SYSTEM
    assert "\"환경 변수로 옮기기\"만으로 해결된다고 하면 bypass" in prompts.RED_SYSTEM
    # 공개용 키 표시만으로 오탐 처리하지 않습니다
    assert "likely_public_key는 오탐 의심의 근거로 씁니다" not in prompts.BLUE_SYSTEM
    assert "_layouts" in prompts.CONTEXT_SYSTEM


def test_report_explains_permission_check_not_red_failure():
    fp = findings_data()[0]["fingerprint"]
    # 저장된 결과에서 이유가 빠져도(DB 열 없음) Red 통과 + 수동 확인이면 권한 확인 문구를 씁니다
    for extra in ({"manual_review_reason": BROWSER_SECRET_REVIEW}, {}):
        req = plain_request(results=[explanation(fp, needs_manual_review=True, **extra)])
        report = plain.build_plain_report(req, datetime(2026, 11, 1, tzinfo=timezone.utc))
        text = report.model_dump_json()
        assert "쓰기·관리 권한" in text
        assert "끝까지 통과시키지 못했습니다" not in text


# ── 리뷰 후속: 폴더 이름만으로 서버 코드를 브라우저 코드로 보지 않기 ──
import pytest  # noqa: E402

from app.llm.context import collect_signals as _signals  # noqa: E402
from app.llm.schemas import FindingInput as _Finding  # noqa: E402


def _sig(path, category="secret", code='API_KEY = "x"'):
    return _signals(_Finding(fingerprint="f", tool="gitleaks", category=category, rule_id="r", title="t",
                             severity="high", file_path=path, snippet=code))


@pytest.mark.parametrize("path", ["myapp/views/payments.py", "shop/templates/render.py", "app/views/helpers.rb"])
def test_server_code_in_views_or_templates_dir_is_not_browser_code(path):
    s = _sig(path)
    assert not s.browser_code and not s.browser_secret
    assert not _sig(path, category="code", code="cursor.execute('SELECT ' + q)").browser_code


@pytest.mark.parametrize("path", ["_layouts/base.html", "_includes/head.liquid", "server/views/index.ejs",
                                  "app/views/users/show.html.erb", "templates/page.njk"])
def test_rendered_templates_are_browser_code_even_under_server_paths(path):
    assert _sig(path).browser_secret
