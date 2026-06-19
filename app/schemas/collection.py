from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class CollectionTagWriteItem(BaseModel):
    tagId: int | None = None
    name: str | None = None
    categoryName: str | None = None


class CollectionCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    isPrivate: bool = False
    description: str | None = None
    tags: list[CollectionTagWriteItem] = []
    bookIds: list[int] = []


class CollectionUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    isPrivate: bool | None = None
    description: str | None = None
    tags: list[CollectionTagWriteItem] | None = None
    bookIds: list[int] | None = None


class CollectionAddBookRequest(BaseModel):
    bookId: int


class CollectionBookOrderRequest(BaseModel):
    bookIds: list[int]


class CollectionBatchAddBookRequest(BaseModel):
    bookId: int
    collectionIds: list[int]


class TagCategoryItem(BaseModel):
    categoryId: int
    code: str
    name: str
    usageCount: int


class TagCategoryListResponse(BaseModel):
    categories: list[TagCategoryItem]


class TagItem(BaseModel):
    tagId: int
    name: str
    categoryId: int | None = None
    categoryName: str | None = None
    isSystem: bool
    usageCount: int


class TagListResponse(BaseModel):
    tags: list[TagItem]


class CollectionBookItem(BaseModel):
    bookId: int
    title: str
    authors: list[str] = []
    thumbnail: str | None = None
    isbn13: str | None = None
    sortOrder: int


class CollectionListItem(BaseModel):
    collectionId: int
    title: str
    description: str | None = None
    userName: str
    profileImageUrl: str | None = None
    thumbnailCovers: list[str] = []
    bookCount: int
    likeCount: int
    tags: list[str] = []
    hasBook: bool | None = None
    isLiked: bool
    isPrivate: bool = False
    updatedAt: datetime


class CollectionListResponse(BaseModel):
    totalCount: int
    collections: list[CollectionListItem]


class CollectionDetailResponse(BaseModel):
    collectionId: int
    title: str
    description: str | None = None
    userName: str
    profileImageUrl: str | None = None
    thumbnailCovers: list[str] = []
    bookCount: int
    likeCount: int
    tags: list[str] = []
    isMine: bool
    isLiked: bool
    isPrivate: bool
    updatedAt: datetime
    createdAt: datetime
    books: list[CollectionBookItem] = []


class CollectionLikeResponse(BaseModel):
    ok: bool
    isLiked: bool
    likeCount: int


class CollectionSimpleResponse(BaseModel):
    ok: bool
    collectionId: int | None = None


class CollectionIdListResponse(BaseModel):
    ok: bool
    addedCollectionIds: list[int] = []

