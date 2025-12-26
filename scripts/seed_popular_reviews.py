import random
from datetime import date, timedelta
from typing import Dict, List, Tuple

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    User,
    Book,
    UserBook,
    Review,
    ReadingStatus,
)

# 임의 데이터: 스크린샷의 책 ID 1472~1497
# 원하는 리뷰 수와 목표 평균 평점을 지정
BOOK_TARGETS: Dict[int, Tuple[int, float]] = {
    1472: (120, 4.6),
    1473: (110, 4.4),
    1474: (105, 4.5),
    1475: (100, 4.7),
    1476: (95, 4.3),
    1477: (90, 4.2),
    1478: (88, 4.1),
    1479: (86, 4.0),
    1480: (84, 4.5),
    1481: (82, 4.0),
    1482: (80, 4.4),
    1483: (78, 4.2),
    1484: (76, 4.3),
    1485: (74, 4.0),
    1486: (72, 4.6),
    1487: (0, 0.0),   # 삭제된 책일 수 있으니 0
    1488: (70, 4.1),
    1489: (68, 4.5),
    1490: (66, 4.2),
    1491: (64, 4.4),
    1492: (62, 4.0),
    1493: (60, 4.3),
    1494: (58, 4.1),
    1495: (56, 4.2),
    1496: (54, 3.9),
    1497: (52, 4.6),
}

# 더미 사용자 풀을 생성 (최대 리뷰 수만큼)
MAX_REVIEWS = max(cnt for cnt, _ in BOOK_TARGETS.values())
DUMMY_USER_COUNT = max(30, MAX_REVIEWS)  # 넉넉히 생성

RANDOM_SEED = 20251201
random.seed(RANDOM_SEED)


def ensure_dummy_users(db: Session) -> List[int]:
    ids: List[int] = []
    for i in range(1, DUMMY_USER_COUNT + 1):
        email = f"seed_pop_{i}@local"
        user = db.query(User).filter(User.email == email).first()
        if not user:
            user = User(
                email=email,
                password_hash=hash_password("seed123!"),
                name=f"SeedUser{i}",
                nickname=f"Seed{i}",
            )
            db.add(user)
            db.flush()  # assign id
        ids.append(user.id)
    db.commit()
    return ids


def rating_to_half_star(x: float) -> float:
    # 0.5 단위로 반올림, 1.0~5.0로 클램프
    r = round(x * 2) / 2.0
    return max(1.0, min(5.0, r))


def generate_ratings(n: int, target_avg: float) -> List[float]:
    if n <= 0:
        return []
    # 정규분포 기반으로 생성 후 평균 보정
    base = [rating_to_half_star(random.normalvariate(target_avg, 0.4)) for _ in range(n)]
    cur_avg = sum(base) / n
    diff = target_avg - cur_avg
    if abs(diff) < 0.05:
        return base
    # 마지막 몇 개 항목을 조정해 근사
    step = 0.5 if diff > 0 else -0.5
    i = 0
    while abs(sum(base) / n - target_avg) >= 0.05 and i < n * 4:
        idx = i % n
        new_val = rating_to_half_star(base[idx] + step)
        base[idx] = new_val
        i += 1
    return base


def ensure_user_book(db: Session, user_id: int, book_id: int) -> int:
    ub = (
        db.query(UserBook)
        .filter(UserBook.user_id == user_id, UserBook.book_id == book_id)
        .first()
    )
    if ub:
        return ub.id
    ub = UserBook(user_id=user_id, book_id=book_id, status=ReadingStatus.COMPLETED)
    db.add(ub)
    db.flush()
    return ub.id


def seed_reviews():
    db = SessionLocal()
    try:
        dummy_user_ids = ensure_dummy_users(db)
        for book_id, (review_count, avg_rating) in BOOK_TARGETS.items():
            if review_count <= 0:
                continue
            exists = db.query(Book).filter(Book.id == book_id).first()
            if not exists:
                print(f"Skip book {book_id}: not found")
                continue
            # 최근 30일 내 날짜 분포
            ratings = generate_ratings(review_count, avg_rating)
            users = dummy_user_ids[:review_count]
            for idx, (uid, rating) in enumerate(zip(users, ratings)):
                ub_id = ensure_user_book(db, uid, book_id)
                # 최근 30일 내 임의 날짜
                days_ago = random.randint(0, 20)
                created = date.today() - timedelta(days=days_ago)
                rv = Review(
                    user_book_id=ub_id,
                    user_id=uid,
                    book_id=book_id,
                    rating=rating,
                    content=f"[seed] auto review #{idx+1}",
                    like_count=random.randint(0, 5),
                    is_spoiler=False,
                    created_date=created,
                )
                db.add(rv)
            db.commit()
            print(f"Seeded reviews: book {book_id} -> {review_count} reviews, avg~{avg_rating}")
    finally:
        db.close()


if __name__ == "__main__":
    seed_reviews()
