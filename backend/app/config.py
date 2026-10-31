from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 어느 폴더에서 실행해도 저장소 루트의 .env 하나를 읽습니다
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # 비워 두면 backend/app.db (SQLite), 팀 공용 DB는 Supabase 연결 문자열
    database_url: str = ""

    # LLM 서버 (OpenAI 호환). GPU 서버의 vLLM을 SSH 터널로 연 8001 포트가 기본입니다
    llm_base_url: str = "http://localhost:8001/v1"
    llm_api_key: str = ""
    llm_model: str = "qwen3.8-27b"
    llm_timeout_s: float = 300.0
    # L4 한 장은 동시 8개에서 처리량이 포화됩니다. 더 보내면 지연만 늘어납니다
    llm_max_concurrency: int = 8
    # 공개 시연용 임시 해석 대기열(LLM_JOBS_ENABLED=false일 때)의 동시 실행 수와 대기 상한.
    # 해석 1건(Red–Blue)은 모델을 한 번에 하나씩 부르므로, 동시 실행 6이면 LLM_MAX_CONCURRENCY 8 안에서 다른 호출 여유를 남깁니다.
    # 브라우저 한 명은 동시에 2건(frontend LLM_PARALLEL)만 보내므로 세 명이 함께 써도 기다리기만 하고 거절되지 않습니다.
    llm_preview_running: int = Field(default=6, ge=1, le=32)
    llm_preview_capacity: int = Field(default=30, ge=1, le=200)
    # Red 검토에서 막히면 Blue가 다시 쓰는 최대 횟수 (아키텍처: 최대 2회)
    llm_red_blue_max_rewrites: int = 2
    # Red의 생각 깊이 (low·medium·high). 깊을수록 우회 경로를 더 찾지만 L4에서 느려집니다
    llm_red_reasoning_effort: str = "low"
    # 문맥 분석을 LLM 으로 할지 (끄면 규칙 신호로만 판단해 호출 1회를 아낌)
    llm_analyze_context: bool = True
    # 위험도 해석에 CISA KEV·FIRST EPSS 를 조회할지 (인터넷이 안 되면 "모름"으로 진행)
    llm_threat_intel: bool = True

    @field_validator("llm_base_url", "llm_model", "llm_red_reasoning_effort", "llm_preview_running", "llm_preview_capacity", mode="before")
    @classmethod
    def _empty_means_default(cls, value, info):
        # .env 에 `LLM_MODEL=` 처럼 빈 값으로 남아 있으면 기본값을 씁니다
        if value in ("", None):
            return cls.model_fields[info.field_name].default
        return value

    @property
    def db_url(self) -> str:
        if not self.database_url:
            return f"sqlite:///{(ROOT_DIR / 'backend' / 'app.db').as_posix()}"
        # Supabase가 주는 postgresql:// 주소를 psycopg 3 드라이버로 연결
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


settings = Settings()
