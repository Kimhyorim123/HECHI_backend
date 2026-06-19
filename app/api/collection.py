from __future__ import annotations

from datetime import datetime
import re
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import (
    Author,
    Book,
    BookAuthor,
    Collection,
    CollectionBook,
    CollectionLike,
    CollectionTag,
    CollectionTagCategoryType,
    Tag,
    TagCategory,
    NotificationType,
    User,
)
from app.services.notify import create_notification
from app.schemas.collection import (
    CollectionAddBookRequest,
    CollectionBatchAddBookRequest,
    CollectionBookItem,
    CollectionBookOrderRequest,
    CollectionCreateRequest,
    CollectionDetailResponse,
    CollectionIdListResponse,
    CollectionLikeResponse,
    CollectionListItem,
    CollectionListResponse,
    CollectionSimpleResponse,
    CollectionUpdateRequest,
    TagCategoryItem,
    TagCategoryListResponse,
    TagItem,
    TagListResponse,
)


router = APIRouter(tags=["collections"])


SYSTEM_TAGS: list[tuple[str, str, list[str]]] = [
    ("EMOTION", "감정", ["힐링", "감동", "눈물나는", "위로되는", "여운이남는", "따뜻한", "다정한", "먹먹한", "쓸쓸한", "벅찬", "희망적인", "설레는", "로맨틱한"]),
    ("MOOD", "분위기", ["잔잔한", "몽환적인", "서늘한", "어두운", "긴장감있는", "몰입감있는", "속도감있는", "유쾌한", "발랄한"]),
    ("SITUATION", "상황", ["잠들기전에읽는", "주말에읽기좋은", "카페에서읽기좋은", "여행할때읽기좋은", "출퇴근에읽기좋은"]),
    ("READING_STYLE", "독서 스타일", ["가볍게읽기좋은", "한번에읽는", "천천히읽는", "인생책", "페이지터너", "다시읽고싶은", "곱씹게되는"]),
    ("DIFFICULTY", "난이도", ["초보추천", "생각이많아지는", "지식이쌓이는", "시야가넓어지는", "통찰을주는", "현실적인", "철학적인", "사회적인"]),
    ("GENRE", "장르", ["소설", "시", "에세이", "만화", "추리", "스릴러/공포", "SF", "판타지", "로맨스", "액션", "역사", "과학", "인문", "철학", "사회/정치", "경제/경영", "자기계발", "예술", "여행", "취미", "코미디"]),
]

ALLOWED_COLLECTION_SORTS = {"like", "latest"}


def _utcnow() -> datetime:
    return datetime.utcnow()


def _default_profile_thumbnail(name: str | None) -> str:
    safe_name = quote(name or 'BookStopper')
    return f"https://ui-avatars.com/api/?name={safe_name}&background=EFE4D2&color=5B4636&size=256"


def _notify_collection_reaction(
    db: Session,
    *,
    collection: Collection,
    actor: User,
    body: str,
    event_kind: str,
) -> None:
    if collection.user_id == actor.id:
        return
    payload = {
        'collectionId': collection.id,
        'actorId': actor.id,
        'actorName': actor.nickname,
        'eventKind': event_kind,
    }
    create_notification(
        db,
        collection.user_id,
        title='컬렉션 반응 알림',
        body=body,
        notification_type=NotificationType.COLLECTION_REACTION,
        target_info=payload,
        thumbnail_url=_default_profile_thumbnail(actor.nickname),
        send_push=True,
        data=payload,
    )


def _normalize_tag_name(name: str) -> str:
    s = (name or "").strip()
    s = s.lstrip("#@").strip()
    return re.sub(r"\s+", "", s)


def _ensure_system_tags(db: Session) -> None:
    existing_categories = {row.code.value: row for row in db.query(TagCategory).all()}
    changed = False
    for code, name, tags in SYSTEM_TAGS:
        category = existing_categories.get(code)
        if not category:
            category = TagCategory(code=CollectionTagCategoryType(code), name=name)
            db.add(category)
            db.flush()
            existing_categories[code] = category
            changed = True
        elif category.name != name:
            category.name = name
            changed = True
        for tag_name in tags:
            normalized = _normalize_tag_name(tag_name).lower()
            tag = db.query(Tag).filter(Tag.normalized_name == normalized).first()
            if not tag:
                db.add(
                    Tag(
                        category_id=category.id,
                        name=tag_name,
                        normalized_name=normalized,
                        is_system=True,
                    )
                )
                changed = True
            elif tag.category_id != category.id or not tag.is_system:
                tag.category_id = category.id
                tag.is_system = True
                changed = True
    if changed:
        db.commit()


