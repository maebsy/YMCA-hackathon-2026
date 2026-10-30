from fastapi import APIRouter
from sqlmodel import col, select

from app.db import SessionDep
from app.models import Item, ItemCreate

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[Item])
def list_items(session: SessionDep):
    return session.exec(select(Item).order_by(col(Item.id).desc())).all()


@router.post("", response_model=Item, status_code=201)
def create_item(body: ItemCreate, session: SessionDep):
    item = Item.model_validate(body)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item
