from __future__ import annotations

from collections import defaultdict
import re
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Book, BookCategory, Collection, CollectionTag, ReadingStatus, Review, Tag, UserBook, Wishlist
from app.services.genre_mapping import get_korean_genres

DISPLAY_LABELS = {
    "여운이남는": "여운이 남는",
    "긴장감있는": "긴장감 있는",
    "몰입감있는": "몰입감 있는",
    "잠들기전에읽는": "잠들기 전에 읽는",
    "주말에읽기좋은": "주말에 읽기 좋은",
    "카페에서읽기좋은": "카페에서 읽기 좋은",
    "여행할때읽기좋은": "여행할 때 읽기 좋은",
    "출퇴근에읽기좋은": "출퇴근에 읽기 좋은",
    "가볍게읽기좋은": "가볍게 읽기 좋은",
    "한번에읽는": "한 번에 읽는",
    "천천히읽는": "천천히 읽는",
    "생각이많아지는": "생각이 많아지는",
    "지식이쌓이는": "지식이 쌓이는",
    "눈물나는": "눈물 나는",
    "다시읽고싶은": "다시 읽고 싶은",
    "곱씹게되는": "곱씹게 되는",
    "시야가넓어지는": "시야가 넓어지는",
    "페이지터너": "페이지터너",
    "사유적인": "사유적인",
    "서사적인": "서사적인",
    "감성적인": "감성적인",
    "현실비판적인": "현실 비판적인",
    "심리적인": "심리적인",
    "상징적인": "상징적인",
    "묵직한": "묵직한",
    "선명한": "선명한",
    "치밀한": "치밀한",
    "명료한": "명료한",
    "확장되는": "확장되는",
}

TAG_CATEGORY_BY_NAME = {
    "힐링": "emotion",
    "감동": "emotion",
    "눈물나는": "emotion",
    "위로되는": "emotion",
    "여운이남는": "emotion",
    "따뜻한": "emotion",
    "다정한": "emotion",
    "먹먹한": "emotion",
    "쓸쓸한": "emotion",
    "벅찬": "emotion",
    "희망적인": "emotion",
    "설레는": "emotion",
    "로맨틱한": "emotion",
    "감성적인": "emotion",
    "묵직한": "emotion",
    "잔잔한": "mood",
    "몽환적인": "mood",
    "서늘한": "mood",
    "어두운": "mood",
    "유쾌한": "mood",
    "발랄한": "mood",
    "긴장감있는": "mood",
    "몰입감있는": "mood",
    "속도감있는": "mood",
    "심리적인": "mood",
    "상징적인": "mood",
    "치밀한": "mood",
    "선명한": "mood",
    "잠들기전에읽는": "situation",
    "주말에읽기좋은": "situation",
    "카페에서읽기좋은": "situation",
    "여행할때읽기좋은": "situation",
    "출퇴근에읽기좋은": "situation",
    "가볍게읽기좋은": "style",
    "한번에읽는": "style",
    "천천히읽는": "style",
    "인생책": "style",
    "페이지터너": "style",
    "다시읽고싶은": "style",
    "곱씹게되는": "style",
    "서사적인": "style",
    "초보추천": "difficulty",
    "생각이많아지는": "difficulty",
    "지식이쌓이는": "difficulty",
    "시야가넓어지는": "difficulty",
    "통찰을주는": "difficulty",
    "현실적인": "difficulty",
    "철학적인": "difficulty",
    "사회적인": "difficulty",
    "사유적인": "difficulty",
    "현실비판적인": "difficulty",
    "명료한": "difficulty",
    "확장되는": "difficulty",
}

GENRE_TAG_HINTS = {
    "로맨스": ["로맨틱한", "설레는", "여운이남는", "다정한", "감성적인"],
    "시": ["여운이남는", "감동", "먹먹한", "곱씹게되는", "상징적인"],
    "에세이": ["여운이남는", "위로되는", "따뜻한", "잔잔한", "사유적인"],
    "소설": ["몰입감있는", "다시읽고싶은", "서사적인", "심리적인"],
    "추리": ["긴장감있는", "몰입감있는", "페이지터너", "치밀한"],
    "스릴러/공포": ["긴장감있는", "몰입감있는", "서늘한", "속도감있는", "치밀한"],
    "SF": ["몰입감있는", "시야가넓어지는", "생각이많아지는", "확장되는"],
    "판타지": ["몰입감있는", "몽환적인", "다시읽고싶은", "상징적인"],
    "액션": ["몰입감있는", "속도감있는", "페이지터너", "선명한"],
    "역사": ["생각이많아지는", "지식이쌓이는", "시야가넓어지는", "사유적인"],
    "과학": ["생각이많아지는", "지식이쌓이는", "시야가넓어지는", "명료한"],
    "인문": ["생각이많아지는", "통찰을주는", "곱씹게되는", "사유적인"],
    "철학": ["생각이많아지는", "철학적인", "곱씹게되는", "사유적인"],
    "사회/정치": ["생각이많아지는", "사회적인", "현실적인", "현실비판적인"],
    "경제/경영": ["생각이많아지는", "지식이쌓이는", "현실적인", "명료한"],
    "자기계발": ["위로되는", "지식이쌓이는", "희망적인", "명료한"],
    "예술": ["여운이남는", "몽환적인", "감동", "감성적인"],
    "여행": ["가볍게읽기좋은", "여행할때읽기좋은", "주말에읽기좋은", "선명한"],
    "취미": ["가볍게읽기좋은", "주말에읽기좋은", "유쾌한", "명료한"],
    "코미디": ["유쾌한", "발랄한", "가볍게읽기좋은", "선명한"],
    "만화": ["가볍게읽기좋은", "유쾌한", "몰입감있는", "서사적인"],
}

