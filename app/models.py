
from datetime import date
import enum

from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Text,
    Date,
    DateTime,
    Boolean,
    ForeignKey,
    Enum,
    Float,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.dialects.mysql import JSON  # MySQL JSON 타입

Base = declarative_base()

# BookList 모델 정의(Base 선언 이후)
class BookList(Base):
    __tablename__ = "book_lists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    isbn = Column(String(13), ForeignKey("books.isbn_10", ondelete="CASCADE"), nullable=False)
    list_type = Column(String(50), nullable=False)  # 예: bestseller_all, new_all
    rank = Column(Integer, nullable=False)
    list_date = Column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("isbn", "list_type", name="uq_booklist_isbn_type"),
    )

Base = declarative_base()

# =========================
# Enum 정의
# =========================


class ProfileVisibility(str, enum.Enum):
    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    FRIEND_ONLY = "FRIEND_ONLY"


class ReadingStatus(str, enum.Enum):
    PENDING = "PENDING"      # 아직 시작 안 함
    READING = "READING"      # 읽는 중
    PAUSED = "PAUSED"        # 일시 중단
    COMPLETED = "COMPLETED"  # 완독
    ARCHIVED = "ARCHIVED"    # 보관


class AIJobType(str, enum.Enum):
    SUMMARY = "SUMMARY"
    RECOMMENDATION = "RECOMMENDATION"
    SPOILER_CHECK = "SPOILER_CHECK"


class AIJobStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


class GroupRole(str, enum.Enum):
    MEMBER = "MEMBER"
    LEADER = "LEADER"


class NotificationType(str, enum.Enum):
    AI_SUMMARY_READY = "AI_SUMMARY_READY"
    GROUP_NOTICE = "GROUP_NOTICE"
    GENERAL = "GENERAL"


class InquiryCategory(str, enum.Enum):
    GENERAL = "GENERAL"
    BUG = "BUG"
    FEATURE = "FEATURE"
    OTHER = "OTHER"


