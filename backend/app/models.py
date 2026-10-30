from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


# 연결 확인용 예시 테이블입니다. 서비스 테이블을 만들면 Item과 routers/items.py는 지우세요.
class ItemCreate(SQLModel):
    name: str = Field(min_length=1, max_length=200)


class Item(ItemCreate, table=True):
    id: int | None = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
