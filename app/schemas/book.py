from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict


class BookCreateRequest(BaseModel):
    isbn: Optional[str] = Field(None, max_length=13)
    title: str
    publisher: Optional[str] = None
    published_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    language: Optional[str] = None
    category: Optional[str] = Field(None, description="원본 카테고리 문자열 예: 'Fiction / Romance / Contemporary'")
    total_pages: Optional[int] = None
    authors: List[str] = []


class BookResponse(BaseModel):
    id: int
    isbn: Optional[str]
    title: str
    publisher: Optional[str]
    published_date: Optional[str]
    language: Optional[str]
    category: Optional[str]
    total_pages: Optional[int]
    model_config = ConfigDict(from_attributes=True)


class BookDetailResponse(BookResponse):
    authors: List[str] = []
    average_rating: Optional[float] = None
    review_count: int = 0


class BookSearchResponse(BaseModel):
    items: List[BookResponse]
