from app.config import Settings


def test_empty_llm_values_fall_back_to_defaults():
    # .env.example 을 복사만 하고 값을 비워 둔 팀원도 기본값으로 동작해야 합니다
    s = Settings(_env_file=None, llm_base_url="", llm_model="", llm_red_reasoning_effort="")

    assert s.llm_base_url == "http://localhost:8001/v1"
    assert s.llm_model == "qwen3.8-27b"
    assert s.llm_red_reasoning_effort == "low"


def test_explicit_llm_values_win():
    s = Settings(_env_file=None, llm_model="qwen3.5-9b", llm_red_reasoning_effort="medium")

    assert s.llm_model == "qwen3.5-9b"
    assert s.llm_red_reasoning_effort == "medium"
