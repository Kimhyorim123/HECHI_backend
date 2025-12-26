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

def update_books_isbn13():
    db = SessionLocal()
    books = db.query(Book).all()
    updated = 0
    skipped = 0
    for book in books:
        if book.isbn_13 and len(book.isbn_13) == 13:
            continue
        isbn_10 = book.isbn_10
        if not isbn_10:
            skipped += 1
            continue
        if len(isbn_10) == 13:
            book.isbn_13 = isbn_10
            updated += 1
            print(f"{book.title}: {isbn_10} -> {book.isbn_13} (already 13)")
            continue
        info = fetch_book_info_by_isbn(isbn_10)
        if info and info.get('isbn13'):
            book.isbn_13 = info['isbn13']
            updated += 1
            print(f"{book.title}: {isbn_10} -> {book.isbn_13}")
        else:
            skipped += 1
            print(f"[SKIP] {book.title}: {isbn_10}")
    db.commit()
    db.close()
    print(f"총 {updated}권의 isbn_13이 업데이트됨. {skipped}권 스킵됨.")

if __name__ == "__main__":
    update_books_isbn13()
