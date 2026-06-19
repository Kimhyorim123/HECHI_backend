from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    BadgeDefinition,
    Book,
    BookCategory,
    Bookmark,
    NotificationType,
    ReadingStatus,
    Review,
    UserBadge,
    UserBook,
    Wishlist,
)
from app.services.genre_mapping import get_korean_genres
from app.services.notify import create_notification

BADGE_DEFINITIONS = [
    {"code": "reading.beginner_5", "category": "reading", "level_code": "beginner_5", "title": "독서 비기너", "description": "완독한 책이 5권 이상이에요.", "threshold": 5},
    {"code": "reading.pro_10", "category": "reading", "level_code": "pro_10", "title": "독서 프로", "description": "완독한 책이 10권 이상이에요.", "threshold": 10},
    {"code": "reading.master_20", "category": "reading", "level_code": "master_20", "title": "독서 마스터", "description": "완독한 책이 20권 이상이에요.", "threshold": 20},
    {"code": "reading.library_50", "category": "reading", "level_code": "library_50", "title": "걸어 다니는 도서관", "description": "완독한 책이 50권 이상이에요.", "threshold": 50},
    {"code": "rating.fairy_10", "category": "rating", "level_code": "fairy_10", "title": "별점 요정", "description": "평점을 10개 이상 남겼어요.", "threshold": 10},
    {"code": "rating.craft_30", "category": "rating", "level_code": "craft_30", "title": "별점 장인", "description": "평점을 30개 이상 남겼어요.", "threshold": 30},
    {"code": "rating.restaurant_100", "category": "rating", "level_code": "restaurant_100", "title": "별점 맛집", "description": "평점을 100개 이상 남겼어요.", "threshold": 100},
    {"code": "review.poem_5", "category": "review", "level_code": "poem_5", "title": "리뷰로 시 쓰기", "description": "리뷰를 5개 이상 작성했어요.", "threshold": 5},
    {"code": "review.short_15", "category": "review", "level_code": "short_15", "title": "리뷰로 단편 쓰기", "description": "리뷰를 15개 이상 작성했어요.", "threshold": 15},
    {"code": "review.author_30", "category": "review", "level_code": "author_30", "title": "리뷰로 작가 등단!", "description": "리뷰를 30개 이상 작성했어요.", "threshold": 30},
    {"code": "genre.lover_10", "category": "genre", "level_code": "lover_10", "title": "해당 장르 러버", "description": "특정 장르에 평점 10개 이상을 남겼어요.", "threshold": 10, "context_type": "genre", "is_repeatable": True},
    {"code": "genre.omnireader_10genres", "category": "genre", "level_code": "omnireader_10genres", "title": "잡독(서)러", "description": "평점을 남긴 장르가 10개 이상이에요.", "threshold": 10},
    {"code": "wishlist.desire_30", "category": "wishlist", "level_code": "desire_30", "title": "독서의 욕망은 끝이 없어!", "description": "위시리스트에 30권 이상 담았어요.", "threshold": 30},
    {"code": "bookmark.collector_10", "category": "bookmark", "level_code": "collector_10", "title": "문장 수집가", "description": "북마크를 10개 이상 남겼어요.", "threshold": 10},
    {"code": "bookmark.lover_50", "category": "bookmark", "level_code": "lover_50", "title": "활자 애호가", "description": "북마크를 50개 이상 남겼어요.", "threshold": 50},
]


def sync_badge_definitions(db: Session) -> dict[str, BadgeDefinition]:
    existing = {item.code: item for item in db.query(BadgeDefinition).all()}
    changed = False
    for definition in BADGE_DEFINITIONS:
        item = existing.get(definition["code"])
        if item is None:
            item = BadgeDefinition(
                code=definition["code"],
                category=definition["category"],
                level_code=definition["level_code"],
                title=definition["title"],
                description=definition.get("description"),
                threshold=definition["threshold"],
                icon_url=definition.get("icon_url"),
                context_type=definition.get("context_type"),
                is_repeatable=definition.get("is_repeatable", False),
            )
            db.add(item)
            existing[item.code] = item
            changed = True
        else:
            item.category = definition["category"]
            item.level_code = definition["level_code"]
            item.title = definition["title"]
            item.description = definition.get("description")
            item.threshold = definition["threshold"]
            item.icon_url = definition.get("icon_url")
            item.context_type = definition.get("context_type")
            item.is_repeatable = definition.get("is_repeatable", False)
            db.add(item)
            changed = True
    if changed:
        db.commit()
    for item in existing.values():
        db.refresh(item)
    return existing


def _book_genres(db: Session, book: Book) -> list[str]:
    rows = db.query(BookCategory.category_name).filter(BookCategory.book_id == book.id).all()
    if rows:
        result: list[str] = []
        for (name,) in rows:
            for genre in get_korean_genres(name):
                if genre not in result:
                    result.append(genre)
        if result:
            return result
    fallback = []
    for genre in get_korean_genres(book.category or ""):
        if genre not in fallback:
            fallback.append(genre)
    return fallback


