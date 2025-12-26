from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class BookmarkCreateRequest(BaseModel):
    book_id: int
    page: int
    memo: Optional[str] = Field(default=None, description="선택 메모")


class BookmarkResponse(BaseModel):
    id: int
    user_book_id: int
    page: int
    memo: Optional[str] = None
    created_date: datetime
    model_config = ConfigDict(from_attributes=True)


class BookmarkUpdateRequest(BaseModel):
    page: Optional[int] = Field(default=None, description="업데이트할 페이지(선택)")
    memo: Optional[str] = Field(default=None, description="업데이트할 메모(선택)")