# =========================
# User / Author / Book
# =========================


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255), nullable=False)

    name = Column(String(100), nullable=False)
    nickname = Column(String(100), nullable=False)
    # 관리자 여부 (운영용)
    is_admin = Column(Boolean, nullable=False, default=False)
    # 사용자 소개글
    description = Column(Text, nullable=True)
    taste_analyzed = Column(Boolean, nullable=False, default=False)
    profile_visibility = Column(
        Enum(ProfileVisibility),
        nullable=False,
        default=ProfileVisibility.PUBLIC,
    )

    # 지금은 기기 1대만 가정 → fcm_token을 User에 직접 둠
    fcm_token = Column(String(255), nullable=True)

    # 취향 분석 완료 여부
    taste_analyzed = Column(Boolean, nullable=False, default=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 관계
    user_books = relationship(
        "UserBook",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reviews = relationship(
        "Review",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    inquiries = relationship(
        "Inquiry",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    notifications = relationship(
        "Notification",
        back_populates="user",
        cascade="all, delete-orphan",
    )
    group_memberships = relationship(
        "GroupMember",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class Author(Base):
    __tablename__ = "authors"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    job_title = Column(String(255), nullable=True)
    biography = Column(Text, nullable=True)

    books = relationship(
        "BookAuthor",
        back_populates="author",
        cascade="all, delete-orphan",
    )


class Book(Base):
    __tablename__ = "books"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 반드시 수정: ISBN은 INT가 아니라 문자열로
    isbn_10 = Column(String(13), unique=True, nullable=True)
    isbn_13 = Column(String(13), nullable=True)

    title = Column(String(255), nullable=False)
    publisher = Column(String(255), nullable=True)
    published_date = Column(Date, nullable=True)
    language = Column(String(50), nullable=True)
    category = Column(String(255), nullable=True)
    total_pages = Column(Integer, nullable=True)
    nfc_uid = Column(String(255), nullable=True)
    # New fields
    thumbnail = Column(String(512), nullable=True)
    small_thumbnail = Column(String(512), nullable=True)
    google_rating = Column(Float, nullable=True)
    google_ratings_count = Column(Integer, nullable=True)
    description = Column(Text, nullable=True)

    # 관계
    authors = relationship(
        "BookAuthor",
        back_populates="book",
        cascade="all, delete-orphan",
    )
    user_books = relationship("UserBook", back_populates="book")
    reviews = relationship("Review", back_populates="book")


 
# =========================
# 고객센터: FAQ / SupportTicket
# =========================


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(String(255), nullable=False)
    answer = Column(Text, nullable=False)
    is_pinned = Column(Boolean, nullable=False, default=True)


class SupportTicketStatus(str, enum.Enum):
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # 첨부 파일 URL (S3/CDN 또는 서버 정적 경로)
    attachment_url = Column(String(1024), nullable=True)
    # 운영진 답변(선택)
    reply = Column(Text, nullable=True)
    # 운영진 답변 메타
    responded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    status = Column(Enum(SupportTicketStatus), nullable=False, default=SupportTicketStatus.OPEN)

    user = relationship("User", foreign_keys=[user_id])
    responder = relationship("User", foreign_keys=[responded_by])


class SupportTicketAction(str, enum.Enum):
    CREATE = "CREATE"
    ANSWER_ADD = "ANSWER_ADD"
    ANSWER_UPDATE = "ANSWER_UPDATE"
    ANSWER_DELETE = "ANSWER_DELETE"
    STATUS_CHANGE = "STATUS_CHANGE"


class SupportTicketLog(Base):
    __tablename__ = "support_ticket_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False)
    actor_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    action = Column(Enum(SupportTicketAction), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


class SupportTicketAnswerHistory(Base):
    __tablename__ = "support_ticket_answer_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(Integer, ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False)
    responder_user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    answer_text = Column(Text, nullable=False)
    answered_at = Column(DateTime, server_default=func.now(), nullable=False)
    # responder 관계는 선택적
    # 명시적 관계가 필요하면 주석 해제
    # responder = relationship("User", foreign_keys=[responded_by])


# =========================
# 순위/통계 대비: 검색/위시/조회
# =========================


class SearchHistory(Base):
    __tablename__ = "search_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    query = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# =========================
# SearchQueryStat: 전역 검색어 집계 (개인 기록과 분리)
# =========================

class SearchQueryStat(Base):
    __tablename__ = "search_query_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(255), nullable=False, unique=True)
    total_count = Column(Integer, nullable=False, default=0)
    last_hit_at = Column(DateTime, nullable=False, server_default=func.now())
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)


class Wishlist(Base):
    __tablename__ = "wishlist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    wishlist_at = Column(DateTime, nullable=True)  # 위시리스트 추가 시점

    __table_args__ = (
        UniqueConstraint("user_id", "book_id", name="uq_wishlist_user_book"),
    )


class BookView(Base):
    __tablename__ = "book_views"

    id = Column(Integer, primary_key=True, autoincrement=True)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)


# 다대다: Book - Author
class BookAuthor(Base):
    __tablename__ = "book_authors"

    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
    )
    author_id = Column(
        Integer,
        ForeignKey("authors.id", ondelete="CASCADE"),
        primary_key=True,
    )

    book = relationship("Book", back_populates="authors")
    author = relationship("Author", back_populates="books")


# 다대다: Book - Category (여러 카테고리 저장)
class BookCategory(Base):
    __tablename__ = "book_categories"

    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
    )
    category_name = Column(String(191), primary_key=True)


# =========================
# UserBook (책 단위 독서 상태)
# =========================


class UserBook(Base):
    __tablename__ = "user_books"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )

    status = Column(
        Enum(ReadingStatus),
        nullable=False,
        default=ReadingStatus.PENDING,
    )
    is_life_book = Column(Boolean, nullable=False, default=False)

    # 책 전체 기준 시작/완독 날짜 (상태 변경 시 기록)
    started_date = Column(Date, nullable=True)
    finished_date = Column(Date, nullable=True)
    started_at = Column(DateTime, nullable=True)  # 읽는 중 상태 진입 시
    completed_at = Column(DateTime, nullable=True)  # 완독 상태 진입 시

    # 전체 누적 독서 시간(초 단위, 선택)
    total_reading_seconds = Column(Integer, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # 관계
    user = relationship("User", back_populates="user_books")
    book = relationship("Book", back_populates="user_books")

    pages = relationship(
        "UserPage",
        back_populates="user_book",
        cascade="all, delete-orphan",
    )
    notes = relationship(
        "Note",
        back_populates="user_book",
        cascade="all, delete-orphan",
    )
    highlights = relationship(
        "Highlight",
        back_populates="user_book",
        cascade="all, delete-orphan",
    )
    bookmarks = relationship(
        "Bookmark",
        back_populates="user_book",
        cascade="all, delete-orphan",
    )
    reviews = relationship(
        "Review",
        back_populates="user_book",
        cascade="all, delete-orphan",
    )


# =========================
# UserPage (날짜별 읽기 구간)
# =========================
# 사용자가 "그날" 언제부터 언제까지, 몇 페이지 읽었는지 기록
# → 날짜별 통계/시각화에 사용


class UserPage(Base):
    __tablename__ = "user_pages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_book_id = Column(
        Integer,
        ForeignKey("user_books.id", ondelete="CASCADE"),
        nullable=False,
    )

    reading_date = Column(Date, nullable=False)  # 그날 날짜 (YYYY-MM-DD)
    start_page = Column(Integer, nullable=False)
    end_page = Column(Integer, nullable=False)

    # 하루 중 독서 시작/종료 시각 (시간까지 보고 싶으면)
    start_time = Column(DateTime, nullable=True)
    end_time = Column(DateTime, nullable=True)

    # 당일 총 소요 시간(초 단위, 선택)
    reading_seconds = Column(Integer, nullable=True)

    user_book = relationship("UserBook", back_populates="pages")

    __table_args__ = (
        # 한 UserBook에서 같은 날짜에 여러 레코드가 필요하면 제거해도 됨
        UniqueConstraint(
            "user_book_id",
            "reading_date",
            name="uq_userpage_userbook_date",
        ),
    )


# =========================
# 메모 / 하이라이트 / 북마크
# - 날짜만 기록(시간 X) → Date 사용
# =========================


class Note(Base):
    __tablename__ = "notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_book_id = Column(
        Integer,
        ForeignKey("user_books.id", ondelete="CASCADE"),
        nullable=False,
    )

    page = Column(Integer, nullable=True)
    content = Column(Text, nullable=False)
    created_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    user_book = relationship("UserBook", back_populates="notes")


