from datetime import datetime, timezone
from typing import List, Optional, Tuple
import re

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import (
    User,
    SearchHistory,
    BookView,
    Book,
    Review,
    ReadingSession,
    UserInsight,
)
from app.schemas.analytics import RatingSummary
from app.schemas.calendar import CalendarMonthResponse, CalendarDay, CalendarBookItem

router = APIRouter(prefix="/analytics", tags=["analytics"])


# =============================
# Request / Response Schemas
# =============================

class SearchLogRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=255)


class ViewLogRequest(BaseModel):
    book_id: int


class RatingBucket(BaseModel):
    rating: float
    count: int


class GenreStat(BaseModel):
    name: str
    review_count: int
    average_5: float
    average_100: int


class ReadingTime(BaseModel):
    total_seconds: int
    human: str


# ✅ 프론트가 subGenres/topLevelGenres를 기대하므로 반드시 포함
class UserStatsResponse(BaseModel):
    rating_distribution: List[RatingBucket]
    rating_summary: RatingSummary
    reading_time: ReadingTime
    sub_genres: List[GenreStat]
    top_level_genres: List[GenreStat]


# =============================
# Insights (임시)
# =============================

class InsightTag(BaseModel):
    label: str
    weight: float = Field(ge=0.0, le=1.0, description="0~1 가중치")


class UserInsightResponse(BaseModel):
    analysis: str | None = None
    tags: List[InsightTag] = []


class UserInsightUpsert(BaseModel):
    analysis: str | None = None
    tags: List[InsightTag] | None = None


# =============================
# Utils
# =============================

def _humanize_seconds(total: int) -> str:
    if total <= 0:
        return "0시간"
    hours = total // 3600
    minutes = (total % 3600) // 60
    if hours and minutes:
        return f"총 {hours}시간 {minutes}분 감상하였습니다."
    if hours:
        return f"총 {hours}시간 감상하였습니다."
    return f"총 {minutes}분 감상하였습니다."


# =============================
# 장르 정의 (너가 쓰겠다고 한 것만)
# =============================

TOP_LEVEL_GENRES = ["소설", "시", "에세이", "만화"]
SUB_GENRES = [
    "추리",
    "스릴러/공포",
    "SF",
    "판타지",
    "로맨스",
    "액션",
    "역사",
    "과학",
    "인문",
    "철학",
    "사회/정치",
    "경제/경영",
    "자기계발",
    "예술",
    "여행",
    "취미",
]
ALL_ALLOWED_GENRES = TOP_LEVEL_GENRES + SUB_GENRES


# =============================
# 카테고리 → 장르(1대1) 매핑 (토큰 기준)
# - Book.category가 '국내도서>...>...>최하위' 형태이므로
#   "최하위 토큰" 또는 "중간 토큰"이 키로 들어오도록 구성
# =============================

