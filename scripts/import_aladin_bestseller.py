import os
import requests
import pymysql
from datetime import datetime
from dotenv import load_dotenv

# 환경변수 로드
load_dotenv()
ALADIN_API_KEY = os.getenv("ALADIN_API_KEY")

# DB 연결 정보 (예시, 실제 환경에 맞게 수정)
DB_HOST = "db"
DB_USER = "root"
DB_PASSWORD = "09150809k!"
DB_NAME = "bookstopper"

# 알라딘 베스트셀러 API URL
API_URL = f"https://www.aladin.co.kr/ttb/api/ItemList.aspx?ttbkey={ALADIN_API_KEY}&QueryType=Bestseller&MaxResults=50&start=1&SearchTarget=Book&output=js&Version=20131101"

headers = {"User-Agent": "Mozilla/5.0"}
response = requests.get(API_URL, headers=headers)
print('API response:', response.text[:1000])  # 응답 앞부분 출력
try:
    data = response.json()
except Exception as e:
    print('JSON decode error:', e)
    data = {}
items = data.get("item", [])
print(f"Parsed {len(items)} items from API response.")

conn = pymysql.connect(host=DB_HOST, user=DB_USER, password=DB_PASSWORD, database=DB_NAME, charset="utf8mb4")
cursor = conn.cursor()

for rank, item in enumerate(items, start=1):
    isbn = item.get("isbn13")
    title = item.get("title")
    author = item.get("author")
    publisher = item.get("publisher")
    category = item.get("categoryName")
    published_date = item.get("pubDate")
    thumbnail = item.get("cover")
    description = item.get("description")

    # books 테이블에 upsert
    cursor.execute(
        """
        INSERT INTO books (isbn, title, publisher, category, published_date, thumbnail, description)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE title=%s, publisher=%s, category=%s, published_date=%s, thumbnail=%s, description=%s
        """,
        (isbn, title, publisher, category, published_date, thumbnail, description,
         title, publisher, category, published_date, thumbnail, description)
    )

    # book_lists 테이블에 insert
    today = datetime.today().date()
    now = datetime.now()
    cursor.execute(
        """
        INSERT INTO book_lists (isbn, list_type, rank, list_date, created_at)
        VALUES (%s, %s, %s, %s, %s)
        """,
        (isbn, "bestseller_all", rank, today, now)
    )

conn.commit()
cursor.close()
conn.close()

print(f"Imported {len(items)} bestseller books from Aladin.")