class Highlight(Base):
    __tablename__ = "highlights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_book_id = Column(
        Integer,
        ForeignKey("user_books.id", ondelete="CASCADE"),
        nullable=False,
    )

    page = Column(Integer, nullable=False)
    sentence = Column(Text, nullable=False)
    memo = Column(Text, nullable=True)
    is_public = Column(Boolean, nullable=False, default=False)
    created_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    user_book = relationship("UserBook", back_populates="highlights")


class Bookmark(Base):
    __tablename__ = "bookmarks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_book_id = Column(
        Integer,
        ForeignKey("user_books.id", ondelete="CASCADE"),
        nullable=False,
    )

    page = Column(Integer, nullable=False)
    memo = Column(Text, nullable=True)
    created_date = Column(DateTime, nullable=False, default=datetime.utcnow)

    user_book = relationship("UserBook", back_populates="bookmarks")


# =========================
# 리뷰
# =========================


class Review(Base):
    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_book_id = Column(
        Integer,
        ForeignKey("user_books.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        nullable=False,
    )

    rating = Column(Float, nullable=True)
    content = Column(Text, nullable=True)

    # 좋아요 단순 카운트 (per-user isLiked는 제거)
    like_count = Column(Integer, nullable=False, default=0)

    is_spoiler = Column(Boolean, nullable=False, default=False)

    # 날짜만 저장
    created_date = Column(Date, nullable=False, default=date.today)

    user_book = relationship("UserBook", back_populates="reviews")
    user = relationship("User", back_populates="reviews")
    book = relationship("Book", back_populates="reviews")
    likes = relationship(
        "ReviewLike",
        back_populates="review",
        cascade="all, delete-orphan",
    )
    comments = relationship(
        "ReviewComment",
        back_populates="review",
        cascade="all, delete-orphan",
    )


class ReviewLike(Base):
    __tablename__ = "review_likes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    wishlist_at = Column(DateTime, nullable=True)  # 위시리스트 추가 시점

    review = relationship("Review", back_populates="likes")

    __table_args__ = (
        UniqueConstraint("review_id", "user_id", name="uq_review_like_user"),
    )


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(Integer, ForeignKey("reviews.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, nullable=True)

    review = relationship("Review", back_populates="comments")


# =========================
# 그룹 / 모임
# =========================


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)

    is_private = Column(Boolean, nullable=False, default=False)
    code = Column(String(50), nullable=True)       # 비공개 코드
    password = Column(String(255), nullable=True)  # 비공개용 비밀번호

    leader_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    members = relationship(
        "GroupMember",
        back_populates="group",
        cascade="all, delete-orphan",
    )
    monthly_books = relationship(
        "GroupMonthlyBook",
        back_populates="group",
        cascade="all, delete-orphan",
    )


class GroupMember(Base):
    __tablename__ = "group_members"

    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )

    role = Column(
        Enum(GroupRole),
        nullable=False,
        default=GroupRole.MEMBER,
    )
    joined_at = Column(DateTime, server_default=func.now(), nullable=False)

    group = relationship("Group", back_populates="members")
    user = relationship("User", back_populates="group_memberships")


class GroupMonthlyBook(Base):
    __tablename__ = "group_monthly_books"

    group_id = Column(
        Integer,
        ForeignKey("groups.id", ondelete="CASCADE"),
        primary_key=True,
    )
    book_id = Column(
        Integer,
        ForeignKey("books.id", ondelete="CASCADE"),
        primary_key=True,
    )

    month = Column(String(7), nullable=False)  # 예: "2025-11"

    group = relationship("Group", back_populates="monthly_books")
    book = relationship("Book")


# =========================
# 문의 / AI Job / 알림
# =========================


class Inquiry(Base):
    __tablename__ = "inquiries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    title = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    category = Column(
        Enum(InquiryCategory),
        nullable=False,
        default=InquiryCategory.GENERAL,
    )

    created_date = Column(Date, nullable=False, default=date.today)
    reply = Column(Text, nullable=True)

    user = relationship("User", back_populates="inquiries")