KEYWORD_TAG_HINTS = {
    "로맨틱한": ["사랑", "연애", "로맨틱", "애틋", "연인"],
    "설레는": ["설렘", "두근", "심쿵", "간질", "두근두근"],
    "따뜻한": ["따뜻", "포근", "온기", "따스", "따사"],
    "다정한": ["다정", "다정함", "다정한", "사려", "섬세"],
    "먹먹한": ["먹먹", "멍해", "먹먹함"],
    "쓸쓸한": ["쓸쓸", "허전", "고독", "외로"],
    "벅찬": ["벅차", "벅찬", "가슴이 찼", "울컥"],
    "희망적인": ["희망", "용기", "다시 해", "버틸", "나아갈"],
    "유쾌한": ["유쾌", "웃겼", "웃기", "재밌", "코믹", "명랑", "발랄"],
    "발랄한": ["발랄", "통통", "경쾌", "명랑"],
    "여운이남는": ["여운", "오래 남", "곱씹", "계속 떠오", "생각났", "생각난다"],
    "긴장감있는": ["긴장", "숨막", "손에 땀", "쫄깃", "압도", "조마조마"],
    "몰입감있는": ["몰입", "흡입", "빠져", "멈출 수 없", "순식간"],
    "속도감있는": ["속도감", "전개", "빠르", "템포"],
    "위로되는": ["위로", "위안", "치유", "힐링", "다독"],
    "감동": ["감동", "울림", "울컥", "눈물", "뭉클"],
    "잔잔한": ["잔잔", "고요", "평온", "조용"],
    "몽환적인": ["몽환", "환상", "꿈결", "비현실"],
    "서늘한": ["서늘", "오싹", "차갑", "냉랭"],
    "생각이많아지는": ["생각", "질문", "고민", "성찰", "철학", "되짚"],
    "지식이쌓이는": ["배웠", "알게", "지식", "이해", "통찰", "정리"],
    "시야가넓어지는": ["시야", "넓어", "다르게 보", "관점", "입체적"],
    "통찰을주는": ["통찰", "통찰력", "꿰뚫", "본질"],
    "현실적인": ["현실", "구체", "실제", "실질적"],
    "철학적인": ["철학", "존재", "의미", "본질"],
    "사회적인": ["사회", "구조", "제도", "정치", "공동체"],
    "잠들기전에읽는": ["잠들기 전", "밤에 읽", "자기 전"],
    "주말에읽기좋은": ["주말", "쉬는 날", "한가한 날"],
    "카페에서읽기좋은": ["카페", "창가", "커피"],
    "여행할때읽기좋은": ["여행", "기차", "비행기", "낯선 곳"],
    "출퇴근에읽기좋은": ["출근길", "퇴근길", "지하철", "버스"],
    "가볍게읽기좋은": ["가볍", "부담 없", "술술", "편하"],
    "한번에읽는": ["단숨", "한 번에", "멈출 수 없"],
    "천천히읽는": ["천천히", "곱씹", "천천히 읽", "음미"],
    "인생책": ["인생책", "오래 간직", "평생", "최고였"],
    "페이지터너": ["페이지", "손에서 못 놓", "계속 넘기", "단숨"],
    "다시읽고싶은": ["다시 읽", "재독", "또 읽", "다시 펼"],
    "곱씹게되는": ["곱씹", "되새기", "계속 생각", "음미"],
    "초보추천": ["입문", "초보", "쉽게 읽", "친절"],
    "사유적인": ["사유", "사색", "되돌아보", "곰곰", "성찰"],
    "서사적인": ["서사", "이야기", "전개", "서술", "플롯"],
    "감성적인": ["감성", "감정선", "섬세", "분위기", "감각적"],
    "현실비판적인": ["비판", "모순", "현실을 꼬집", "풍자", "구조적"],
    "심리적인": ["심리", "내면", "무의식", "감정 변화", "심층"],
    "상징적인": ["상징", "비유", "은유", "이미지", "함의"],
    "묵직한": ["묵직", "무겁", "진중", "쉽지 않", "깊은 여운"],
    "선명한": ["선명", "또렷", "강렬", "인상적", "뚜렷"],
    "치밀한": ["치밀", "정교", "촘촘", "계산된", "짜임새"],
    "명료한": ["명료", "깔끔", "분명", "이해하기 쉬", "정돈"],
    "확장되는": ["확장", "넓어졌", "열리", "커졌", "확장되는"],
}


