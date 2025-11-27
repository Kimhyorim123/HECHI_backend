from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class HighlightCreateRequest(BaseModel):
    book_id: int
    page: int
    sentence: str = Field(..., min_length=1)
    is_public: Optional[bool] = False


class HighlightUpdateRequest(BaseModel):
    sentence: Optional[str] = Field(None, min_length=1)
    is_public: Optional[bool] = None


class HighlightResponse(BaseModel):
    id: int
    user_book_id: int
    page: int
    sentence: str
    is_public: bool
    created_date: date
    model_config = ConfigDict(from_attributes=True)
