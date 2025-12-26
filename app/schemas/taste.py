from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict

ALLOWED_CATEGORIES = ["소설", "시", "에세이", "만화"]
ALLOWED_GENRES = [
    "추리", "코미디", "스릴러/공포", "SF", "판타지", "로맨스", "액션", "철학", "인문", "역사", "과학", "사회/정치", "경제/경영", "예술", "자기계발", "여행", "취미"
]

class TasteOptionsResponse(BaseModel):
    categories: List[str]
    genres: List[str]

class TasteSubmitRequest(BaseModel):
    categories: List[str] = Field(..., min_items=1)
    genres: List[str] = Field(..., min_items=1)

class UserTasteResponse(BaseModel):
    categories: List[str]
    genres: List[str]
    model_config = ConfigDict(from_attributes=True)

class TasteStatusResponse(BaseModel):
    analyzed: bool
    preferences: Optional[UserTasteResponse] = None
