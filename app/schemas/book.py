from typing import List, Optional

from pydantic import BaseModel, Field, ConfigDict
from typing import Dict


class BookCreateRequest(BaseModel):
    isbn: Optional[str] = Field(None, max_length=13)
    title: str
    publisher: Optional[str] = None
    published_date: Optional[str] = Field(None, description="YYYY-MM-DD")
    language: Optional[str] = None
    category: Optional[str] = Field(None, description="원본 카테고리 문자열 예: 'Fiction / Romance / Contemporary'")
    total_pages: Optional[int] = None
    authors: List[str] = []
    thumbnail: Optional[str] = None
    small_thumbnail: Optional[str] = None
    google_rating: Optional[float] = None
    google_ratings_count: Optional[int] = None
    description: Optional[str] = None


class BookResponse(BaseModel):
    id: int
    isbn: Optional[str]
    title: str
    publisher: Optional[str]
    published_date: Optional[str]
    language: Optional[str]
    category: Optional[str]
    total_pages: Optional[int]
    thumbnail: Optional[str] = None
    small_thumbnail: Optional[str] = None
    google_rating: Optional[float] = None
    google_ratings_count: Optional[int] = None
    description: Optional[str] = None
    # 집계 필드(옵션): 평균 별점과 리뷰 수
    average_rating: Optional[float] = None
    review_count: int = 0
    authors: List[str] = []
    categories: List[str] = []
    model_config = ConfigDict(from_attributes=True)


class BookDetailResponse(BookResponse):
    average_rating: Optional[float] = None
    review_count: int = 0
    rating_histogram: Dict[str, int] = {}
    description: Optional[str] = None


class BookSearchResponse(BaseModel):
    items: List[BookResponse]


class GoogleImportRequest(BaseModel):
    isbn: Optional[str] = Field(None, description="ISBN-10 또는 ISBN-13 한 개")
    query: Optional[str] = Field(None, description="일반 검색어 (isbn 없을 때 사용)")

    @property
    def mode(self) -> str:
        return "isbn" if self.isbn else "query"

class GoogleImportResult(BaseModel):
    created: List[BookResponse] = []
    skipped: List[str] = []  # ISBN 이미 존재 등
    updated: List[BookResponse] = []


class GoogleQueryImportRequest(BaseModel):
    query: str = Field(..., description="검색어")
    pages: int = Field(1, ge=1, le=50, description="가져올 페이지 수 (startIndex 기반)")
    page_size: int = Field(20, ge=1, le=40, description="Google API maxResults (최대 40)")
    start_index: int = Field(0, ge=0, description="시작 startIndex")
    language: Optional[str] = Field(None, description="언어 코드 필터 (예: 'ko')")
    max_create: Optional[int] = Field(None, description="생성할 최대 도서 수 (초과 시 중단)")
    exclude_no_isbn: bool = Field(True, description="ISBN 없는 항목은 건너뛰기")
