from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, ConfigDict


class ReadingSessionStartRequest(BaseModel):
    book_id: int = Field(..., description="읽는 책 ID")
    start_page: Optional[int] = Field(
        None,
        description=(
            "시작 페이지 (미제공 시 서버가 최근 읽은 페이지로 자동 설정: "
            "최근 이벤트 페이지→최근 세션 end_page→없으면 1)"
        ),
    )


class ReadingEventCreateRequest(BaseModel):
    event_type: str = Field(..., description="이벤트 타입: START, PAGE_TURN, PAUSE, RESUME, END")
    page: Optional[int] = Field(None, description="해당 이벤트에 관련된 페이지")
    occurred_at: Optional[datetime] = Field(
        None, description="이벤트 발생 시각(미제공 시 서버 시간)"
    )


class ReadingSessionEndRequest(BaseModel):
    end_page: Optional[int] = Field(None, description="종료 페이지")
    total_seconds: Optional[int] = Field(None, description="총 독서 시간(초)")


class ReadingEventResponse(BaseModel):
    id: int
    event_type: str
    page: Optional[int]
    occurred_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReadingSessionResponse(BaseModel):
    id: int
    user_id: int
    book_id: int
    start_time: datetime
    end_time: Optional[datetime]
    start_page: Optional[int]
    end_page: Optional[int]
    total_seconds: Optional[int]
    events: List[ReadingEventResponse] = []
    model_config = ConfigDict(from_attributes=True)
