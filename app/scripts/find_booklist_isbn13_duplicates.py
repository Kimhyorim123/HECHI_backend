# 변환 후 (isbn13, list_type) 기준으로 중복이 생길 row를 미리 탐지하는 스크립트
# 실행: python3 app/scripts/find_booklist_isbn13_duplicates.py

from app.models import BookList
from app.database import SessionLocal
from app.scripts.sync_booklist_isbn13 import fetch_isbn13_from_aladin
from collections import defaultdict


def main():
    db = SessionLocal()
    # (isbn13, list_type) -> [BookList row list]
    isbn13_type_map = defaultdict(list)
    all_lists = db.query(BookList).all()
    for bl in all_lists:
        # 이미 13자리면 그대로, 아니면 변환
        isbn13 = bl.isbn if bl.isbn and len(bl.isbn) == 13 else fetch_isbn13_from_aladin(bl.isbn)
        if not isbn13:
            continue
        isbn13_type_map[(isbn13, bl.list_type)].append(bl)

    # 2개 이상인 조합만 출력
    print("[isbn13, list_type] 기준 변환 후 중복 예상 목록:")
    found = False
    for (isbn13, list_type), rows in isbn13_type_map.items():
        if len(rows) > 1:
            found = True
            print(f"isbn13={isbn13}, list_type={list_type}, count={len(rows)}")
            for bl in rows:
                print(f"  id={bl.id}, 원래 isbn={bl.isbn}")
    if not found:
        print("변환 후 중복될 조합이 없습니다.")
    db.close()

if __name__ == "__main__":
    main()
