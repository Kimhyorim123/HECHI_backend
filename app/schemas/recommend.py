from typing import List
from pydantic import BaseModel
from .book import BookResponse


class RecommendResponse(BaseModel):
    items: List[BookResponse]


class CurationItem(BaseModel):
    title: str
    items: List[BookResponse]


class CurationsResponse(BaseModel):
    curations: List[CurationItem]
