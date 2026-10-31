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
    # 검사할 수 있는 GitHub 소유자 (쉼표 목록, 대소문자 무시). 비우면 제한 없음 (로컬 개발용, #67)
    scan_allowed_owners: str = ""
    # 위 제한을 받지 않는 관리자 Supabase 사용자 ID (쉼표 목록). 로그인을 켠 경우에만 의미가 있습니다
    scan_admin_user_ids: str = ""

    def allowed_owners(self) -> set[str]:
        return {o.strip().lower() for o in self.scan_allowed_owners.split(",") if o.strip()}

    def admin_user_ids(self) -> set[str]:
        return {u.strip().lower() for u in self.scan_admin_user_ids.split(",") if u.strip()}

    def validate_auth(self) -> None:
        url = urlsplit(self.supabase_url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ("", "/")
                or not self.supabase_publishable_key.strip()):
            raise RuntimeError("Configure an HTTPS SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY")


job_settings = JobSettings()
