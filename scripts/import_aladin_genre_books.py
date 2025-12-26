import os
import requests
import time
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from app.models import Book
# from app.database import Base  # Base는 사용하지 않으므로 주석 처리

# 알라딘 API 키 환경변수에서 불러오기
env_path = os.path.join(os.path.dirname(__file__), '../.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
ALADIN_API_KEY = os.getenv('ALADIN_API_KEY')

# DB 연결
DB_URL = os.getenv('DATABASE_URL', 'mysql+pymysql://root:password@localhost:3306/bookstopper')
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
session = Session()

# 장르별 알라딘 API categoryId 매핑 (예시, 실제 ID는 알라딘 문서 참고)
GENRE_CATEGORY_IDS = {
    '추리': '2551',
    '스릴러/공포': '2553',
    'SF': '2555',
    '판타지': '2557',
    '로맨스': '2559',
    '액션': '2561',
    '역사': '656',
    '과학': '987',
    '인문': '51346',
    '철학': '51347',
    '사회/정치': '51348',
    '경제/경영': '170',
    '자기계발': '336',
    '예술': '517',
    '여행': '1196',
    '취미': '55889',
}

# 한 장르당 몇 권 저장할지
BOOKS_PER_GENRE = 20

# 알라딘 API 호출 함수
def fetch_aladin_books(category_id, max_results=20):
    url = 'https://www.aladin.co.kr/ttb/api/ItemList.aspx'
    params = {
        'ttbkey': ALADIN_API_KEY,
        'QueryType': 'Bestseller',
        'MaxResults': max_results,
        'start': 1,
        'SearchTarget': 'Book',
        'output': 'js',
        'Version': '20131101',
        'CategoryId': category_id,
        'Cover': 'Big',
        'OptResult': 'authors,reviewAvgRating,reviewCount',
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    return resp.json().get('item', [])

def save_book_to_db(book_data):
    isbn = book_data.get('isbn13') or book_data.get('isbn')
    if not isbn:
        return None
    # 이미 존재하면 skip
    exists = session.query(Book).filter(Book.isbn == isbn).first()
    if exists:
        return None
    book = Book(
        isbn=isbn,
        title=book_data.get('title'),
        publisher=book_data.get('publisher'),
        published_date=book_data.get('pubDate'),
        language='ko',
        category=book_data.get('categoryName'),
        total_pages=None,
        thumbnail=book_data.get('cover'),
        small_thumbnail=book_data.get('cover'),
        google_rating=None,
        google_ratings_count=None,
        description=book_data.get('description'),
    )
    session.add(book)
    session.commit()
    return book

def main():
    for genre, category_id in GENRE_CATEGORY_IDS.items():
        print(f'[{genre}] 장르 도서 수집 중...')
        try:
            items = fetch_aladin_books(category_id, BOOKS_PER_GENRE)
            count = 0
            for item in items:
                book = save_book_to_db(item)
                if book:
                    count += 1
            print(f'  → {count}권 저장 완료')
            time.sleep(1)  # API rate limit 방지
        except Exception as e:
            print(f'  [ERROR] {genre}: {e}')

if __name__ == '__main__':
    main()
