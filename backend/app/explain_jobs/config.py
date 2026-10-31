from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import ROOT_DIR


class JobSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_DIR / ".env", extra="ignore")

    llm_jobs_enabled: bool = False
    # /api/scans 를 Supabase 로그인 사용자에게만 열지 (프론트에 실제 로그인이 붙으면 켭니다, #53)
    scan_require_auth: bool = False
    supabase_url: str = ""
    supabase_publishable_key: str = ""
    llm_job_lease_s: int = Field(default=180, ge=30, le=600)
    llm_job_timeout_s: int = Field(default=900, ge=30, le=3600)
    llm_job_poll_s: float = Field(default=2, ge=0.1, le=30)

    def validate_auth(self) -> None:
        url = urlsplit(self.supabase_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ("", "/")
                or not self.supabase_publishable_key.strip()):
            raise RuntimeError("Configure an HTTPS SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY")


job_settings = JobSettings()
