import os
import requests
import time
from dotenv import load_dotenv
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine
from app.models import Book

# 환경 변수 로드
env_path = os.path.join(os.path.dirname(__file__), '../.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
ALADIN_API_KEY = os.getenv('ALADIN_API_KEY')
DB_URL = os.getenv('DATABASE_URL', 'mysql+pymysql://root:password@localhost:3306/bookstopper')
engine = create_engine(DB_URL)
Session = sessionmaker(bind=engine)
session = Session()

# 100권의 책 제목 리스트 (줄바꿈 기준)
TITLES = [
    "흔한남매 21",
    "최소한의 삼국지",
    "할매",
    "채식주의자",
    "소년이 온다",
    "김지영, 82년생",
    "인간실격",
    "8 (Eight)",
    "이불 속의 작은 우주",
    "트렌드 코리아 2020",
    "트렌드 코리아 2021",
    "트렌드 코리아 2022",
    "트렌드 코리아 2023",
    "트렌드 코리아 2024",
    "이제, 브런치처럼 살아라",
    "비즈니스 모델의 탄생",
    "초격차",
    "언어의 온도",
    "죽고 싶지만 떡볶이는 먹고 싶어",
    "하버드 상위 1퍼센트의 공부법",
    "완전한 행복",
    "오래된 서점",
    "블루보틀 스토리",
    "연필로 쓰기",
    "아이 엠 어 히어로",
    "파친코",
    "종의 기원",
    "총, 균, 쇠",
    "죽음에 관하여",
    "페스트",
    "그리스인 조르바",
    "신경 끄기의 기술",
    "데미안",
    "연금술사",
    "모모",
    "알라딘과 요술램프",
    "키르케",
    "인간 실격",
    "오늘의 법칙들",
    "어린왕자",
    "우리의 소원은",
    "밤의 여행자들",
    "세대의 기록",
    "삶의 발견",
    "식스 센스",
    "고백",
    "비밀",
    "나미야 잡화점의 기적",
    "달러구트 꿈 백화점",
    "프랑켄슈타인",
    "빨간 머리 앤",
    "연을 쫓는 아이",
    "삶의 기쁨을 찾아서",
    "시인들의 모임",
    "언어의 온도 2",
    "오늘도 무사히",
    "아침의 피아노",
    "빅 픽처",
    "나는 나로 살기로 했다",
    "삶의 의미",
    "내게 무해한 사람",
    "보통의 존재",
    "어제처럼",
    "작은 아씨들",
    "시골빵집에서 …",
    "소확행 에세이",
    "글쓰기의 감각",
    "지금 알고 있는 걸 그때도 알았더라면",
    "서른, 잔치는 끝났다",
    "삶의 법칙",
    "해변의 카프카",
    "1Q84",
    "노르웨이의 숲",
    "백년의 고독",
    "삶과 죽음의 책",
    "카라마조프가의 형제들",
    "레 미제라블",
    "전쟁과 평화",
    "동물 농장",
    "1984",
    "데미안 2",
    "어린 왕자 2",
    "해리 포터 시리즈",
    "반지의 제왕",
    "별의 계승자",
    "설국열차",
    "아몬드",
    "편의점 사람들",
    "나의 Don Quixote",
    "불편한 편의점2",
    "플라밍고의 장소",
    "여름날의 문",
    "초승달의 꿈",
    "사랑과 젊음과",
    "시인들의 연대기",
    "문학과 사랑",
    "청춘의 기록",
    "비밀의 정원",
    "그림자 속의 대화",
    "새벽의 기억",
]

def fetch_aladin_by_title(title):
    url = 'https://www.aladin.co.kr/ttb/api/ItemSearch.aspx'
    params = {
        'ttbkey': ALADIN_API_KEY,
        'Query': title,
        'QueryType': 'Title',
        'MaxResults': 1,
        'start': 1,
        'SearchTarget': 'Book',
        'output': 'js',
        'Version': '20131101',
        'Cover': 'Big',
        'OptResult': 'authors,reviewAvgRating,reviewCount',
    }
    resp = requests.get(url, params=params)
    resp.raise_for_status()
    items = resp.json().get('item', [])
    return items[0] if items else None

def save_book_to_db(book_data):
    isbn = book_data.get('isbn13') or book_data.get('isbn')
    if not isbn:
        return None
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
    for title in TITLES:
        print(f'[{title}] 검색 중...')
        try:
            item = fetch_aladin_by_title(title)
            if not item:
                print('  → 검색 결과 없음')
                continue
            book = save_book_to_db(item)
            if book:
                print('  → 저장 완료')
            else:
                print('  → 이미 존재/저장 실패')
            time.sleep(1)  # API rate limit 방지
        except Exception as e:
            print(f'  [ERROR] {title}: {e}')

if __name__ == '__main__':
    main()
