import json

import pytest
from fastapi.testclient import TestClient

from app.llm.pipeline import Explainer
from app.main import app
from app.routers.llm import get_explainer
from tests.conftest import FIXTURES, FakeVLLM, blue_draft


@pytest.fixture
def api(fake_vllm):
    explainer = Explainer(fake_vllm.client())
    app.dependency_overrides[get_explainer] = lambda: explainer
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def sample_findings(n: int = 1) -> list[dict]:
    return json.loads((FIXTURES / "findings.json").read_text(encoding="utf-8"))[:n]


def test_health_ok(api):
    resp = api.get("/api/llm/health")

    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "model": "qwen3.8-27b"}


def test_health_503_when_model_not_loaded():
    explainer = Explainer(FakeVLLM(models=("other",)).client())
    app.dependency_overrides[get_explainer] = lambda: explainer
    try:
        with TestClient(app) as client:
            resp = client.get("/api/llm/health")
    finally:
        app.dependency_overrides.clear()

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "LLM_UNAVAILABLE"


def test_explain_blue(api, fake_vllm):
    fake_vllm.queue("BlueDraft", blue_draft(), blue_draft())

    resp = api.post("/api/llm/explain", json={"findings": sample_findings(2), "mode": "blue"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "blue"
    assert body["model"] == "qwen3.8-27b"
    assert [r["status"] for r in body["results"]] == ["done", "done"]
    assert body["results"][0]["explanation"]["variant"] == "C"


@pytest.mark.parametrize(
    "payload",
    [
        {"findings": []},
        {"findings": sample_findings(1) * 51},
        {"findings": [{**sample_findings(1)[0], "severity": "urgent"}]},
        {"findings": sample_findings(1), "mode": "red"},
    ],
    ids=["empty", "too-many", "bad-severity", "bad-mode"],
)
def test_explain_rejects_bad_requests(api, payload):
    assert api.post("/api/llm/explain", json=payload).status_code == 422


def test_explain_503_when_llm_down(api, fake_vllm):
    fake_vllm.queue("BlueDraft", *([503] * 6))

    resp = api.post("/api/llm/explain", json={"findings": sample_findings(2), "mode": "blue"})

    assert resp.status_code == 503
    assert resp.json()["detail"]["code"] == "LLM_UNAVAILABLE"


def test_default_mode_is_red_blue(api, fake_vllm):
    from tests.conftest import red_review

    fake_vllm.queue("BlueDraft", blue_draft()).queue("RedReview", red_review("pass"))

    resp = api.post("/api/llm/explain", json={"findings": sample_findings(1)})

    explanation = resp.json()["results"][0]["explanation"]
    assert explanation["variant"] == "D"
    assert explanation["red_verdict"] == "pass"


def test_unknown_severity_is_accepted(api, fake_vllm):
    fake_vllm.queue("BlueDraft", blue_draft())

    resp = api.post(
        "/api/llm/explain", json={"findings": [{**sample_findings(1)[0], "severity": "unknown"}], "mode": "blue"}
    )

    assert resp.status_code == 200


def test_skipped_items_do_not_hide_an_outage(api, fake_vllm):
    resolved = {**sample_findings(1)[0], "fingerprint": "done-already", "status": "code_resolved"}
    fake_vllm.queue("BlueDraft", 503, 503, 503)

    resp = api.post("/api/llm/explain", json={"findings": [resolved, sample_findings(2)[1]], "mode": "blue"})

    assert resp.status_code == 503


def test_all_skipped_returns_200(api):
    resolved = {**sample_findings(1)[0], "status": "code_resolved"}

    resp = api.post("/api/llm/explain", json={"findings": [resolved], "mode": "blue"})

    assert resp.status_code == 200
    assert resp.json()["results"][0]["status"] == "skipped"


def test_environment_is_passed_through(api, fake_vllm):
    fake_vllm.queue("BlueDraft", blue_draft())
    finding = sample_findings(4)[3]  # next 의존성

    resp = api.post("/api/llm/explain", json={"findings": [finding], "mode": "blue", "environment": {"os": "macos"}})

    guide = resp.json()["results"][0]["explanation"]["guide"]
    assert guide["environment"]["os"] == "macos"
    assert {b["os"] for a in guide["actions"] for b in a["commands"]} == {"macos"}


def test_bad_environment_is_rejected(api):
    payload = {"findings": sample_findings(1), "environment": {"os": "windows11"}}
    assert api.post("/api/llm/explain", json=payload).status_code == 422
