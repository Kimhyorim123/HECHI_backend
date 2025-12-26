# comment_books.py의 리스트를 DB에 저장하는 스크립트
import sys
import os
from datetime import date
import requests
from dotenv import load_dotenv

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal
from app.models import Book, Author, BookAuthor, BookList
from app.scripts.comment_books import COMMENT_BOOKS

def get_api_key():
    load_dotenv()
    return os.environ.get("ALADIN_API_KEY")

def search_aladin(title, author=None):
    api_key = get_api_key()
    url = "https://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
    params = {
        "ttbkey": api_key,
        "Query": title,
        "QueryType": "Title",
        "MaxResults": 10,
        "SearchTarget": "Book",
        "output": "js",
        "Version": "20131101",
    }
    response = requests.get(url, params=params)
    response.encoding = 'utf-8'
    try:
        items = response.json().get('item', [])
    except Exception as e:
        print(f"[ERROR] JSON decode error: {e}")
        items = []
    # 저자명까지 매칭
    if author:
        for item in items:
            if author in item.get('author', ''):
                return item
    return items[0] if items else None

def upsert_book_from_item(item, db):
    isbn = item.get('isbn13')
    book = db.query(Book).filter_by(isbn=isbn).first()
    if not book:
        book = Book(
            isbn=isbn,
            title=item.get('title'),
            publisher=item.get('publisher'),
            category=item.get('categoryName'),
            published_date=item.get('pubDate'),
            thumbnail=item.get('cover'),
            small_thumbnail=item.get('cover'),
            description=item.get('description')
        )
        db.add(book)
        db.commit()
    return book

def upsert_author(name, db):
    author = db.query(Author).filter_by(name=name).first()
    if not author:
        author = Author(name=name)
        db.add(author)
        db.commit()
    return author

def link_book_author(book_id, author_id, db):
    if not db.query(BookAuthor).filter_by(book_id=book_id, author_id=author_id).first():
        db.add(BookAuthor(book_id=book_id, author_id=author_id))
        db.commit()

def upsert_book_list(book, comment, rank, db):
    today = date.today()
    list_type = f"comment_{comment}"
    obj = db.query(BookList).filter_by(isbn=book.isbn, list_type=list_type, list_date=today).first()
    if not obj:
        obj = BookList(isbn=book.isbn, list_type=list_type, rank=rank, list_date=today)
        db.add(obj)
        db.commit()
    return obj

def main():
    db = SessionLocal()
    for comment, books in COMMENT_BOOKS.items():
        print(f"[INFO] 코멘트: {comment}")
        for idx, (title, author) in enumerate(books, start=1):
            item = search_aladin(title, author)
            if not item:
                print(f"[ERROR] 알라딘 검색 실패: {title} - {author}")
                continue
            book = upsert_book_from_item(item, db)
            # 저자 연결
            for author_name in item.get('author', '').split(','):
                author_obj = upsert_author(author_name.strip(), db)
                link_book_author(book.id, author_obj.id, db)
            upsert_book_list(book, comment, idx, db)
            print(f"[SUCCESS] 저장: {title} - {author}")
    db.close()

if __name__ == "__main__":
    main()
