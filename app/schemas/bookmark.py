from datetime import date
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BookmarkCreateRequest(BaseModel):
    book_id: int
    page: int
    memo: Optional[str] = None


class BookmarkResponse(BaseModel):
    id: int
    user_book_id: int
    page: int
    memo: Optional[str] = None
    created_date: date
    model_config = ConfigDict(from_attributes=True)
