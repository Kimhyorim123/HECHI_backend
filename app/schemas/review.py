from datetime import date
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


class ReviewCreateRequest(BaseModel):
    book_id: int
    rating: int = Field(..., ge=1, le=5)
    content: str = Field(..., min_length=1)
    is_spoiler: bool = False


class ReviewUpdateRequest(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    content: Optional[str] = Field(None, min_length=1)
    is_spoiler: Optional[bool] = None


class ReviewResponse(BaseModel):
    id: int
    user_book_id: int
    user_id: int
    book_id: int
    rating: int
    content: str
    like_count: int
    is_spoiler: bool
    created_date: date
    model_config = ConfigDict(from_attributes=True)


class BookRatingSummary(BaseModel):
    book_id: int
    average_rating: Optional[float]
    review_count: int
