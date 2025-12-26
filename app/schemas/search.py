from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict

from .book import BookResponse


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, description="검색 키워드")
    limit: int = Field(20, ge=1, le=50)
    save_history: bool = Field(True, description="개인별 검색 기록 저장 여부")


class AuthorItem(BaseModel):
    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class SearchResult(BaseModel):
    books: List[BookResponse] = []
    authors: List[AuthorItem] = []


class SearchHistoryItem(BaseModel):
    id: int
    query: str
    created_at: str
    model_config = ConfigDict(from_attributes=True)


class BarcodeSearchResponse(BaseModel):
    book: Optional[BookResponse] = None
    already_registered: bool = False
