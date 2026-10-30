from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 어느 폴더에서 실행해도 저장소 루트의 .env 하나를 읽습니다
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    # 비워 두면 backend/app.db (SQLite), 팀 공용 DB는 Supabase 연결 문자열
    database_url: str = ""

    @property
    def db_url(self) -> str:
        if not self.database_url:
            return f"sqlite:///{(ROOT_DIR / 'backend' / 'app.db').as_posix()}"
        # Supabase가 주는 postgresql:// 주소를 psycopg 3 드라이버로 연결
        return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)


settings = Settings()
