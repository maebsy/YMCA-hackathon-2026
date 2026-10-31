"""Red·Blue 출력 → 실검증 입력 연결 (#97). 가짜 vLLM으로 모델 출력을 주입합니다."""
import shutil
from pathlib import Path

import pytest

from app.llm.schemas import FindingInput, FindingRefs
from app.verify import llm_bridge as B
from app.verify import verifier as V

pytestmark = pytest.mark.anyio

DEMO = Path(__file__).resolve().parents[2] / "demo-vulnerable-site"
FIXED = (DEMO / "verify" / "fix" / "server.js").read_text(encoding="utf-8")

SQLI = FindingInput(fingerprint="semgrep:sqli", tool="semgrep", category="code", rule_id="vibe-coding/sql-string-concat",
                    title="SQL 문자열 연결", severity="critical", file_path="server.js", start_line=39,
                    refs=FindingRefs(cwe=["CWE-89"]))
XSS = FindingInput(fingerprint="red:xss", tool="red", category="code", rule_id="reflected-xss",
                   title="검색어가 HTML에 그대로 출력", severity="high", file_path="server.js", start_line=49)


def red(**over):
    attack = {"reproducible": True, "method": "GET", "path": "/api/orders", "query": [{"name": "orderId", "value": "0 OR 1=1"}],
              "body": "", "content_type": "none", "success_rule": "json_array_len_gte", "success_value": "2",
              "reason": "조건이 항상 참이 되어 모든 주문이 나옵니다."}
    attack.update(over)
    return {"attack": attack}


RED_XSS = red(path="/search", query=[{"name": "q", "value": "<script>alert(1)</script>"}],
              success_rule="body_contains", success_value="<script>alert(1)</script>", reason="입력이 그대로 반사됩니다.")


def blue(content=FIXED, file_path="server.js"):
    return {"file_path": file_path, "content": content, "summary": "자리표시자와 이스케이프로 고쳤습니다."}


async def test_red_blue_outputs_become_verify_inputs(fake_vllm):
    fake_vllm.queue("RedAttackPlan", red(), RED_XSS).queue("BluePatch", blue())

    plan = await B.plan_verification(fake_vllm.client(), [SQLI, XSS], DEMO)

    assert not plan.skipped
    sqli, xss = plan.attacks
    assert sqli.request.path == "/api/orders" and sqli.request.query == {"orderId": "0 OR 1=1"}
    assert sqli.success_when == "json_array_len_gte:2" and sqli.cwe == "CWE-89" and sqli.runtime
    assert xss.success_when == "body_contains:<script>alert(1)</script>"
    assert plan.attack_fingerprints == {sqli.id: "semgrep:sqli", xss.id: "red:xss"}
    assert plan.patch.files == {"server.js": FIXED}
    # 같은 파일의 두 결과는 Blue가 한 번에 고칩니다. 두 모델 모두 파일 전체를 봅니다
    assert len(fake_vllm.calls("BluePatch")) == 1
    for call in fake_vllm.calls("RedAttackPlan") + fake_vllm.calls("BluePatch"):
        assert 'app.get("/api/orders"' in call["messages"][-1]["content"]
    assert '"attacks"' in B.plan_json(plan)


@pytest.mark.parametrize(
    ("over", "why"),
    [
        ({"path": "http://169.254.169.254/latest"}, "앱 안 경로"),
        ({"path": "//evil.example/x"}, "앱 안 경로"),
        ({"path": "api/orders"}, "앱 안 경로"),
        ({"reproducible": False}, "재현할 수 없"),
        ({"success_rule": "status_eq", "success_value": "abc"}, "성공 판정"),
        ({"success_rule": "json_array_len_gte", "success_value": "0"}, "성공 판정"),
        ({"success_rule": "body_contains", "success_value": "  "}, "성공 판정"),
        ({"query": [{"name": " ", "value": "x"}]}, "파라미터 이름"),
    ],
)
async def test_bad_red_output_is_skipped(fake_vllm, over, why):
    fake_vllm.queue("RedAttackPlan", red(**over)).queue("BluePatch", blue())

    plan = await B.plan_verification(fake_vllm.client(), [SQLI], DEMO)

    assert not plan.attacks
    assert plan.skipped[0].stage == "red" and why in plan.skipped[0].reason


