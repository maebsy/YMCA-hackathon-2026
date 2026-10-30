import json
import os
import tempfile
from pathlib import Path

# app 을 import 하기 전에 설정합니다. 저장소 루트 .env 의 실제 DB·LLM 주소로 테스트가 나가지 않게 막습니다
_TMP_DB = Path(tempfile.gettempdir()) / "ymca-hackathon-test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DB.as_posix()}"
if os.environ.get("LLM_LIVE") != "1":
    os.environ["LLM_BASE_URL"] = "http://127.0.0.1:9/v1"
    os.environ["LLM_API_KEY"] = "test-key"

import httpx  # noqa: E402
import pytest  # noqa: E402

from app.llm.client import LLMClient  # noqa: E402
from app.llm.schemas import FindingInput  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"

# 가짜 비밀값. 소스에 통째로 적으면 커밋 훅·gitleaks 가 진짜로 보고 막아서 실행할 때 조립합니다
FAKE_OPENAI_KEY = "sk-" + "proj-" + "x1y2z3" * 6
FAKE_JWT = ".".join(["eyJ" + "hbGciOiJIUzI1NiJ9", "eyJ" + "yb2xlIjoic2VydmljZV9yb2xlIn0", "c2lnbmF0dXJl" + "LXNpZ25hdHVyZQ"])
FAKE_DB_PASSWORD = "hunter" + "2pass"


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def findings() -> list[FindingInput]:
    data = json.loads((FIXTURES / "findings.json").read_text(encoding="utf-8"))
    return [FindingInput.model_validate(item) for item in data]


def blue_draft(**overrides) -> dict:
    draft = {
        "summary": "주문 조회 API가 주소창 값을 SQL 문에 그대로 붙입니다.",
        "why_risky": "누군가 주소창에 특수한 값을 넣으면 다른 손님의 주문 내역까지 볼 수 있습니다.",
        "priority": "now",
        "fix_steps": [
            {"title": "쿼리를 매개변수 방식으로 바꾸기", "detail": "값을 문장에 붙이지 말고 따로 넘깁니다."},
            {"title": "고쳐졌는지 확인하기", "detail": "주소창에 작은따옴표를 넣어도 오류가 나지 않는지 봅니다."},
        ],
        "ai_fix_prompt": "src/app/api/orders/route.ts 9~11줄(규칙 vibe.nextjs.sql-injection-template-literal)의 SQL을 매개변수 쿼리로 바꿔 주세요.",
        "false_positive_suspect": False,
        "false_positive_reason": None,
    }
    draft.update(overrides)
    return draft


def red_review(verdict: str = "pass", **overrides) -> dict:
    review = {
        "verdict": verdict,
        "attack_scenario": "공격자가 주소창의 uid 값에 조건문을 넣어 모든 주문을 한꺼번에 볼 수 있습니다.",
        "issues": [] if verdict == "pass" else ["로그인한 사용자 본인 주문만 보이도록 확인하는 단계가 없습니다."],
    }
    review.update(overrides)
    return review


class FakeVLLM:
    """vLLM 의 /v1/chat/completions·/v1/models 흉내. 응답 스키마 이름(BlueDraft·RedReview)별로 줄 세운 답을 돌려줍니다.

    큐에는 dict(JSON으로 보낼 답), str(본문 그대로), int(그 HTTP 상태), (상태, 본문), Exception(연결 오류)을 넣을 수 있습니다.
    """

    def __init__(self, models: tuple[str, ...] = ("qwen3.8-27b",)) -> None:
        self.models = models
        self.queues: dict[str, list] = {}
        self.requests: list[dict] = []
        self.headers: list[httpx.Headers] = []

    def queue(self, schema_name: str, *items) -> "FakeVLLM":
        self.queues.setdefault(schema_name, []).extend(items)
        return self

    def calls(self, schema_name: str) -> list[dict]:
        return [r for r in self.requests if r["response_format"]["json_schema"]["name"] == schema_name]

    async def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": m} for m in self.models]})
        body = json.loads(request.content)
        self.requests.append(body)
        self.headers.append(request.headers)
        name = body["response_format"]["json_schema"]["name"]
        item = self.queues[name].pop(0)
        if isinstance(item, Exception):
            raise item
        if isinstance(item, int):
            return httpx.Response(item, text="error")
        if isinstance(item, tuple) and isinstance(item[0], int):  # (상태, 본문)
            return httpx.Response(item[0], text=item[1])
        finish = "stop"
        if isinstance(item, tuple):  # (본문, finish_reason)
            item, finish = item
        content = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": content}, "finish_reason": finish}],
                "usage": {"completion_tokens": 50},
            },
        )

    def client(self, **kwargs) -> LLMClient:
        kwargs.setdefault("max_retries", 2)
        kwargs.setdefault("retry_backoff_s", 0)  # 재시도 대기를 테스트에서는 건너뜁니다
        return LLMClient(
            base_url="http://vllm.test/v1",
            model="qwen3.8-27b",
            api_key="test-key",
            transport=httpx.MockTransport(self.handler),
            **kwargs,
        )


@pytest.fixture
def fake_vllm() -> FakeVLLM:
    return FakeVLLM()
