from typing import List, Optional

from pydantic import BaseModel, Field

from .book import BookResponse


class BookLibraryItem(BaseModel):
    book: BookResponse
    status: str = Field(..., description="UserBook.status 또는 wishlist 지정")
    added_at: Optional[str] = Field(None, description="보관함에 담긴 시점 (user_books.created_at / wishlist.created_at)")
    started_at: Optional[str] = Field(None, description="읽는 중 상태 진입 시각 (UserBook.started_at)")
    completed_at: Optional[str] = Field(None, description="완독 상태 진입 시각 (UserBook.completed_at)")
    wishlist_at: Optional[str] = Field(None, description="위시리스트 추가 시각 (Wishlist.wishlist_at)")
    my_rating: Optional[float] = Field(None, description="사용자가 준 별점")
    avg_rating: Optional[float] = Field(None, description="전체 평균 별점")
    review_count: int = Field(0, description="리뷰 수")
    progress_percent: Optional[float] = Field(None, description="읽은 페이지 기반 진행률 (0~100)")
    current_page: Optional[int] = Field(
        None,
        description="현재 페이지(최근 이벤트의 page → 최근 세션 end_page → UserPage.max(end_page) 순으로 추론)",
    )
    total_reading_seconds: Optional[int] = Field(None, description="책별 누적 독서 시간(초)")


class LibraryResponse(BaseModel):
    total: int
    items: List[BookLibraryItem]
