# 알라딘 장르별 카테고리ID 매핑
aladin_genre_category = {
    '소설': 1,
    '시': 3,
    '에세이': 55889,
    '만화': 2551,
    '추리': 2553,
    '스릴러/공포': 2555,
    'SF': 2557,
    '판타지': 2557,
    '로맨스': 2559,
    '액션': 2551,  # 만화 내 액션/무협 등
    '역사': 74,
    '과학': 987,
    '인문': 656,
    '철학': 51346,
    '사회/정치': 798,
    '경제/경영': 170,
    '자기계발': 336,
    '예술': 517,
    '여행': 1196,
    '취미': 1383,
}
import os
import requests
from dotenv import load_dotenv
from datetime import datetime
from app.models import Book, Author, BookAuthor, BookCategory
from app.database import SessionLocal

# 환경변수 로드
def get_api_key():
    load_dotenv()
    return os.environ.get("ALADIN_API_KEY")

# 알라딘 API에서 리스트 가져오기
def fetch_aladin_list(list_type, max_results=20, category_id=0):
    api_key = get_api_key()
    url = "https://www.aladin.co.kr/ttb/api/ItemList.aspx"
    params = {
        "ttbkey": api_key,
        "QueryType": list_type,
        "MaxResults": max_results,
        "Cover": "Big",
        "output": "js",
        "Version": "20131101",
        "CategoryId": category_id,
        "SearchTarget": "Book"  # 도서만 대상으로 지정
    }
    print(f"[DEBUG] API KEY: {api_key}")
    print(f"[DEBUG] Request URL: {url}")
    print(f"[DEBUG] Request Params: {params}")
    response = requests.get(url, params=params)
    response.encoding = 'utf-8'
    print(f"[DEBUG] Response Status: {response.status_code}")
    print(f"[DEBUG] Response Text: {response.text[:1000]}")  # 1000자까지만 출력
    response.raise_for_status()
    try:
        items = response.json().get('item', [])
    except Exception as e:
        print(f"[ERROR] JSON decode error: {e}")
        items = []
    return items

# DB에 저장 함수들
def upsert_book(item, db):
    isbn = item.get('isbn13')
    book = db.query(Book).filter_by(isbn=isbn).first()
    if not book:
        total_pages = None
        # 알라딘 API에서 subInfo.itemPage에 페이지 정보가 있을 수 있음
        if 'subInfo' in item and 'itemPage' in item['subInfo']:
            try:
                total_pages = int(item['subInfo']['itemPage'])
            except Exception:
                total_pages = None
        book = Book(
            isbn=isbn,
            title=item.get('title'),
            publisher=item.get('publisher'),
            category=item.get('categoryName'),
            published_date=item.get('pubDate'),
            total_pages=total_pages,
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

def link_book_category(book_id, category, db):
    if not db.query(BookCategory).filter_by(book_id=book_id, category_name=category).first():
        db.add(BookCategory(book_id=book_id, category_name=category))
        db.commit()

def save_book_list(isbn, list_type, rank, list_date, db):
    from app.models import BookList
    # 이미 있으면 update, 없으면 insert
    obj = db.query(BookList).filter_by(isbn=isbn, list_type=list_type, list_date=list_date).first()
    if obj:
        obj.rank = rank
    else:
        obj = BookList(isbn=isbn, list_type=list_type, rank=rank, list_date=list_date)
        db.add(obj)
    db.commit()

if __name__ == "__main__":
    db = SessionLocal()
    today = datetime.today().date()
    # 장르별 베스트셀러 20권씩 수집
    for genre, category_id in aladin_genre_category.items():
        print(f"[INFO] Fetching bestseller for genre: {genre} (CategoryId: {category_id})")
        items = fetch_aladin_list("Bestseller", max_results=20, category_id=category_id)
        print(f"[INFO] {genre} - {len(items)} items fetched")
        for rank, item in enumerate(items, start=1):
            try:
                print(f"[INFO] Try to save book: {item.get('title')} (ISBN13: {item.get('isbn13')})")
                book = upsert_book(item, db)
                print(f"[SUCCESS] Book saved: {book.title} (ISBN13: {book.isbn})")
                # 저자 저장 및 연결
                for author_name in item.get('author', '').split(','):
                    author = upsert_author(author_name.strip(), db)
                    link_book_author(book.id, author.id, db)
                # 카테고리 저장 및 연결
                for category in item.get('categoryName', '').split('>'):
                    link_book_category(book.id, category.strip(), db)
                # 리스트 저장 (list_type에 genre명 포함)
                save_book_list(book.isbn, f"bestseller_{genre}", rank, today, db)
            except Exception as e:
                print(f"[ERROR] Failed to save book: {item.get('title')} (ISBN: {item.get('isbn')}) - {e}")
    db.close()