CATEGORY_TO_GENRE_PRIMARY: dict[str, str] = {
    # ---- 소설 계열(토큰) ----
    "1950년대 이후 일본소설": "소설",
    "1950년대 이전 일본소설": "소설",
    "2000년대 이전 한국소설": "소설",
    "2000년대 이후 한국소설": "소설",
    "독일소설": "소설",
    "동유럽소설": "소설",
    "아일랜드소설": "소설",
    "영미소설": "소설",
    "일본소설": "소설",
    "프랑스문학": "소설",
    "프랑스소설": "소설",
    "러시아소설": "소설",
    "스페인/중남미소설": "소설",
    "세계의 소설": "소설",
    "세계의 문학": "소설",
    "기타 국가 소설": "소설",
    "청소년 소설": "소설",
    "문학/논술/고전": "소설",
    "동화/명작/고전": "소설",
    "세계명작": "소설",
    "외국창작동화": "소설",
    "국내창작동화": "만화",  # 사용자 규칙: 어린이/국내창작동화는 만화로 넣었음(학습/아동 컨셉)

    # ---- 희곡/문학 ----
    "소설/시/희곡": "소설",
    "희곡": "소설",
    "외국희곡": "소설",

    # ---- 시 ----
    "시": "시",
    "한국시": "시",
    "외국시": "시",

    # ---- 에세이 ----
    "에세이": "에세이",
    "한국에세이": "에세이",
    "외국에세이": "에세이",
    "여행에세이": "에세이",
    "해외여행에세이": "에세이",
    "독서에세이": "에세이",
    "명사에세이": "에세이",
    "기타 명사에세이": "에세이",
    "방송연예인에세이": "에세이",
    "사진/그림 에세이": "에세이",
    "인문 에세이": "에세이",
    "일본여행 에세이": "에세이",
    "힐링": "에세이",
    "마음 다스리기": "에세이",

    # ---- 만화 ----
    "만화": "만화",
    "만화 일반": "만화",
    "인터넷 연재 만화": "만화",
    "가족만화": "만화",
    "동물만화": "만화",
    "소년만화": "만화",
    "순정만화": "만화",
    "틴에이지 순정": "만화",
    "레이디스 코믹": "만화",
    "본격장르만화": "만화",
    "학습만화": "만화",
    "만화비평/만화이론": "만화",
    "그래픽노블": "만화",
    "스포츠만화": "만화",
    "어린이": "만화",
    "TV/만화/영화": "만화",  # 토큰 자체는 만화/영화지만, 사용자 규칙상 만화로 두어도 무방

    # ---- 추리/스릴러 ----
    "추리/미스터리": "추리",
    "추리/미스터리소설": "추리",
    "한국 추리/미스터리소설": "추리",
    "영미 추리/미스터리소설": "추리",
    "기타국가 추리/미스터리소설": "추리",
    "스릴러 성향 작품": "스릴러/공포",
    "범죄·서스펜스 소설": "추리",
    "호러/스릴러": "스릴러/공포",
    "호러.공포소설": "스릴러/공포",
    "외국 호러.공포소설": "스릴러/공포",
    "액션/스릴러소설": "액션",
    "외국 액션/스릴러소설": "액션",

    # ---- SF/판타지/액션 ----
    "SF/가상사회": "SF",
    "과학소설(SF)": "SF",
    "한국 과학소설": "SF",
    "외국 과학소설": "SF",
    "판타지": "판타지",
    "판타지·환상문학": "판타지",
    "판타지/환상문학": "판타지",
    "한국판타지/환상소설": "판타지",
    "외국판타지/환상소설": "판타지",
    "액션 판타지": "판타지",
    "드라마틱 판타지": "판타지",
    "무협": "판타지",
    "액션": "액션",

    # ---- 로맨스 ----
    "로맨스소설": "로맨스",
    "한국 로맨스소설": "로맨스",
    "BL": "로맨스",

    # ---- 역사 ----
    "역사": "역사",
    "역사학 일반": "역사",
    "세계사 일반": "역사",
    "한국사": "역사",
    "한국사 일반": "역사",
    "한국근현대사": "역사",
    "일제치하/항일시대": "역사",
    "중국사": "역사",
    "중국사 일반": "역사",
    "중국고대사(선사시대~진한시대)": "역사",
    "세계문화": "역사",
    "문명/문명사": "역사",
    "한국사능력검정시험": "자기계발",  # 시험은 자기계발로

    # ---- 과학 ----
    "과학": "과학",
    "기초과학/교양과학": "과학",
    "물리학": "과학",
    "양자역학": "과학",
    "우주과학": "과학",
    "천문학": "과학",
    "생명과학": "과학",
    "뇌과학": "과학",
    "뇌과학 일반": "과학",
    "뇌과학/인지심리학": "과학",
    "법의학": "과학",
    "인공지능": "과학",
    "인공지능/빅데이터": "과학",
    "인공지능·빅데이터": "과학",
    "그래픽 일반": "취미",  # 컴퓨터/모바일>그래픽 일반 (취미로 두는게 UI상 자연스러움)

    # ---- 인문/철학 ----
    "인문학": "인문",
    "교양 인문학": "인문",
    "상식/교양": "인문",
    "책읽기": "인문",
    "글쓰기": "인문",
    "인류학": "인문",
    "일본문화": "인문",
    "문화연구/문화이론": "인문",
    "교양 심리학": "인문",

    "철학 일반": "철학",
    "교양 철학": "철학",
    "서양철학": "철학",
    "윤리학/도덕철학": "철학",
    "노자철학": "철학",

    # ---- 사회/정치 ----
    "사회과학": "사회/정치",
    "사회과학계열": "사회/정치",
    "사회문제": "사회/정치",
    "사회문제 일반": "사회/정치",
    "사회학": "사회/정치",
    "사회학 일반": "사회/정치",
    "정치학/외교학/행정학": "사회/정치",
    "정치학·외교학·행정학": "사회/정치",
    "세계패권과 국제질서": "사회/정치",
    "여성학/젠더": "사회/정치",
    "여성학이론": "사회/정치",
    "언론/미디어": "사회/정치",
    "언론정보학": "사회/정치",
    "출판/편집": "사회/정치",
    "광고/홍보": "경제/경영",  # 경제/경영 쪽에 더 가까움
    "법과 생활": "사회/정치",
    "헌법": "사회/정치",
    "저작권법": "사회/정치",
    "생활법률 일반": "사회/정치",
    "법률이야기/법조인이야기": "사회/정치",
    "한국사회비평/칼럼": "사회/정치",
    "환경문제": "사회/정치",
    "인권문제": "사회/정치",

    # ---- 경제/경영 ----
    "경제경영": "경제/경영",
    "경영": "경제/경영",
    "경영 일반": "경제/경영",
    "기업 경영": "경제/경영",
    "경제학": "경제/경영",
    "경제일반": "경제/경영",
    "경제이야기": "경제/경영",
    "경제사/경제전망": "경제/경영",
    "한국 경제사/경제전망": "경제/경영",
    "세계 경제사/경제전망": "경제/경영",
    "재테크/투자": "경제/경영",
    "재테크/투자 일반": "경제/경영",
    "주식/펀드": "경제/경영",
    "가상/암호화폐": "경제/경영",
    "마케팅/브랜드": "경제/경영",
    "마케팅/세일즈": "경제/경영",
    "트렌드/미래전망": "경제/경영",
    "트렌드/미래전망 일반": "경제/경영",
    "광고/홍보/PR": "경제/경영",
    "경영전략/혁신": "경제/경영",
    "e-비즈니스/온라인 창업": "경제/경영",
    "e비즈니스/창업": "경제/경영",

    # ---- 자기계발(학습/시험 포함) ----
    "자기계발": "자기계발",
    "시간관리": "자기계발",
    "성공": "자기계발",
    "성공학": "자기계발",
    "성공담": "자기계발",
    "인간관계": "자기계발",
    "기획": "자기계발",
    "기획·보고": "자기계발",
    "협상": "자기계발",
    "창의적사고/두뇌계발": "자기계발",
    "취업/진로/유망직업": "자기계발",
    "국내 진학/취업": "자기계발",
    "수험서/자격증": "자기계발",
    "국가전문자격": "자기계발",
    "민간자격": "자기계발",
    "7/9급 공무원": "자기계발",
    "7/9급 교재": "자기계발",
    "공무원 수험서": "자기계발",
    "공단 수험서": "자기계발",
    "경찰공무원(승진)": "자기계발",
    "토익": "자기계발",
    "Reading": "자기계발",
    "Listening": "자기계발",
    "영어": "자기계발",
    "영어독해": "자기계발",
    "생활영어": "자기계발",
    "일본어": "자기계발",
    "일본어 독해/작문/쓰기": "자기계발",
    "단어/문법/독해 외": "자기계발",

    # ---- 예술 ----
    "예술/대중문화": "예술",
    "예술/대중문화의 이해": "예술",
    "미학/예술이론": "예술",
    "대중문화론": "예술",
    "미술": "예술",
    "미술사": "예술",
    "미술 이야기": "예술",
    "미술 실기": "예술",
    "화집": "예술",
    "음악": "예술",
    "서양음악(클래식)": "예술",
    "클래식": "예술",
    "음악이야기": "예술",
    "음악가": "예술",
    "악보/작곡": "예술",
    "기타/베이스": "취미",
    "영화/드라마": "예술",
    "연출/연기/제작": "예술",
    "시나리오/시나리오작법": "예술",
    "연극/영화": "예술",
    "건축": "예술",
    "건축이론/비평/역사": "예술",

    # ---- 여행 ----
    "여행": "여행",
    "여행 가이드북": "여행",
    "전국여행 가이드북": "여행",
    "일본여행 가이드북": "여행",
    "중국여행 가이드북": "여행",
    "홍콩/대만/마카오여행 가이드북": "여행",

    # ---- 취미 ----
    "요리/살림": "취미",
    "제과제빵": "취미",
    "컬러링북": "취미",
    "취미기타": "취미",
    "기타": "취미",
    "건강정보": "취미",
    "건강에세이/건강정보": "취미",

    # ---- 청소년/좋은부모 등 ----
    "청소년의 진로선택": "자기계발",
    "청소년 인문/사회": "인문",
    "논술참고도서": "인문",
    "교육 일반": "자기계발",
    "학교/학습법": "자기계발",
    "독서/작문 교육": "자기계발",
    "청소년": "인문",
    "좋은부모": "자기계발",

    # ---- 종교 ----
    "불교": "인문",
    "불교명상/수행": "인문",
    "기독교(개신교)": "인문",
    "간증/영적성장": "인문",
    "신학일반": "인문",
    "교회일반": "인문",

    # ---- 유아 ----
    "스티커북": "만화",
}


