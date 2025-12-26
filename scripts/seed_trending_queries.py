from datetime import datetime, timedelta
from typing import List, Tuple

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import SearchQueryStat, Book

# 인기순 상위(1472~1481)를 피해서, 1482~1498 중심으로 매칭되는 쿼리 구성
# (쿼리는 Book.title/Publisher/Author.name의 부분일치로 매핑됨)
# 형식: (query, total_count)
QUERIES: List[Tuple[str, int]] = [
    ("도파민네이션", 420),     # 1483
    ("나는 생각이 너무 많아", 400),  # 1484
    ("아침 5시", 520),         # 1486
    ("세이노의 가르침", 480),    # 1488
    ("상처받지 않는 영혼", 460),  # 1489
    ("채식주의자", 440),        # 1490
    ("첫 여름 완주", 300),       # 1491
    ("류수영 레시피", 380),      # 1492 (publisher/author 키워드 혼용 가능)
    ("청춘의 독서", 360),        # 1493
    ("낙원맨션", 340),          # 1494
    ("안녕이라 그랬어", 320),     # 1495
    ("손자병법", 500),          # 1496
    ("헤일메리", 560),          # 1497
    ("빛의 속도로", 450),        # 1498 '우리가 빛의 속도로 갈 수 없다면'
]

DAYS_WINDOW = 30


def upsert_query(db: Session, q: str, cnt: int):
    row = db.query(SearchQueryStat).filter(SearchQueryStat.query == q).first()
    now = datetime.utcnow()
    if row:
        row.total_count = cnt
        row.last_hit_at = now
    else:
        row = SearchQueryStat(query=q, total_count=cnt, last_hit_at=now)
        db.add(row)


def seed_queries():
    db = SessionLocal()
    try:
        for q, cnt in QUERIES:
            upsert_query(db, q, cnt)
        db.commit()
        print(f"Seeded {len(QUERIES)} trending queries")
    finally:
        db.close()


if __name__ == "__main__":
    seed_queries()
