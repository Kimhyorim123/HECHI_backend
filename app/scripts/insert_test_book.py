import os
import requests
from dotenv import load_dotenv
from app.models import Book
from app.database import SessionLocal

# 환경변수 로드
def get_api_key():
    load_dotenv()
    return os.environ.get("ALADIN_API_KEY")

# 알라딘 API에서 특정 책 검색
def fetch_book_by_title_author(title, author):
    api_key = get_api_key()
    url = "https://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
    params = {
        "ttbkey": api_key,
        "Query": title,
        "Author": author,
        "MaxResults": 10,
        "Cover": "Big",
        "output": "js",
        "Version": "20131101"
    }
    response = requests.get(url, params=params)
    response.encoding = 'utf-8'  # 한글 인코딩 명시
    response.raise_for_status()
    return response.json().get('item', [])

# DB에 저장
def save_book_to_db(book_data):
    db = SessionLocal()
    isbn = book_data.get('isbn13')
    title = book_data.get('title')
    publisher = book_data.get('publisher')
    category = book_data.get('categoryName')
    total_pages = None
    if 'subInfo' in book_data and 'itemPage' in book_data['subInfo']:
        try:
            total_pages = int(book_data['subInfo']['itemPage'])
        except Exception:
            total_pages = None
    published_date = book_data.get('pubDate')  # YYYY-MM-DD
    language = book_data.get('language')
    thumbnail = book_data.get('cover')
    small_thumbnail = book_data.get('cover')
    description = book_data.get('description')
    # 이미 존재하는지 확인
    book = db.query(Book).filter_by(isbn=isbn).first()
    if not book:
        book = Book(
            isbn=isbn,
            title=title,
            publisher=publisher,
            category=category,
            total_pages=total_pages,
            published_date=published_date,
            language=language,
            thumbnail=thumbnail,
            small_thumbnail=small_thumbnail,
            description=description
        )
        db.add(book)
        db.commit()
        print(f"저장 완료: {title}")
    else:
        print(f"이미 존재: {title}")
    db.close()

if __name__ == "__main__":
    title = "나무"
    author = "베르나르 베르베르"
    items = fetch_book_by_title_author(title, author)
    # 그림 작가까지 필터링
    for item in items:
        if "뫼비우스" in item.get("author", ""):
            save_book_to_db(item)
            break
    else:
        print("책을 찾을 수 없습니다.")
