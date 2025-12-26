from app.database import SessionLocal
from app.models import ReadingSession, ReadingEvent

def check_reading_sessions():
    db = SessionLocal()
    print("[ReadingSession] start_page IS NULL OR 0, end_page IS NULL OR 0:")
    sessions = db.query(ReadingSession).filter(
        (ReadingSession.start_page == None) | (ReadingSession.start_page == 0) |
        (ReadingSession.end_page == None) | (ReadingSession.end_page == 0)
    ).all()
    for s in sessions:
        print(f"id={s.id}, user_id={s.user_id}, book_id={s.book_id}, start_page={s.start_page}, end_page={s.end_page}")
    db.close()

def check_reading_events():
    db = SessionLocal()
    print("[ReadingEvent] page IS NULL OR 0:")
    events = db.query(ReadingEvent).filter(
        (ReadingEvent.page == None) | (ReadingEvent.page == 0)
    ).all()
    for e in events:
        print(f"id={e.id}, session_id={e.session_id}, event_type={e.event_type}, page={e.page}")
    db.close()

if __name__ == "__main__":
    check_reading_sessions()
    check_reading_events()