def _user_metrics(db: Session, user_id: int) -> dict[str, Any]:
    completed_books = (
        db.query(func.count(UserBook.id))
        .filter(UserBook.user_id == user_id, UserBook.status == ReadingStatus.COMPLETED)
        .scalar()
        or 0
    )
    rating_reviews = (
        db.query(Review)
        .join(Book, Book.id == Review.book_id)
        .filter(Review.user_id == user_id, Review.rating.isnot(None))
        .all()
    )
    rating_count = len(rating_reviews)
    review_count = sum(1 for review in rating_reviews if (review.content or '').strip())
    wishlist_count = db.query(func.count(Wishlist.id)).filter(Wishlist.user_id == user_id).scalar() or 0
    bookmark_count = (
        db.query(func.count(Bookmark.id))
        .join(UserBook, UserBook.id == Bookmark.user_book_id)
        .filter(UserBook.user_id == user_id)
        .scalar()
        or 0
    )

    genre_counts: dict[str, int] = {}
    for review in rating_reviews:
        book = db.query(Book).filter(Book.id == review.book_id).first()
        if not book:
            continue
        for genre in _book_genres(db, book):
            genre_counts[genre] = genre_counts.get(genre, 0) + 1

    return {
        "completed_books": int(completed_books),
        "rating_count": int(rating_count),
        "review_count": int(review_count),
        "wishlist_count": int(wishlist_count),
        "bookmark_count": int(bookmark_count),
        "genre_counts": genre_counts,
        "genre_variety": len(genre_counts),
    }


def _award_badge(
    db: Session,
    *,
    user_id: int,
    definition: BadgeDefinition,
    progress_snapshot: dict[str, Any],
    context_value: str | None = None,
) -> bool:
    existing = (
        db.query(UserBadge)
        .filter(
            UserBadge.user_id == user_id,
            UserBadge.badge_definition_id == definition.id,
            UserBadge.context_value == context_value,
        )
        .first()
    )
    if existing:
        return False

    user_badge = UserBadge(
        user_id=user_id,
        badge_definition_id=definition.id,
        context_value=context_value,
        progress_snapshot=progress_snapshot,
    )
    db.add(user_badge)
    db.commit()
    db.refresh(user_badge)

    target = {
        "badgeCode": definition.code,
        "badgeCategory": definition.category,
        "badgeLevel": definition.level_code,
    }
    if context_value:
        target["contextValue"] = context_value
    create_notification(
        db,
        user_id,
        title=f"새 배지 획득: {definition.title}",
        body=definition.description or "새로운 독서 업적을 달성했어요.",
        notification_type=NotificationType.BADGE_EARNED,
        target_info=target,
        data=target,
        send_push=True,
    )
    return True


def evaluate_user_badges(db: Session, user_id: int) -> int:
    definitions = sync_badge_definitions(db)
    metrics = _user_metrics(db, user_id)
    awarded = 0

    threshold_codes = [
        ("reading.beginner_5", metrics["completed_books"]),
        ("reading.pro_10", metrics["completed_books"]),
        ("reading.master_20", metrics["completed_books"]),
        ("reading.library_50", metrics["completed_books"]),
        ("rating.fairy_10", metrics["rating_count"]),
        ("rating.craft_30", metrics["rating_count"]),
        ("rating.restaurant_100", metrics["rating_count"]),
        ("review.poem_5", metrics["review_count"]),
        ("review.short_15", metrics["review_count"]),
        ("review.author_30", metrics["review_count"]),
        ("genre.omnireader_10genres", metrics["genre_variety"]),
        ("wishlist.desire_30", metrics["wishlist_count"]),
        ("bookmark.collector_10", metrics["bookmark_count"]),
        ("bookmark.lover_50", metrics["bookmark_count"]),
    ]
    for code, value in threshold_codes:
        definition = definitions[code]
        if value >= definition.threshold:
            awarded += int(_award_badge(db, user_id=user_id, definition=definition, progress_snapshot={"value": value}))

    lover_definition = definitions["genre.lover_10"]
    for genre_name, count in metrics["genre_counts"].items():
        if count >= lover_definition.threshold:
            awarded += int(
                _award_badge(
                    db,
                    user_id=user_id,
                    definition=lover_definition,
                    context_value=genre_name,
                    progress_snapshot={"value": count, "genre": genre_name},
                )
            )

    return awarded


def list_user_badges(db: Session, user_id: int) -> list[UserBadge]:
    sync_badge_definitions(db)
    return (
        db.query(UserBadge)
        .join(BadgeDefinition, BadgeDefinition.id == UserBadge.badge_definition_id)
        .filter(UserBadge.user_id == user_id)
        .order_by(UserBadge.earned_at.desc(), UserBadge.id.desc())
        .all()
    )
