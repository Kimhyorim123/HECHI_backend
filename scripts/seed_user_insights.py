import random
from typing import List

from app.database import SessionLocal
from app.models import User, UserInsight

TAGS_POOL = [
    "힐링", "감동적인", "스릴 넘친", "블랙코미디", "깊이 있는",
    "몰입감", "잔잔한", "철학적", "재미있는", "지적인",
]

RANDOM_SEED = 20251201
random.seed(RANDOM_SEED)


def make_tags(k: int = 6) -> List[dict]:
    labels = random.sample(TAGS_POOL, k)
    # 상위일수록 높은 가중치
    weights = sorted([random.uniform(0.55, 0.97) for _ in range(k)], reverse=True)
    return [{"label": l, "weight": round(w, 2)} for l, w in zip(labels, weights)]


def seed():
    db = SessionLocal()
    try:
        users = db.query(User).all()
        for u in users:
            row = db.query(UserInsight).filter(UserInsight.user_id == u.id).first()
            text = "대중의 평가에 잘 휘둘리지 않는 편이며, 깊이 있는 작품을 선호하는 경향이 있습니다."
            tags = make_tags()
            if not row:
                row = UserInsight(user_id=u.id, analysis_text=text, tags=tags)
                db.add(row)
            else:
                row.analysis_text = text
                row.tags = tags
        db.commit()
        print(f"Seeded insights for {len(users)} users")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