def _display_label(name: str) -> str:
    return DISPLAY_LABELS.get(name, name)


def _normalize_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _genres_from_category_text(category: str | None) -> list[str]:
    if not category:
        return []
    candidates = []
    raw = (category or "").strip()
    if raw:
        candidates.append(raw)
        candidates.extend(token.strip() for token in raw.split(">") if token.strip())
    result: list[str] = []
    for candidate in candidates:
        for genre in get_korean_genres(candidate):
            if genre not in result:
                result.append(genre)
    return result


def _book_genres(book_id: int, primary_category: str | None, cached_categories: dict[int, list[str]]) -> list[str]:
    result: list[str] = []
    for genre in _genres_from_category_text(primary_category):
        if genre not in result:
            result.append(genre)
    for category in cached_categories.get(book_id, []):
        for genre in _genres_from_category_text(category):
            if genre not in result:
                result.append(genre)
    return result


def _rank_tags(tag_scores: dict[str, float]) -> list[tuple[str, float]]:
    ranked = sorted(((label, score) for label, score in tag_scores.items() if score > 0), key=lambda item: item[1], reverse=True)
    chosen: list[tuple[str, float]] = []
    category_counts: dict[str, int] = defaultdict(int)
    for label, score in ranked:
        category = TAG_CATEGORY_BY_NAME.get(label, "other")
        if category_counts[category] >= 1 and len(chosen) < 8:
            continue
        chosen.append((label, score))
        category_counts[category] += 1
        if len(chosen) >= 8:
            break
    if len(chosen) < 8:
        seen = {label for label, _ in chosen}
        for label, score in ranked:
            if label in seen:
                continue
            chosen.append((label, score))
            if len(chosen) >= 8:
                break
    return chosen


def _review_rating_weight(rating: float) -> float:
    if rating >= 5.0:
        return 2.6
    if rating >= 4.5:
        return 2.25
    if rating >= 4.0:
        return 1.9
    if rating >= 3.5:
        return 1.2
    if rating >= 3.0:
        return 0.55
    return 0.15


def _status_signal_weight(status: ReadingStatus) -> float:
    if status == ReadingStatus.COMPLETED:
        return 1.8
    if status == ReadingStatus.READING:
        return 0.25
    if status == ReadingStatus.PAUSED:
        return 0.12
    if status == ReadingStatus.PENDING:
        return 0.08
    return 0.05