@pytest.mark.parametrize(
    ("patch", "why"),
    [
        (blue(file_path="../package.json"), "입력에 없는 파일"),
        (blue(file_path="other.js"), "입력에 없는 파일"),
        (blue(content="   "), "비어"),
        (blue(content=(DEMO / "server.js").read_text(encoding="utf-8")), "원본과 같"),
        (blue(content="// ...이하 동일\n"), "절반보다 짧"),
    ],
)
async def test_bad_blue_output_is_skipped(fake_vllm, patch, why):
    fake_vllm.queue("RedAttackPlan", red()).queue("BluePatch", patch)

    plan = await B.plan_verification(fake_vllm.client(), [SQLI], DEMO)

    assert not plan.patch.files
    assert plan.skipped[0].stage == "blue" and why in plan.skipped[0].reason


async def test_fenced_patch_is_unwrapped(fake_vllm):
    fake_vllm.queue("RedAttackPlan", red()).queue("BluePatch", blue(content=f"```javascript\n{FIXED}```"))

    plan = await B.plan_verification(fake_vllm.client(), [SQLI], DEMO)

    assert plan.patch.files["server.js"].strip() == FIXED.strip()


@pytest.mark.parametrize("file_path", [None, "../../etc/passwd", "/etc/passwd", "missing.js"])
async def test_findings_without_readable_file_are_skipped_before_llm(fake_vllm, file_path):
    finding = SQLI.model_copy(update={"file_path": file_path})

    plan = await B.plan_verification(fake_vllm.client(), [finding], DEMO)

    assert plan.skipped[0].stage == "input" and not fake_vllm.requests


async def test_oversized_file_is_skipped(fake_vllm, tmp_path):
    (tmp_path / "big.js").write_text("x" * (B.MAX_SOURCE_CHARS + 1), encoding="utf-8")

    plan = await B.plan_verification(fake_vllm.client(), [SQLI.model_copy(update={"file_path": "big.js"})], tmp_path)

    assert "넘어" in plan.skipped[0].reason and not fake_vllm.requests


class _FakeSandbox:
    name = "docker"

    def __init__(self):
        self.cfgs = []

    def run(self, workdir, cfg, **kw):
        self.cfgs.append((workdir, cfg))
        after = len(self.cfgs) == 2
        assert ("WHERE id = ?" in (Path(workdir) / "server.js").read_text(encoding="utf-8")) is after  # 수정본은 after에만
        iso = {"network_isolated": True, "non_root": True, "caps_dropped": True, "no_new_privs": True}
        attacks = [{"id": a["id"], "succeeded": not after, "status": 200, "evidence": "x"} for a in cfg["attacks"]]
        return {"reachable": True, "attacks": attacks, "tests": {"ok": True, "passed": 3, "failed": 0}, "isolation": iso}


async def test_verify_findings_runs_before_after(fake_vllm, monkeypatch):
    sandbox = _FakeSandbox()
    monkeypatch.setattr(V, "pick_sandbox", lambda trusted: sandbox)
    fake_vllm.queue("RedAttackPlan", red(), RED_XSS).queue("BluePatch", blue())

    out = await B.verify_findings(fake_vllm.client(), [SQLI, XSS], DEMO)

    assert out.result.status == "verified" and out.result.isolation_confirmed
    assert [a.verdict for a in out.result.attacks] == ["verified", "verified"]
    sent = sandbox.cfgs[0][1]["attacks"]
    assert [a["request"]["path"] for a in sent] == ["/api/orders", "/search"]


async def test_nothing_to_verify_returns_plan_only(fake_vllm):
    fake_vllm.queue("RedAttackPlan", red(reproducible=False)).queue("BluePatch", blue())

    out = await B.verify_findings(fake_vllm.client(), [SQLI], DEMO)

    assert out.result is None and out.plan.skipped


# ── 통합: 실제 데모 과녁 + 샌드박스 (Docker 있으면 Docker, 없으면 Local). Node 22.5+ 필요 ──
def _node_ok() -> bool:
    import subprocess
    exe = shutil.which("node")
    if not exe or not shutil.which("npm"):
        return False
    try:
        return subprocess.run([exe, "-e", "require('node:sqlite')"], capture_output=True, timeout=20, check=False).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.mark.skipif(not _node_ok(), reason="Node 22.5+(node:sqlite)·npm 필요")
async def test_integration_llm_outputs_verified_in_sandbox(fake_vllm):
    fake_vllm.queue("RedAttackPlan", red(), RED_XSS).queue("BluePatch", blue())

    out = await B.verify_findings(fake_vllm.client(), [SQLI, XSS], DEMO, trusted=True)

    assert out.result.status == "verified", out.result.message
    assert {a.verdict for a in out.result.attacks} == {"verified"}
