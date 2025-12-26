from datetime import datetime, date, timezone
try:
    from zoneinfo import ZoneInfo
    SEOUL_TZ = ZoneInfo("Asia/Seoul")
except ImportError:
    from pytz import timezone
    SEOUL_TZ = timezone("Asia/Seoul")

def to_seoul(dt):
    if dt is None:
        return None
    # 날짜만 있는 경우(출판일 등)는 변환하지 않음
    if isinstance(dt, date) and not isinstance(dt, datetime):
        return dt
    # naive datetime이면 UTC로 간주
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # 서울 시간으로 변환
    return dt.astimezone(SEOUL_TZ)