# ✅ fallback (토큰/전체문자열 둘 다 적용됨)
FALLBACK_RULES: List[Tuple[str, str]] = [
    # 경제/경영
    ("경제경영", "경제/경영"),
    ("경제", "경제/경영"),
    ("경영", "경제/경영"),
    ("재테크", "경제/경영"),
    ("투자", "경제/경영"),
    ("주식", "경제/경영"),
    ("펀드", "경제/경영"),
    ("가상", "경제/경영"),
    ("암호", "경제/경영"),
    ("마케팅", "경제/경영"),
    ("브랜드", "경제/경영"),
    ("세일즈", "경제/경영"),
    ("광고", "경제/경영"),
    ("홍보", "경제/경영"),
    ("PR", "경제/경영"),
    ("트렌드", "경제/경영"),
    ("미래전망", "경제/경영"),
    ("창업", "경제/경영"),
    ("비즈니스", "경제/경영"),

    # 사회/정치
    ("사회과학", "사회/정치"),
    ("사회", "사회/정치"),
    ("정치", "사회/정치"),
    ("외교", "사회/정치"),
    ("행정", "사회/정치"),
    ("법", "사회/정치"),
    ("헌법", "사회/정치"),
    ("저작권", "사회/정치"),
    ("언론", "사회/정치"),
    ("미디어", "사회/정치"),
    ("출판", "사회/정치"),
    ("환경", "사회/정치"),
    ("인권", "사회/정치"),

    # 인문/철학
    ("인문", "인문"),
    ("심리", "인문"),
    ("정신분석", "인문"),
    ("문화", "인문"),
    ("인류", "인문"),
    ("철학", "철학"),
    ("윤리", "철학"),
    ("도덕", "철학"),
    ("노자", "철학"),
    ("노장", "철학"),

    # 과학
    ("과학", "과학"),
    ("우주", "과학"),
    ("천문", "과학"),
    ("뇌과학", "과학"),
    ("물리", "과학"),
    ("생명과학", "과학"),
    ("양자", "과학"),
    ("법의학", "과학"),
    ("인공지능", "과학"),
    ("빅데이터", "과학"),

    # 소설/장르
    ("호러", "스릴러/공포"),
    ("공포", "스릴러/공포"),
    ("스릴러", "스릴러/공포"),
    ("추리", "추리"),
    ("미스터리", "추리"),
    ("SF", "SF"),
    ("과학소설", "SF"),
    ("판타지", "판타지"),
    ("로맨스", "로맨스"),
    ("액션", "액션"),

    # 대분류
    ("에세이", "에세이"),
    ("시", "시"),
    ("소설", "소설"),
    ("만화", "만화"),

    # 여행/취미/자기계발
    ("여행", "여행"),
    ("가이드북", "여행"),
    ("요리", "취미"),
    ("제과", "취미"),
    ("컬러링", "취미"),
    ("취미", "취미"),
    ("자기계발", "자기계발"),
    ("수험서", "자기계발"),
    ("자격증", "자기계발"),
    ("토익", "자기계발"),
    ("영어", "자기계발"),
    ("일본어", "자기계발"),
    ("외국어", "자기계발"),
    ("시간관리", "자기계발"),
    ("성공", "자기계발"),
    ("인간관계", "자기계발"),
    ("협상", "자기계발"),
    ("취업", "자기계발"),
    ("진로", "자기계발"),
    ("학습", "자기계발"),
    ("교육", "자기계발"),

    # 예술
    ("예술", "예술"),
    ("대중문화", "예술"),
    ("미술", "예술"),
    ("음악", "예술"),
    ("영화", "예술"),
    ("연극", "예술"),
    ("애니메이션", "만화"),
]


