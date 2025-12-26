import re
from app.services.google_books import get_client, map_volume_to_book_fields
from app.database import SessionLocal
from scripts.import_books_by_titles import upsert_book_from_fields
from app.models import Book

# 한글 제목만 허용 (한자 미포함)
def is_korean_title(text):
    if not text:
        return False
    has_korean = bool(re.search(r"[가-힣]{2,}", text))
    has_hanja = bool(re.search(r"[\u4E00-\u9FFF]", text))
    return has_korean and not has_hanja

KEYWORDS = [
    # 자기계발/자격증/공부
    "자기계발", "자격증", "공부", "수험서", "공무원", "토익", "토플", "한국사능력검정", "정보처리기사", "IT", "코딩", "프로그래밍",
    # 전세계적으로 유명한 책 한글 번역본
    "해리포터", "Harry Potter 한글", "반지의 제왕", "Lord of the Rings 한글"
]

client = get_client()
db = SessionLocal()
try:
    existing_isbns = set(r[0] for r in db.query(Book.isbn).filter(Book.isbn != None).all())
    existing_titles = set((r[0].strip(), (r[1] or '').strip()) for r in db.query(Book.title, Book.publisher).all())
    total = 0
    for kw in KEYWORDS:
        print(f"\n=== {kw} ===")
        for i in range(0, 40, 20):  # 소량만 요청
            vols = client.by_query_paged(f'{kw} 한국', i, 20)
            for v in vols:
                fields = map_volume_to_book_fields(v)
                title = (fields.get("title") or "").strip()
                if not is_korean_title(title):
                    continue
                isbn = fields.get("isbn")
                publisher = (fields.get("publisher") or "").strip()
                if isbn and isbn in existing_isbns:
                    continue
                if (title, publisher) in existing_titles:
                    continue
                book = upsert_book_from_fields(db, fields)
                db.commit()
                if book:
                    print(f'Imported: {kw} | {fields.get("title")} -> book_id={book.id}')
                    total += 1
                    if isbn:
                        existing_isbns.add(isbn)
                    existing_titles.add((title, publisher))
    print(f"총 {total}권 키워드별 한글 제목 신규 저장 완료")
finally:
    db.close()
