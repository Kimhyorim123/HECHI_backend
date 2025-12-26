from app.services.google_books import get_client, map_volume_to_book_fields
from app.database import SessionLocal
from scripts.import_books_by_titles import upsert_book_from_fields
from app.models import Book
from sqlalchemy import func

# 장르별 키워드
GENRES = [
    ("추리", ["추리", "미스터리", "탐정"]),
    ("스릴러/공포", ["스릴러", "공포", "호러"]),
    ("SF", ["SF", "공상과학", "과학소설"]),
    ("판타지", ["판타지", "마법", "이세계"]),
    ("로맨스", ["로맨스", "사랑", "연애"]),
    ("액션", ["액션", "모험"]),
    ("역사", ["역사", "한국사", "세계사"]),
    ("과학", ["과학", "자연과학", "물리학", "생명과학"]),
    ("인문", ["인문", "인문학"]),
    ("철학", ["철학"]),
    ("사회/정치", ["사회", "정치"]),
    ("경제/경영", ["경제", "경영", "비즈니스"]),
    ("자기계발", ["자기계발", "자기개발", "성장"]),
    ("예술", ["예술", "미술", "음악", "디자인"]),
    ("여행", ["여행", "세계여행", "국내여행"]),
    ("취미", ["취미", "요리", "운동", "게임"]),
    ("소설/시/에세이/만화", ["소설", "시", "에세이", "만화"]),
]

client = get_client()
db = SessionLocal()
try:
    # 이미 등록된 ISBN/제목+출판사 세트 조회
    existing_isbns = set(r[0] for r in db.query(Book.isbn).filter(Book.isbn != None).all())
    existing_titles = set((r[0].strip(), (r[1] or '').strip()) for r in db.query(Book.title, Book.publisher).all())
    total = 0
    for genre, keywords in GENRES:
        print(f"\n=== {genre} ===")
        for kw in keywords:
            for i in range(0, 120, 40):
                vols = client.by_query_paged(f'{kw} 한국', i, 40)
                for v in vols:
                    fields = map_volume_to_book_fields(v)
                    isbn = fields.get("isbn")
                    title = (fields.get("title") or "").strip()
                    publisher = (fields.get("publisher") or "").strip()
                    # 중복 체크
                    if isbn and isbn in existing_isbns:
                        continue
                    if (title, publisher) in existing_titles:
                        continue
                    book = upsert_book_from_fields(db, fields)
                    db.commit()
                    if book:
                        print(f'Imported: {genre} | {fields.get("title")} -> book_id={book.id}')
                        total += 1
                        if isbn:
                            existing_isbns.add(isbn)
                        existing_titles.add((title, publisher))
    print(f"총 {total}권 장르별 신규 저장 완료")
finally:
    db.close()
