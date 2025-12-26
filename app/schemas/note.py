from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class NoteCreateRequest(BaseModel):
    book_id: int
    content: str = Field(..., min_length=1)


class NoteUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class NoteResponse(BaseModel):
    id: int
    user_book_id: int
    content: str
    created_date: datetime
    model_config = ConfigDict(from_attributes=True)
