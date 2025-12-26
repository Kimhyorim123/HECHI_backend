from app.services.google_books import get_client, map_volume_to_book_fields
from app.database import SessionLocal
from scripts.import_books_by_titles import upsert_book_from_fields

client = get_client()
db = SessionLocal()
try:
    total = 0
    for i in range(0, 500, 40):
        vols = client.by_query_paged('한국', i, 40)
        for v in vols:
            fields = map_volume_to_book_fields(v)
            book = upsert_book_from_fields(db, fields)
            db.commit()
            if book:
                print(f'Imported: {fields.get("title")} -> book_id={book.id}')
                total += 1
    print(f"총 {total}권 저장 완료")
finally:
    db.close()