class AIJob(Base):
    __tablename__ = "ai_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    job_type = Column(Enum(AIJobType), nullable=False)
    status = Column(
        Enum(AIJobStatus),
        nullable=False,
        default=AIJobStatus.PENDING,
    )

    # 어떤 대상에 대한 작업인지 (세션/책/유저 등)
    target_type = Column(String(50), nullable=True)
    target_id = Column(Integer, nullable=True)

    # 프롬프트/조건 등 입력 데이터
    payload = Column(JSON, nullable=True)

    # OpenAI 결과 등
    result = Column(JSON, nullable=True)

    attempt = Column(Integer, nullable=False, default=0)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    type = Column(
        Enum(NotificationType),
        nullable=False,
        default=NotificationType.GENERAL,
    )
    title = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    data = Column(JSON, nullable=True)

    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="notifications")


# =========================
# 추가: UserInsight (임시 AI 분석/태그 저장)
# =========================


class UserInsight(Base):
    __tablename__ = "user_insights"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)

    # 임시 분석 텍스트(나중에 AI 결과로 대체 예정)
    analysis_text = Column(Text, nullable=True)

    # 태그 + 가중치 리스트(JSON)
    # 예: [{"label": "힐링", "weight": 0.92}, ...]
    tags = Column(JSON, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User")


# =========================
# 추가: Device / ReadingSession / ReadingEvent / FCMToken
# =========================


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    ble_ideSntifier = Column(String(255), nullable=False, unique=True)  # 디바이스 고유 BLE ID
    registered_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User")


class ReadingSession(Base):
    __tablename__ = "reading_sessions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    book_id = Column(Integer, ForeignKey("books.id", ondelete="CASCADE"), nullable=False)

    start_time = Column(DateTime, nullable=False, server_default=func.now())
    end_time = Column(DateTime, nullable=True)

    start_page = Column(Integer, nullable=True)
    end_page = Column(Integer, nullable=True)
    total_seconds = Column(Integer, nullable=True)

    created_at = Column(DateTime, server_default=func.now(), nullable=False)

    user = relationship("User")
    book = relationship("Book")
    events = relationship("ReadingEvent", back_populates="session", cascade="all, delete-orphan")


class ReadingEventType(str, enum.Enum):
    START = "START"
    PAGE_TURN = "PAGE_TURN"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    END = "END"


class ReadingEvent(Base):
    __tablename__ = "reading_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(Integer, ForeignKey("reading_sessions.id", ondelete="CASCADE"), nullable=False)
    event_type = Column(Enum(ReadingEventType), nullable=False)
    page = Column(Integer, nullable=True)
    occurred_at = Column(DateTime, nullable=False, server_default=func.now())

    session = relationship("ReadingSession", back_populates="events")


class FCMToken(Base):
    __tablename__ = "fcm_tokens"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    token = Column(String(255), nullable=False, unique=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User")


# =========================
# UserTaste (초기 취향 분석 결과 저장)
# =========================

class UserTaste(Base):
    __tablename__ = "user_tastes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    # 다중 선택 카테고리 (소설, 시, 에세이, 만화 등)
    categories = Column(JSON, nullable=False)
    # 다중 선택 장르 (추리, 코미디, SF, 판타지, 로맨스 등)
    genres = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    user = relationship("User")
