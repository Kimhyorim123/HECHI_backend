

import os
import requests
from dotenv import load_dotenv
from app.models import Book, BookList
from app.database import SessionLocal

def get_api_key():
    load_dotenv()
    return os.environ.get("ALADIN_API_KEY")

def fetch_isbn13_from_aladin(isbn):
    api_key = get_api_key()
    url = "https://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
    params = {
        "ttbkey": api_key,
        "itemIdType": "ISBN",
        "ItemId": isbn,
        "output": "js",
        "Version": "20131101"
    }
    try:
        r = requests.get(url, params=params, timeout=10)
        r.encoding = "utf-8"
        r.raise_for_status()
        items = r.json().get("item", [])
        if items and items[0].get("isbn13"):
            return items[0]["isbn13"]
    except Exception as e:
        print(f"[ERROR] 알라딘 API 실패: {isbn} - {e}")
    return None

def sync_booklist_isbn_to_13():
    db = SessionLocal()
    updated = 0
    skipped = 0
    # (isbn13, list_type) -> BookList id 리스트
    merge_map = {}
    all_lists = db.query(BookList).all()
    for bl in all_lists:
        # isbn13 변환
        isbn13 = bl.isbn if bl.isbn and len(bl.isbn) == 13 else fetch_isbn13_from_aladin(bl.isbn)
        if not isbn13:
            skipped += 1
            print(f"[SKIP] BookList id={bl.id} isbn={bl.isbn} (알라딘 변환 불가)")
            continue
        # books 테이블에 isbn13이 실제로 존재하는지 확인
        book = db.query(Book).filter(Book.isbn == isbn13).first()
        if not book:
            skipped += 1
            print(f"[SKIP] BookList id={bl.id} isbn={bl.isbn} → isbn13={isbn13} (books에 없음)")
            continue
        key = (isbn13, bl.list_type)
        if key not in merge_map:
            # 첫 번째 row만 남기고
            merge_map[key] = bl
            old = bl.isbn
            bl.isbn = isbn13
            updated += 1
            print(f"[UPDATE] BookList id={bl.id} {old} -> {bl.isbn}")
        else:
            # 중복 row는 삭제
            db.delete(bl)
            skipped += 1
            print(f"[DUPLICATE-DELETE] BookList id={bl.id} isbn13={isbn13} (중복, id={merge_map[key].id}만 남김)")
    db.commit()
    db.close()
    print(f"총 {updated}건 동기화, {skipped}건 스킵")

if __name__ == "__main__":
    sync_booklist_isbn_to_13()

if __name__ == "__main__":
    sync_booklist_isbn_to_13()
