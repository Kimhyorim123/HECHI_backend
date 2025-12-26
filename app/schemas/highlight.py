from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class HighlightCreateRequest(BaseModel):
    book_id: int
    page: int
    sentence: str = Field(..., min_length=1)
    is_public: Optional[bool] = False
    memo: Optional[str] = Field(default=None, description="선택 메모")


class HighlightUpdateRequest(BaseModel):
    page: Optional[int] = None
    sentence: str = Field(..., min_length=1)
    is_public: bool = Field(...)
    memo: Optional[str] = None


class HighlightResponse(BaseModel):
    id: int
    user_book_id: int
    page: int
    sentence: str
    is_public: bool
    memo: Optional[str] = None
    created_date: datetime
    model_config = ConfigDict(from_attributes=True)
