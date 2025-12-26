from typing import List, Optional
from pydantic import BaseModel, Field

class CalendarBookItem(BaseModel):
    book_id: int
    title: str
    thumbnail: Optional[str] = None
    authors: list[str] = []
    rating: Optional[float] = None

class CalendarDay(BaseModel):
    date: str  # YYYY-MM-DD
    items: List[CalendarBookItem]

class CalendarMonthResponse(BaseModel):
    year: int
    month: int
    total_read_count: int
    top_genre: Optional[str] = Field(default=None, description="그 달에 가장 많이 읽은 장르")
    days: List[CalendarDay]