def _touch_collection(collection: Collection) -> None:
    collection.updated_at = _utcnow()


def _get_collection_or_404(db: Session, collection_id: int) -> Collection:
    collection = db.query(Collection).filter(Collection.id == collection_id).first()
    if not collection:
        raise HTTPException(status_code=404, detail="컬렉션을 찾을 수 없습니다")
    return collection


def _ensure_collection_owner(collection: Collection, user: User) -> None:
    if collection.user_id != user.id:
        raise HTTPException(status_code=403, detail="본인 컬렉션만 수정할 수 있습니다")


def _ensure_collection_readable(collection: Collection, user: User) -> None:
    if collection.is_private and collection.user_id != user.id:
        raise HTTPException(status_code=404, detail="컬렉션을 찾을 수 없습니다")


def _parse_tag_ids(tag_ids: str | None) -> list[int]:
    if not tag_ids:
        return []
    out: list[int] = []
    for token in tag_ids.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            out.append(int(token))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="tagIds 형식이 올바르지 않습니다") from exc
    return out


def _resolve_tag_inputs(db: Session, current_user: User, items) -> list[Tag]:
    resolved: list[Tag] = []
    seen: set[int] = set()
    for item in items or []:
        tag = None
        if item.tagId is not None:
            tag = db.query(Tag).filter(Tag.id == item.tagId).first()
            if not tag:
                raise HTTPException(status_code=404, detail=f"태그를 찾을 수 없습니다: {item.tagId}")
        elif item.name:
            normalized = _normalize_tag_name(item.name).lower()
            if not normalized:
                continue
            tag = db.query(Tag).filter(Tag.normalized_name == normalized).first()
            if not tag:
                category = None
                if item.categoryName:
                    category = db.query(TagCategory).filter(TagCategory.name == item.categoryName.strip()).first()
                display_name = _normalize_tag_name(item.name)
                tag = Tag(
                    category_id=category.id if category else None,
                    name=display_name,
                    normalized_name=normalized,
                    is_system=False,
                    created_by_user_id=current_user.id,
                )
                db.add(tag)
                db.flush()
        if tag and tag.id not in seen:
            resolved.append(tag)
            seen.add(tag.id)
    return resolved


def _sync_collection_tags(db: Session, collection: Collection, tags: list[Tag]) -> None:
    existing = {link.tag_id: link for link in db.query(CollectionTag).filter(CollectionTag.collection_id == collection.id).all()}
    desired_ids = {tag.id for tag in tags}
    for tag_id, link in existing.items():
        if tag_id not in desired_ids:
            db.delete(link)
    for tag in tags:
        if tag.id not in existing:
            db.add(CollectionTag(collection_id=collection.id, tag_id=tag.id))


def _book_title_matches_query(book: Book, query: str) -> bool:
    return query.lower() in (book.title or "").lower()


def _collection_tag_names(db: Session, collection_id: int) -> list[str]:
    rows = (
        db.query(Tag.name)
        .join(CollectionTag, CollectionTag.tag_id == Tag.id)
        .filter(CollectionTag.collection_id == collection_id)
        .order_by(Tag.name.asc())
        .all()
    )
    return [name for (name,) in rows]


def _collection_thumbnail_covers(db: Session, collection_id: int) -> list[str]:
    rows = (
        db.query(Book.thumbnail)
        .join(CollectionBook, CollectionBook.book_id == Book.id)
        .filter(CollectionBook.collection_id == collection_id, Book.thumbnail.isnot(None))
        .order_by(CollectionBook.sort_order.asc(), CollectionBook.id.asc())
        .limit(5)
        .all()
    )
    return [thumb for (thumb,) in rows if thumb]


def _collection_book_count(db: Session, collection_id: int) -> int:
    return (
        db.query(func.count(CollectionBook.id))
        .filter(CollectionBook.collection_id == collection_id)
        .scalar()
        or 0
    )


def _collection_like_count(db: Session, collection_id: int) -> int:
    return (
        db.query(func.count(CollectionLike.id))
        .filter(CollectionLike.collection_id == collection_id)
        .scalar()
        or 0
    )


def _is_collection_liked(db: Session, collection_id: int, user_id: int) -> bool:
    return db.query(CollectionLike.id).filter(CollectionLike.collection_id == collection_id, CollectionLike.user_id == user_id).first() is not None


