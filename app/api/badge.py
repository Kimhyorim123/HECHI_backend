from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.badge import BadgeRecalculateResponse, UserBadgeItem, UserBadgeListResponse
from app.services.badges import evaluate_user_badges, list_user_badges

router = APIRouter(tags=["badges"])


@router.get("/users/me/badges", response_model=UserBadgeListResponse, summary="내 배지 목록")
def get_my_badges(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    badges = list_user_badges(db, current_user.id)
    items = [
        UserBadgeItem(
            badgeId=badge.id,
            code=badge.badge_definition.code,
            category=badge.badge_definition.category,
            levelCode=badge.badge_definition.level_code,
            title=badge.badge_definition.title,
            description=badge.badge_definition.description,
            iconUrl=badge.badge_definition.icon_url,
            contextValue=badge.context_value,
            earnedAt=badge.earned_at,
            progressSnapshot=badge.progress_snapshot,
        )
        for badge in badges
    ]
    return UserBadgeListResponse(badges=items)


@router.post("/users/me/badges/recalculate", response_model=BadgeRecalculateResponse, summary="내 배지 재계산")
def recalculate_my_badges(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    newly_awarded = evaluate_user_badges(db, current_user.id)
    total_badges = len(list_user_badges(db, current_user.id))
    return BadgeRecalculateResponse(ok=True, newlyAwarded=newly_awarded, totalBadges=total_badges)
