import os
import requests
from dotenv import load_dotenv
from app.models import Book
from app.database import SessionLocal

def get_api_key():
    load_dotenv()
    return os.environ.get("ALADIN_API_KEY")

def fetch_book_info_by_isbn(isbn):
    api_key = get_api_key()
    url = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
    params = {
        "ttbkey": api_key,
        "itemIdType": "ISBN",
        "ItemId": isbn,
        "output": "js",
        "Version": "20131101"
    }
    response = requests.get(url, params=params)
    response.encoding = 'utf-8'
    response.raise_for_status()
    items = response.json().get('item', [])
    return items[0] if items else None

def update_all_books_to_isbn13():
    db = SessionLocal()
    books = db.query(Book).all()
    updated = 0
    deleted = 0
    seen_isbn13 = set()
    for book in books:
        # 이미 13자리면 스킵
        if book.isbn and len(book.isbn) == 13:
            isbn13 = book.isbn
        else:
            # 알라딘에서 isbn13 조회
            info = fetch_book_info_by_isbn(book.isbn)
            if info and info.get('isbn13'):
                isbn13 = info['isbn13']
            else:
                continue
        # 중복 ISBN13 처리
        if isbn13 in seen_isbn13 or db.query(Book).filter(Book.isbn == isbn13, Book.id != book.id).first():
            print(f"[삭제] {book.title}: {book.isbn} -> {isbn13} (중복)")
            db.delete(book)
            deleted += 1
        else:
            if book.isbn != isbn13:
                print(f"{book.title}: {book.isbn} -> {isbn13}")
                book.isbn = isbn13
                updated += 1
            seen_isbn13.add(isbn13)
    db.commit()
    db.close()
    print(f"총 {updated}권의 isbn이 13자리로 업데이트됨. {deleted}권 삭제됨.")

if __name__ == "__main__":
    update_all_books_to_isbn13()
