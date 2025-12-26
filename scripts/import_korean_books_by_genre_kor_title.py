
import re
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
    # 공부/코딩/자격증 관련
    ("공부/코딩/자격증", [
        "공부", "수험서", "자격증", "정보처리기사", "컴퓨터", "IT", "코딩", "프로그래밍", "파이썬", "자바", "C언어", "알고리즘", "데이터베이스", "SQL", "네트워크", "리눅스", "정보보안", "AI", "인공지능", "딥러닝", "머신러닝", "토익", "토플", "한국사능력검정", "공무원", "수능", "수학", "과학탐구"
    ]),
    # 유명도서 한글판(해리포터 등)
    ("유명도서(한글판)", [
        "해리포터", "Harry Potter 한글", "해리 포터", "반지의 제왕 한글", "Lord of the Rings 한글", "셜록홈즈 한글", "Sherlock Holmes 한글", "어린왕자 한글", "Le Petit Prince 한글", "호빗 한글", "Hobbit 한글", "나니아 연대기 한글", "Narnia 한글", "데미안 한글", "Demian 한글", "노인과 바다 한글", "The Old Man and the Sea 한글", "1984 한글", "동물농장 한글", "Animal Farm 한글"
    ]),
]

def is_korean_title(text):
    # 한글이 2글자 이상 포함, 한자(\u4E00-\u9FFF) 미포함
    if not text:
        return False
    has_korean = bool(re.search(r"[가-힣]{2,}", text))
    has_hanja = bool(re.search(r"[\u4E00-\u9FFF]", text))
    return has_korean and not has_hanja

client = get_client()
db = SessionLocal()
try:
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
                    title = (fields.get("title") or "").strip()
                    if not is_korean_title(title):
                        continue
                    isbn = fields.get("isbn")
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
    print(f"총 {total}권 장르별 한글 제목 신규 저장 완료")
finally:
    db.close()
