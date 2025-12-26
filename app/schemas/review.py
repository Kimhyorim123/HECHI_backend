from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict, model_validator


class ReviewCreateRequest(BaseModel):
    book_id: int
    rating: Optional[float] = Field(None, ge=0.5, le=5, multiple_of=0.5)
    content: Optional[str] = Field(None, min_length=1)
    is_spoiler: bool = False

    @model_validator(mode="after")
    def validate_either_rating_or_content(self):
        if self.rating is None and (self.content is None or self.content.strip() == ""):
            raise ValueError("rating 또는 content 중 하나는 반드시 필요합니다")
        return self


class ReviewUpsertRequest(BaseModel):
    book_id: int
    rating: Optional[float] = Field(None, ge=0.5, le=5, multiple_of=0.5, description="별점만 갱신 가능")
    content: Optional[str] = Field(None, min_length=1, description="코멘트는 선택사항")
    is_spoiler: Optional[bool] = Field(default=False, description="스포일러 여부(선택)")

    # Upsert는 기존 리뷰를 수정(필드 초기화 포함)할 수 있어야 하므로
    # rating/content 둘 다 비어있어도 허용한다.


class ReviewUpdateRequest(BaseModel):
    rating: Optional[float] = Field(None, ge=0.5, le=5, multiple_of=0.5)
    content: Optional[str] = Field(None, min_length=1)
    is_spoiler: Optional[bool] = None


class ReviewResponse(BaseModel):
    id: int
    user_book_id: int
    user_id: int
    book_id: int
    rating: Optional[float]
    content: Optional[str]
    like_count: int
    is_spoiler: bool
    created_date: date
    # 책 전체 코멘트 개수 (상세에서 제공; 목록에서는 0 기본)
    book_comment_count: int | None = 0
    # 유저 전체 코멘트 개수
    user_comment_count: int | None = 0
    # 별점 개수 (상세에서 제공)
    rating_count: int = 0
    # 각 리뷰별 댓글 수
    comment_count: int = 0
    # 클라이언트가 내 리뷰 식별을 쉽게 하도록 서버가 제공
    is_my_review: bool = False
    # 현재 로그인한 사용자가 좋아요를 눌렀는지 여부
    is_liked: bool = False
    # 작성자 닉네임
    nickname: str | None = None
    model_config = ConfigDict(from_attributes=True)


class CommentCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=2000)


class CommentResponse(BaseModel):
    id: int
    review_id: int
    user_id: int
    content: str
    created_at: datetime | date | str | None = None
    model_config = ConfigDict(from_attributes=True)


class BookRatingSummary(BaseModel):
    book_id: int
    average_rating: Optional[float]
    review_count: int


class RatingBucket(BaseModel):
    rating: float
    count: int