def _serialize_collection_list_item(db: Session, collection: Collection, current_user: User, has_book: bool | None = None) -> CollectionListItem:
    return CollectionListItem(
        collectionId=collection.id,
        title=collection.title,
        description=collection.description,
        userName=collection.user.nickname if collection.user else "",
        profileImageUrl=collection.user.profile_image_url if collection.user else None,
        thumbnailCovers=_collection_thumbnail_covers(db, collection.id),
        bookCount=_collection_book_count(db, collection.id),
        likeCount=_collection_like_count(db, collection.id),
        tags=_collection_tag_names(db, collection.id),
        hasBook=has_book,
        isLiked=_is_collection_liked(db, collection.id, current_user.id),
        isPrivate=bool(collection.is_private),
        updatedAt=collection.updated_at,
    )


def _serialize_collection_detail(db: Session, collection: Collection, current_user: User) -> CollectionDetailResponse:
    books = (
        db.query(CollectionBook)
        .filter(CollectionBook.collection_id == collection.id)
        .order_by(CollectionBook.sort_order.asc(), CollectionBook.id.asc())
        .all()
    )
    book_items: list[CollectionBookItem] = []
    for item in books:
        author_rows = (
            db.query(Author.name)
            .join(BookAuthor, BookAuthor.author_id == Author.id)
            .filter(BookAuthor.book_id == item.book_id)
            .order_by(Author.name.asc())
            .all()
        )
        book_items.append(
            CollectionBookItem(
                bookId=item.book.id,
                title=item.book.title,
                authors=[name for (name,) in author_rows],
                thumbnail=item.book.thumbnail,
                isbn13=item.book.isbn_13,
                sortOrder=item.sort_order,
            )
        )
    return CollectionDetailResponse(
        collectionId=collection.id,
        title=collection.title,
        description=collection.description,
        userName=collection.user.nickname if collection.user else "",
        profileImageUrl=collection.user.profile_image_url if collection.user else None,
        thumbnailCovers=_collection_thumbnail_covers(db, collection.id),
        bookCount=_collection_book_count(db, collection.id),
        likeCount=_collection_like_count(db, collection.id),
        tags=_collection_tag_names(db, collection.id),
        isMine=collection.user_id == current_user.id,
        isLiked=_is_collection_liked(db, collection.id, current_user.id),
        isPrivate=bool(collection.is_private),
        updatedAt=collection.updated_at,
        createdAt=collection.created_at,
        books=book_items,
    )


def _apply_book_ids(db: Session, collection: Collection, book_ids: list[int]) -> None:
    unique_ids: list[int] = []
    seen: set[int] = set()
    for book_id in book_ids:
        if book_id in seen:
            raise HTTPException(status_code=400, detail="같은 책은 한 컬렉션에 중복 추가할 수 없습니다")
        seen.add(book_id)
        unique_ids.append(book_id)
    if unique_ids:
        found = {row.id for row in db.query(Book.id).filter(Book.id.in_(unique_ids)).all()}
        missing = [book_id for book_id in unique_ids if book_id not in found]
        if missing:
            raise HTTPException(status_code=404, detail=f"책을 찾을 수 없습니다: {missing[0]}")
    existing_links = db.query(CollectionBook).filter(CollectionBook.collection_id == collection.id).all()
    existing_by_book = {link.book_id: link for link in existing_links}
    desired = set(unique_ids)
    for link in existing_links:
        if link.book_id not in desired:
            db.delete(link)
    for idx, book_id in enumerate(unique_ids):
        link = existing_by_book.get(book_id)
        if link:
            link.sort_order = idx
        else:
            db.add(CollectionBook(collection_id=collection.id, book_id=book_id, sort_order=idx))

def _insert_book_at_front(db: Session, collection_id: int, book_id: int) -> None:
    links = db.query(CollectionBook).filter(CollectionBook.collection_id == collection_id).all()
    for link in links:
        link.sort_order += 1
    db.add(CollectionBook(collection_id=collection_id, book_id=book_id, sort_order=0))


@router.get("/tags/categories", response_model=TagCategoryListResponse, summary="태그 카테고리 조회")
def get_tag_categories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_system_tags(db)
    usage_rows = (
        db.query(Tag.category_id, func.count(CollectionTag.id))
        .join(CollectionTag, CollectionTag.tag_id == Tag.id)
        .group_by(Tag.category_id)
        .all()
    )
    usage_map = {category_id: count for category_id, count in usage_rows}
    rows = db.query(TagCategory).all()
    rows.sort(key=lambda row: (-(usage_map.get(row.id, 0)), row.name))
    return TagCategoryListResponse(
        categories=[
            TagCategoryItem(
                categoryId=row.id,
                code=row.code.value,
                name=row.name,
                usageCount=int(usage_map.get(row.id, 0)),
            )
            for row in rows
        ]
    )


