from datetime import date
from pydantic import BaseModel, Field, ConfigDict


class NoteCreateRequest(BaseModel):
    book_id: int
    page: int
    content: str = Field(..., min_length=1)


class NoteUpdateRequest(BaseModel):
    content: str = Field(..., min_length=1)


class NoteResponse(BaseModel):
    id: int
    user_book_id: int
    page: int
    content: str
    created_date: date
    model_config = ConfigDict(from_attributes=True)
