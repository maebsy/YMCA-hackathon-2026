from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings

# SQLite는 FastAPI 스레드 여러 개에서 같은 연결을 쓰도록 허용해야 합니다
connect_args = {"check_same_thread": False} if settings.db_url.startswith("sqlite") else {}
engine = create_engine(settings.db_url, connect_args=connect_args, pool_pre_ping=True)


def init_db() -> None:
    # models.py 에 정의한 테이블 중 없는 것만 만듭니다 (해커톤용: 마이그레이션 도구 없이)
    from app import models  # noqa: F401  테이블을 metadata에 등록

    SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
