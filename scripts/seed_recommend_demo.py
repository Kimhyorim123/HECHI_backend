from datetime import datetime, timedelta
import random

from app.database import SessionLocal
from app.models import Book, Review, SearchHistory, User

POPULAR_KEYWORDS = [
    "Harry Potter",
    "Lord of the Rings",
    "The Hobbit",
    "1984",
    "Pride and Prejudice",
    "To Kill a Mockingbird",
    "The Great Gatsby",
    "The Catcher in the Rye",
    "The Little Prince",
    "Moby Dick",
]

# Choose some well-known book title substrings to match existing books
TITLE_CANDIDATES = [
    "Harry", "Potter", "Lord", "Rings", "Hobbit", "1984",
    "Pride", "Prejudice", "Mockingbird", "Gatsby", "Prince", "Moby"
]


def seed():
    db = SessionLocal()
    try:
        # Pick or create a demo user for reviews/searches
        user = db.query(User).filter(User.email == "searchtest@example.com").first()
        if not user:
            # If test user not present, pick any user
            user = db.query(User).first()
        if not user:
            print("No user available to attach reviews/search; aborting.")
            return

        # Find candidate books by title keywords
        books = (
            db.query(Book)
            .filter(
                (
                    Book.title.ilike("%" + TITLE_CANDIDATES[0] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[1] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[2] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[3] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[4] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[5] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[6] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[7] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[8] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[9] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[10] + "%")
                    | Book.title.ilike("%" + TITLE_CANDIDATES[11] + "%")
                )
            )
            .limit(20)
            .all()
        )
        if not books:
            print("No candidate books found; try importing more metadata first.")
            return

        now = datetime.utcnow()
        since = now - timedelta(days=30)

        # Seed reviews: multiple entries with ratings for popularity
        for b in books:
            # Randomly decide number of reviews 1..5
            nreviews = random.randint(2, 6)
            for _ in range(nreviews):
                r = Review(
                    user_id=user.id,
                    book_id=b.id,
                    rating=random.choice([3,4,5]),
                    comment="Demo review",
                    created_date=random.choice([
                        since.date(), (since + timedelta(days=random.randint(1, 28))).date(), now.date()
                    ]),
                )
                db.add(r)
        db.commit()
        print(f"Inserted demo reviews for {len(books)} books.")

        # Seed search history using popular keywords
        for kw in POPULAR_KEYWORDS:
            # Randomly repeat searches
            for _ in range(random.randint(3, 8)):
                sh = SearchHistory(
                    user_id=user.id,
                    query=kw,
                    created_at=since + timedelta(days=random.randint(0, 28), seconds=random.randint(0, 86400)),
                )
                db.add(sh)
        db.commit()
        print("Inserted demo search history.")

    finally:
        db.close()


if __name__ == "__main__":
    seed()