def generate_user_insight(db: Session, user_id: int) -> tuple[str | None, list[dict[str, Any]]]:
    tag_scores: dict[str, float] = defaultdict(float)
    genre_scores: dict[str, float] = defaultdict(float)
    genre_counts: dict[str, int] = defaultdict(int)

    collection_tag_rows = (
        db.query(Tag.name, func.count(CollectionTag.id))
        .join(CollectionTag, CollectionTag.tag_id == Tag.id)
        .join(Collection, Collection.id == CollectionTag.collection_id)
        .filter(Collection.user_id == user_id)
        .group_by(Tag.name)
        .all()
    )
    for tag_name, count in collection_tag_rows:
        if not tag_name:
            continue
        # Collection tags are treated as a weak hint, not the primary signal.
        tag_scores[tag_name] += float(count) * 0.7

    review_rows = (
        db.query(Review.rating, Review.content, Book.id, Book.category, UserBook.status)
        .join(Book, Review.book_id == Book.id)
        .outerjoin(UserBook, Review.user_book_id == UserBook.id)
        .filter(Review.user_id == user_id, Review.rating.isnot(None))
        .all()
    )

    user_book_rows = (
        db.query(UserBook.status, Book.id, Book.category)
        .join(Book, UserBook.book_id == Book.id)
        .filter(UserBook.user_id == user_id)
        .all()
    )

    wishlist_rows = (
        db.query(Book.id, Book.category)
        .join(Wishlist, Wishlist.book_id == Book.id)
        .filter(Wishlist.user_id == user_id)
        .all()
    )

    if not review_rows and not collection_tag_rows and not user_book_rows and not wishlist_rows:
        return None, []

    book_ids = {book_id for _, _, book_id, _, _ in review_rows}
    book_ids.update(book_id for _, book_id, _ in user_book_rows)
    book_ids.update(book_id for book_id, _ in wishlist_rows)

    categories_by_book: dict[int, list[str]] = defaultdict(list)
    if book_ids:
        for bid, cname in db.query(BookCategory.book_id, BookCategory.category_name).filter(BookCategory.book_id.in_(book_ids)).all():
            if cname:
                categories_by_book[bid].append(cname)

    total_rating = 0.0
    total_reviews = 0
    strong_signal_found = False
    completed_book_ids = {book_id for status, book_id, _ in user_book_rows if status == ReadingStatus.COMPLETED}

    for rating, content, book_id, primary_category, user_book_status in review_rows:
        rating_val = float(rating or 0.0)
        total_rating += rating_val
        total_reviews += 1

        rating_weight = _review_rating_weight(rating_val)
        completed_bonus = 1.2 if (user_book_status == ReadingStatus.COMPLETED or book_id in completed_book_ids) else 1.0
        strong_review = rating_val >= 4.0
        if strong_review:
            strong_signal_found = True

        genres = _book_genres(book_id, primary_category, categories_by_book)
        for genre in genres:
            genre_boost = rating_weight * completed_bonus
            genre_scores[genre] += genre_boost
            if strong_review or completed_bonus > 1.0:
                genre_counts[genre] += 2
            else:
                genre_counts[genre] += 1
            for tag in GENRE_TAG_HINTS.get(genre, []):
                tag_scores[tag] += genre_boost * 1.35

        normalized = _normalize_text(content)
        if normalized:
            for tag, keywords in KEYWORD_TAG_HINTS.items():
                hits = sum(1 for keyword in keywords if keyword in normalized)
                if hits:
                    text_boost = (1.2 + (0.35 * min(hits, 3))) * completed_bonus
                    if strong_review:
                        text_boost += 0.85
                    tag_scores[tag] += text_boost

    for status, book_id, primary_category in user_book_rows:
        signal_weight = _status_signal_weight(status)
        if status == ReadingStatus.COMPLETED:
            strong_signal_found = True
        genres = _book_genres(book_id, primary_category, categories_by_book)
        for genre in genres:
            genre_scores[genre] += signal_weight
            genre_counts[genre] += 2 if status == ReadingStatus.COMPLETED else 1
            genre_tag_weight = signal_weight * (1.05 if status == ReadingStatus.COMPLETED else 0.35)
            for tag in GENRE_TAG_HINTS.get(genre, []):
                tag_scores[tag] += genre_tag_weight

    if not strong_signal_found:
        for book_id, primary_category in wishlist_rows:
            genres = _book_genres(book_id, primary_category, categories_by_book)
            for genre in genres:
                genre_scores[genre] += 0.2
                genre_counts[genre] += 1
                for tag in GENRE_TAG_HINTS.get(genre, []):
                    tag_scores[tag] += 0.1

    top_genres = sorted(
        genre_counts.items(),
        key=lambda item: (item[1], genre_scores.get(item[0], 0.0)),
        reverse=True,
    )[:3]

    top_tags = _rank_tags(tag_scores)
    if not top_tags and top_genres:
        fallback = []
        seen = set()
        for genre, _ in top_genres:
            for tag in GENRE_TAG_HINTS.get(genre, []):
                if tag not in seen:
                    fallback.append((tag, 1.0))
                    seen.add(tag)
                if len(fallback) >= 8:
                    break
            if len(fallback) >= 8:
                break
        top_tags = fallback

    if not top_tags and not top_genres:
        return None, []

    max_score = top_tags[0][1] if top_tags else 1.0
    tags = [
        {
            "label": _display_label(label),
            "weight": round(min(score / max_score, 1.0), 2),
        }
        for label, score in top_tags
    ]

    avg_100 = int(round((total_rating / total_reviews) * 20)) if total_reviews else 0
    genre_phrase = ", ".join(genre for genre, _ in top_genres[:2]) if top_genres else None
    tag_phrase = ", ".join(item["label"] for item in tags[:4]) if tags else None

    parts: list[str] = []
    if genre_phrase:
        parts.append(f"완독했거나 높게 평가한 책을 보면 {genre_phrase} 장르 취향이 두드러져요.")
    elif user_book_rows or wishlist_rows:
        parts.append("완독한 책과 높은 평점을 남긴 책의 장르 성향이 반영되고 있어요.")
    if avg_100:
        parts.append(f"평균 별점은 100점 기준 {avg_100}점이에요.")
    if tag_phrase:
        parts.append(f"특히 {tag_phrase} 같은 결의 책에 자주 반응하고 있어요.")
    analysis = " ".join(parts) if parts else None
    return analysis, tags