# =============================
# ✅ category “정규화(leaf 추출)” 후 매핑 (이 부분만 변경)
# =============================

_COUNT_SUFFIX_RE = re.compile(r"\s*\(\s*\d+\s*권\s*\)\s*$")
_LEADING_BULLET_RE = re.compile(r"^\s*[-•]\s*")


def _normalize_token(s: str) -> str:
    s = s.strip().strip("'\"")
    s = _LEADING_BULLET_RE.sub("", s)
    s = _COUNT_SUFFIX_RE.sub("", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def _leaf_from_path(category: str) -> str:
    """
    '국내도서>...>...>최하위 (2권)' -> '최하위'
    """
    s = _normalize_token(category)
    if ">" in s:
        s = s.split(">")[-1]
    return _normalize_token(s)


def _split_category_tokens(category: str) -> list[str]:
    """
    기존 토큰화 + leaf를 최우선으로 포함시키도록 강화.
    1) leaf(최하위) / leaf의 분해 토큰들
    2) 전체 경로 '>' 분해 토큰들
    3) 각 토큰에서 '/' '·' 로 추가 분해
    """
    base = _normalize_token(category)
    leaf = _leaf_from_path(base)

    tokens: list[str] = []

    # 1) leaf 우선
    if leaf:
        tokens.append(leaf)
        for sub in re.split(r"[\/·]", leaf):
            sub = _normalize_token(sub)
            if sub and sub != leaf:
                tokens.append(sub)

    # 2) 경로 토큰들
    parts = [_normalize_token(p) for p in base.split(">") if p and p.strip()]
    for p in parts:
        if p:
            tokens.append(p)
        # 3) 추가 분해
        for sub in re.split(r"[\/·]", p):
            sub = _normalize_token(sub)
            if sub and sub != p:
                tokens.append(sub)

    # 중복 제거(순서 유지)
    return list(dict.fromkeys([t for t in tokens if t]))


def resolve_genre(category: Optional[str]) -> Optional[str]:
    """
    Book.category 문자열 -> 허용 장르(20개) 중 1개로 1:1 매핑.
    우선순위:
      1) leaf 포함 토큰들을 앞(leaf)부터 exact 매핑
      2) leaf 포함 토큰들을 앞(leaf)부터 fallback contains
      3) 전체 문자열에 대해 fallback contains
    """
    if not category:
        return None

    cat_norm = _normalize_token(category)
    tokens = _split_category_tokens(cat_norm)

    # 1) exact: leaf 우선(앞쪽)부터
    for t in tokens:
        g = CATEGORY_TO_GENRE_PRIMARY.get(t)
        if g in ALL_ALLOWED_GENRES:
            return g

    # 2) contains fallback: leaf 우선(앞쪽)부터
    for t in tokens:
        for needle, genre in FALLBACK_RULES:
            if needle and needle in t:
                if genre in ALL_ALLOWED_GENRES:
                    return genre

    # 3) 전체 문자열 fallback
    for needle, genre in FALLBACK_RULES:
        if needle and needle in cat_norm:
            if genre in ALL_ALLOWED_GENRES:
                return genre

    return None


def build_stats(bucket: dict[str, dict], names: List[str]) -> List[GenreStat]:
    out: List[GenreStat] = []
    for name in names:
        data = bucket.get(name)
        if not data or data["count"] == 0:
            out.append(GenreStat(name=name, review_count=0, average_5=0.0, average_100=0))
        else:
            avg5 = round(data["sum"] / data["count"], 2)
            out.append(
                GenreStat(
                    name=name,
                    review_count=int(data["count"]),
                    average_5=avg5,
                    average_100=int(round(avg5 * 20)),
                )
            )
    out.sort(key=lambda x: (x.average_5, x.review_count), reverse=True)
    return out


# =============================
# Endpoints
# =============================

@router.post("/search", status_code=status.HTTP_201_CREATED)
def log_search(
    data: SearchLogRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    entry = SearchHistory(user_id=user.id, query=data.query, created_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    return {"ok": True}


@router.post("/views", status_code=status.HTTP_201_CREATED)
def log_view(
    data: ViewLogRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    exists = db.query(Book.id).filter(Book.id == data.book_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail="Book not found")

    entry = BookView(book_id=data.book_id, user_id=user.id, created_at=datetime.now(timezone.utc))
    db.add(entry)
    db.commit()
    return {"ok": True}


@router.get(
    "/my-stats",
    response_model=UserStatsResponse,
    summary="사용자 독서/평점/선호 통계",
)
def user_stats(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # -------------------------
    # 평점 분포 (0.5 ~ 5.0, 10개)  ✅ 프론트 useIndexMapping(distData.length==10) 대응
    # -------------------------
    rows = (
        db.query((func.round(Review.rating * 2) / 2).label("bucket"), func.count(Review.id))
        .filter(Review.user_id == user.id, Review.rating != None)
        .group_by("bucket")
        .all()
    )
    bucket_counts: dict[float, int] = {float(b): int(c) for b, c in rows if b is not None}

    distribution: List[RatingBucket] = []
    v = 5.0
    total_reviews = 0
    while v >= 0.5 - 1e-9:
        vv = round(v, 1)
        cnt = bucket_counts.get(vv, 0)
        total_reviews += cnt
        distribution.append(RatingBucket(rating=vv, count=cnt))
        v -= 0.5

    # -------------------------
    # 평점 요약
    # -------------------------
    avg_val = (
        db.query(func.avg(Review.rating))
        .filter(Review.user_id == user.id, Review.rating != None)
        .scalar()
    )
    avg_5 = round(float(avg_val), 2) if avg_val is not None else 0.0
    avg_100 = int(round(avg_5 * 20))

    most_frequent_rating = 0.0
    if bucket_counts:
        most_frequent_rating = float(max(bucket_counts.items(), key=lambda x: x[1])[0])

    total_comments = (
        db.query(func.count())
        .select_from(Review)
        .filter(
            Review.user_id == user.id,
            Review.content != None,
            Review.content != "",
        )
        .scalar()
    )

    rating_summary = RatingSummary(
        average_5=avg_5,
        average_100=avg_100,
        total_reviews=total_reviews,
        most_frequent_rating=most_frequent_rating,
        total_comments=int(total_comments or 0),
    )

    # -------------------------
    # 독서 감상 시간
    # -------------------------
    session_rows = (
        db.query(ReadingSession.start_time, ReadingSession.end_time, ReadingSession.total_seconds)
        .filter(ReadingSession.user_id == user.id)
        .all()
    )
    total_seconds = 0
    for start, end, total in session_rows:
        if total is not None:
            total_seconds += int(total)
        elif start and end:
            diff = int((end - start).total_seconds())
            if diff > 0:
                total_seconds += diff
    reading_time = ReadingTime(total_seconds=total_seconds, human=_humanize_seconds(total_seconds))

    # -------------------------
    # ✅ 장르 통계: Review 기준 + Book.category 매핑
    # -------------------------
    category_rows = (
        db.query(Book.category, Review.rating)
        .join(Review, Review.book_id == Book.id)
        .filter(Review.user_id == user.id, Review.rating != None)
        .all()
    )

    acc: dict[str, dict] = {g: {"sum": 0.0, "count": 0} for g in ALL_ALLOWED_GENRES}

    for cat, rating in category_rows:
        genre = resolve_genre(cat)
        if not genre:
            continue
        acc[genre]["sum"] += float(rating)
        acc[genre]["count"] += 1

    top_stats = build_stats(acc, TOP_LEVEL_GENRES)
    sub_stats = build_stats(acc, SUB_GENRES)

    return UserStatsResponse(
        rating_distribution=distribution,
        rating_summary=rating_summary,
        reading_time=reading_time,
        sub_genres=sub_stats,
        top_level_genres=top_stats,
    )


@router.get("/my-insights", response_model=UserInsightResponse, summary="사용자 인사이트/태그 (임시 AI 대체)")
def my_insights(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(UserInsight).filter(UserInsight.user_id == user.id).first()
    if not row:
        return UserInsightResponse(analysis=None, tags=[])

    tags: List[InsightTag] = []
    if row.tags:
        for t in row.tags:
            label = t.get("label")
            weight = t.get("weight", 0.0)
            if label:
                tags.append(InsightTag(label=label, weight=float(weight)))
    return UserInsightResponse(analysis=row.analysis_text, tags=tags)


@router.post("/my-insights", response_model=UserInsightResponse, summary="사용자 인사이트/태그 업서트(임시 저장)")
def upsert_my_insights(
    data: UserInsightUpsert,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = db.query(UserInsight).filter(UserInsight.user_id == user.id).first()

    payload_tags = None
    if data.tags is not None:
        payload_tags = [{"label": t.label, "weight": float(t.weight)} for t in data.tags]

    if not row:
        row = UserInsight(
            user_id=user.id,
            analysis_text=data.analysis,
            tags=payload_tags,
        )
        db.add(row)
    else:
        if data.analysis is not None:
            row.analysis_text = data.analysis
        if payload_tags is not None:
            row.tags = payload_tags

    db.commit()

    out_tags: List[InsightTag] = []
    if row.tags:
        out_tags = [
            InsightTag(label=t["label"], weight=float(t.get("weight", 0.0)))
            for t in row.tags
            if t.get("label")
        ]
    return UserInsightResponse(analysis=row.analysis_text, tags=out_tags)


@router.get("/calendar-month", response_model=CalendarMonthResponse, summary="월간 독서 캘린더 요약 + 평점 남긴 책 표지")
def calendar_month(
    year: int,
    month: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    주어진 월에 사용자가 평점을 남긴 책을 캘린더에 표시합니다.
    - 평점 남긴 날짜를 기준으로 책을 표시합니다.
    """
    from datetime import date
    from calendar import monthrange

    start = date(year, month, 1)
    last_day = monthrange(year, month)[1]
    end = date(year, month, last_day)

    rated_books = (
        db.query(Review.book_id, Review.created_date)
        .filter(
            Review.user_id == user.id,
            Review.created_date >= start,
            Review.created_date <= end,
            Review.rating != None,
        )
        .all()
    )
    book_ids = [bid for (bid, _) in rated_books]
    total_rated_count = len(book_ids)

    top_genre = None
    if book_ids:
        from collections import Counter
        cats = db.query(Book.category).filter(Book.id.in_(book_ids)).all()
        cnt = Counter([c for (c,) in cats if c])
        if cnt:
            top_genre = cnt.most_common(1)[0][0]

    books = db.query(Book).filter(Book.id.in_(book_ids)).all()
    author_map = {b.id: [ba.author.name for ba in b.authors] for b in books}
    rating_map = {
        r.book_id: r.rating
        for r in db.query(Review.book_id, Review.rating)
        .filter(Review.user_id == user.id, Review.book_id.in_(book_ids))
        .all()
    }
    books_map = {b.id: b for b in books}

    by_date: dict[str, list[CalendarBookItem]] = {}
    for (bid, rdate) in rated_books:
        if not rdate:
            continue
        b = books_map.get(bid)
        if not b:
            continue
        key = rdate.isoformat()
        by_date.setdefault(key, []).append(
            CalendarBookItem(
                book_id=bid,
                title=b.title,
                thumbnail=getattr(b, "thumbnail", None),
                authors=author_map.get(bid, []),
                rating=rating_map.get(bid),
            )
        )

    days = [CalendarDay(date=d, items=items) for d, items in sorted(by_date.items())]
    return CalendarMonthResponse(
        year=year,
        month=month,
        total_read_count=total_rated_count,
        top_genre=top_genre,
        days=days,
    )
