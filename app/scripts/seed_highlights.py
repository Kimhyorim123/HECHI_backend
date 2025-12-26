from app.models import Book, Author, UserBook, Highlight, BookAuthor
from app.database import SessionLocal
from datetime import datetime

def get_book_id(title):
    db = SessionLocal()
    book = db.query(Book).filter(Book.title == title).first()
    db.close()
    return book.id if book else None

def get_author_id(name):
    db = SessionLocal()
    author = db.query(Author).filter(Author.name == name).first()
    db.close()
    return author.id if author else None

def get_user_book_id(book_id):
    db = SessionLocal()
    user_book = db.query(UserBook).filter(UserBook.book_id == book_id).first()
    db.close()
    return user_book.id if user_book else None

def seed_highlights():
    db = SessionLocal()
    highlights = [
        {
            "book_title": "데미안",
            "author": "헤르만 헤세",
            "sentence": "새는 알에서 나오려고 투쟁한다. 알은 세계다. 태어나려는 자는 하나의 세계를 깨뜨려야 한다.",
        },
        {
            "book_title": "우리가 빛의 속도로 갈 수 없다면",
            "author": "김초엽",
            "sentence": "그럼 루이, 네게는 저 풍경이 말을 걸어오는 것처럼 보이겠네.",
        },
        {
            "book_title": "소년이 온다",
            "author": "한강",
            "sentence": "인간은 끝내 인간을 포기하지 않는다.",
        },
        {
            "book_title": "급류",
            "author": "정대건",
            "sentence": "우리는 서로를 이해하지 못한 채로도 함께 흘러간다.",
        },
        {
            "book_title": "혼모노",
            "author": "성해나",
            "sentence": "진짜는 흉내 내는 순간 이미 진짜가 아니다.",
        },
    ]
    for h in highlights:
        book_id = get_book_id(h["book_title"])
        if not book_id:
            print(f"Book not found: {h['book_title']}")
            continue
        user_book_id = get_user_book_id(book_id)
        if not user_book_id:
            print(f"UserBook not found for book_id: {book_id}")
            continue
        highlight = Highlight(
            user_book_id=user_book_id,
            page=1,
            sentence=h["sentence"],
            is_public=True,
            created_date=datetime.utcnow(),
        )
        db.add(highlight)
        print(f"Added highlight for {h['book_title']}")
    db.commit()
    db.close()

if __name__ == "__main__":
    seed_highlights()