@router.get("/tags", response_model=TagListResponse, summary="태그 목록/자동완성 조회")
def get_tags(
    category: str | None = Query(None),
    query: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_system_tags(db)
    usage_subq = (
        db.query(CollectionTag.tag_id.label("tag_id"), func.count(CollectionTag.id).label("usage_count"))
        .group_by(CollectionTag.tag_id)
        .subquery()
    )
    q = db.query(Tag, func.coalesce(usage_subq.c.usage_count, 0)).outerjoin(usage_subq, usage_subq.c.tag_id == Tag.id)
    if category:
        q = q.join(TagCategory, TagCategory.id == Tag.category_id).filter(TagCategory.name == category.strip())
    if query:
        token = _normalize_tag_name(query)
        q = q.filter(Tag.name.ilike(f"%{token}%"))
    rows = q.order_by(func.coalesce(usage_subq.c.usage_count, 0).desc(), Tag.name.asc()).limit(limit).all()
    return TagListResponse(
        tags=[
            TagItem(
                tagId=tag.id,
                name=tag.name,
                categoryId=tag.category_id,
                categoryName=tag.category.name if tag.category else None,
                isSystem=bool(tag.is_system),
                usageCount=int(usage_count or 0),
            )
            for tag, usage_count in rows
        ]
    )


@router.post("/collections", response_model=CollectionSimpleResponse, status_code=status.HTTP_201_CREATED, summary="컬렉션 생성")
def create_collection(
    payload: CollectionCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_system_tags(db)
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title은 비어 있을 수 없습니다")
    collection = Collection(
        user_id=current_user.id,
        title=title,
        description=payload.description,
        is_private=bool(payload.isPrivate),
    )
    db.add(collection)
    db.flush()
    tags = _resolve_tag_inputs(db, current_user, payload.tags)
    _sync_collection_tags(db, collection, tags)
    _apply_book_ids(db, collection, payload.bookIds)
    _touch_collection(collection)
    db.commit()
    return CollectionSimpleResponse(ok=True, collectionId=collection.id)


@router.get("/collections", response_model=CollectionListResponse, summary="공개 컬렉션 목록/검색")
def list_public_collections(
    query: str | None = Query(None),
    tagIds: str | None = Query(None),
    sort: str = Query("like"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_system_tags(db)
    if sort not in ALLOWED_COLLECTION_SORTS:
        raise HTTPException(status_code=400, detail="sort는 like 또는 latest만 가능합니다")
    requested_tag_ids = _parse_tag_ids(tagIds)
    collections = db.query(Collection).filter(Collection.is_private.is_(False)).all()
    q = (query or "").strip()
    tag_query = None
    if q.startswith("@"):
        tag_query = _normalize_tag_name(q[1:]).lower()
    elif q:
        text_query = q.lower()
        filtered = []
        for collection in collections:
            title_match = text_query in (collection.title or "").lower()
            book_match = any(_book_title_matches_query(link.book, q) for link in collection.books)
            if title_match or book_match:
                filtered.append(collection)
        collections = filtered
    if tag_query is not None:
        filtered = []
        for collection in collections:
            names = [_normalize_tag_name(tag).lower() for tag in _collection_tag_names(db, collection.id)]
            if any(tag_query in name for name in names):
                filtered.append(collection)
        collections = filtered
    if requested_tag_ids:
        requested = set(requested_tag_ids)
        filtered = []
        for collection in collections:
            current_tag_ids = {row.tag_id for row in db.query(CollectionTag.tag_id).filter(CollectionTag.collection_id == collection.id).all()}
            if requested.issubset(current_tag_ids):
                filtered.append(collection)
        collections = filtered
    if sort == "latest":
        collections.sort(key=lambda row: (row.updated_at, row.id), reverse=True)
    else:
        collections.sort(key=lambda row: (_collection_like_count(db, row.id), row.updated_at, row.id), reverse=True)
    collections = collections[:limit]
    return CollectionListResponse(
        totalCount=len(collections),
        collections=[_serialize_collection_list_item(db, row, current_user) for row in collections],
    )


@router.get("/collections/{collection_id}", response_model=CollectionDetailResponse, summary="컬렉션 상세 조회")
def get_collection_detail(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = _get_collection_or_404(db, collection_id)
    _ensure_collection_readable(collection, current_user)
    return _serialize_collection_detail(db, collection, current_user)


@router.put("/collections/{collection_id}", response_model=CollectionSimpleResponse, summary="컬렉션 수정")
def update_collection(
    collection_id: int,
    payload: CollectionUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_system_tags(db)
    collection = _get_collection_or_404(db, collection_id)
    _ensure_collection_owner(collection, current_user)
    payload_data = payload.model_dump(exclude_unset=True)
    if "title" in payload_data:
        title = (payload_data.get("title") or "").strip()
        if not title:
            raise HTTPException(status_code=400, detail="title은 비어 있을 수 없습니다")
        collection.title = title
    if "description" in payload_data:
        collection.description = payload_data.get("description")
    if "isPrivate" in payload_data:
        collection.is_private = bool(payload_data.get("isPrivate"))
    if "tags" in payload_data:
        tags = _resolve_tag_inputs(db, current_user, payload.tags or [])
        _sync_collection_tags(db, collection, tags)
    if "bookIds" in payload_data:
        _apply_book_ids(db, collection, payload.bookIds or [])
    _touch_collection(collection)
    db.commit()
    return CollectionSimpleResponse(ok=True, collectionId=collection.id)


@router.delete("/collections/{collection_id}", response_model=CollectionSimpleResponse, summary="컬렉션 삭제")
def delete_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = _get_collection_or_404(db, collection_id)
    _ensure_collection_owner(collection, current_user)
    db.delete(collection)
    db.commit()
    return CollectionSimpleResponse(ok=True, collectionId=collection_id)


@router.get("/users/me/collections", response_model=CollectionListResponse, summary="내 컬렉션 목록")
def my_collections(
    bookId: int | None = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Collection)
        .filter(Collection.user_id == current_user.id)
        .order_by(Collection.updated_at.desc(), Collection.id.desc())
        .all()
    )
    items = []
    for row in rows:
        has_book = None
        if bookId is not None:
            has_book = db.query(CollectionBook.id).filter(CollectionBook.collection_id == row.id, CollectionBook.book_id == bookId).first() is not None
        items.append(_serialize_collection_list_item(db, row, current_user, has_book=has_book))
    return CollectionListResponse(totalCount=len(items), collections=items)


@router.get("/users/me/likes/collections", response_model=CollectionListResponse, summary="좋아요한 컬렉션")
def my_liked_collections(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Collection)
        .join(CollectionLike, CollectionLike.collection_id == Collection.id)
        .filter(CollectionLike.user_id == current_user.id, Collection.is_private.is_(False))
        .order_by(CollectionLike.created_at.desc(), Collection.id.desc())
        .all()
    )
    return CollectionListResponse(
        totalCount=len(rows),
        collections=[_serialize_collection_list_item(db, row, current_user) for row in rows],
    )


@router.get("/books/{book_id}/collections", response_model=CollectionListResponse, summary="도서가 담긴 공개 컬렉션 목록")
def collections_by_book(
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Collection)
        .join(CollectionBook, CollectionBook.collection_id == Collection.id)
        .filter(CollectionBook.book_id == book_id, Collection.is_private.is_(False))
        .all()
    )
    rows.sort(key=lambda row: (_collection_like_count(db, row.id), row.updated_at, row.id), reverse=True)
    return CollectionListResponse(
        totalCount=len(rows),
        collections=[_serialize_collection_list_item(db, row, current_user) for row in rows],
    )


@router.post("/collections/{collection_id}/books", response_model=CollectionSimpleResponse, summary="컬렉션에 도서 추가")
def add_book_to_collection(
    collection_id: int,
    payload: CollectionAddBookRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = _get_collection_or_404(db, collection_id)
    _ensure_collection_owner(collection, current_user)
    if db.query(CollectionBook.id).filter(CollectionBook.collection_id == collection_id, CollectionBook.book_id == payload.bookId).first():
        raise HTTPException(status_code=400, detail="같은 책은 한 컬렉션에 중복 추가할 수 없습니다")
    book = db.query(Book).filter(Book.id == payload.bookId).first()
    if not book:
        raise HTTPException(status_code=404, detail="책을 찾을 수 없습니다")
    _insert_book_at_front(db, collection_id, payload.bookId)
    _touch_collection(collection)
    db.commit()
    return CollectionSimpleResponse(ok=True, collectionId=collection_id)


@router.delete("/collections/{collection_id}/books/{book_id}", response_model=CollectionSimpleResponse, summary="컬렉션에서 도서 삭제")
def remove_book_from_collection(
    collection_id: int,
    book_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = _get_collection_or_404(db, collection_id)
    _ensure_collection_owner(collection, current_user)
    link = db.query(CollectionBook).filter(CollectionBook.collection_id == collection_id, CollectionBook.book_id == book_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="컬렉션에 포함된 책을 찾을 수 없습니다")
    db.delete(link)
    db.flush()
    remaining = (
        db.query(CollectionBook)
        .filter(CollectionBook.collection_id == collection_id)
        .order_by(CollectionBook.sort_order.asc(), CollectionBook.id.asc())
        .all()
    )
    for idx, item in enumerate(remaining):
        item.sort_order = idx
    _touch_collection(collection)
    db.commit()
    return CollectionSimpleResponse(ok=True, collectionId=collection_id)


@router.put("/collections/{collection_id}/books/order", response_model=CollectionSimpleResponse, summary="컬렉션 도서 순서 변경")
def reorder_collection_books(
    collection_id: int,
    payload: CollectionBookOrderRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = _get_collection_or_404(db, collection_id)
    _ensure_collection_owner(collection, current_user)
    links = db.query(CollectionBook).filter(CollectionBook.collection_id == collection_id).all()
    existing_ids = [link.book_id for link in links]
    if sorted(existing_ids) != sorted(payload.bookIds):
        raise HTTPException(status_code=400, detail="현재 컬렉션에 포함된 책 목록과 순서 변경 요청이 일치하지 않습니다")
    link_map = {link.book_id: link for link in links}
    for idx, book_id in enumerate(payload.bookIds):
        link_map[book_id].sort_order = idx
    _touch_collection(collection)
    db.commit()
    return CollectionSimpleResponse(ok=True, collectionId=collection_id)


@router.post("/collections/batch-add-book", response_model=CollectionIdListResponse, summary="여러 컬렉션에 도서 일괄 추가")
def batch_add_book(
    payload: CollectionBatchAddBookRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    book = db.query(Book).filter(Book.id == payload.bookId).first()
    if not book:
        raise HTTPException(status_code=404, detail="책을 찾을 수 없습니다")
    added: list[int] = []
    collections = db.query(Collection).filter(Collection.id.in_(payload.collectionIds), Collection.user_id == current_user.id).all()
    found_ids = {row.id for row in collections}
    missing = [collection_id for collection_id in payload.collectionIds if collection_id not in found_ids]
    if missing:
        raise HTTPException(status_code=404, detail=f"컬렉션을 찾을 수 없습니다: {missing[0]}")
    for collection in collections:
        exists = db.query(CollectionBook.id).filter(CollectionBook.collection_id == collection.id, CollectionBook.book_id == payload.bookId).first()
        if exists:
            continue
        _insert_book_at_front(db, collection.id, payload.bookId)
        _touch_collection(collection)
        added.append(collection.id)
    db.commit()
    return CollectionIdListResponse(ok=True, addedCollectionIds=added)


@router.post("/collections/{collection_id}/like", response_model=CollectionLikeResponse, summary="컬렉션 좋아요")
def like_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = _get_collection_or_404(db, collection_id)
    if collection.is_private:
        raise HTTPException(status_code=403, detail="비공개 컬렉션에는 좋아요를 할 수 없습니다")
    like = db.query(CollectionLike).filter(CollectionLike.collection_id == collection_id, CollectionLike.user_id == current_user.id).first()
    if not like:
        db.add(CollectionLike(collection_id=collection_id, user_id=current_user.id))
        db.commit()

        _notify_collection_reaction(
            db,
            collection=collection,
            actor=current_user,
            body='내 컬렉션에 좋아요가 추가됐어요.',
            event_kind='COLLECTION_LIKE',
        )
    return CollectionLikeResponse(ok=True, isLiked=True, likeCount=_collection_like_count(db, collection_id))


@router.delete("/collections/{collection_id}/like", response_model=CollectionLikeResponse, summary="컬렉션 좋아요 취소")
def unlike_collection(
    collection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    collection = _get_collection_or_404(db, collection_id)
    _ensure_collection_readable(collection, current_user)
    like = db.query(CollectionLike).filter(CollectionLike.collection_id == collection_id, CollectionLike.user_id == current_user.id).first()
    if like:
        db.delete(like)
        db.commit()
    return CollectionLikeResponse(ok=True, isLiked=False, likeCount=_collection_like_count(db, collection_id))

