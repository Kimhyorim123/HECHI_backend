from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class UserBadgeItem(BaseModel):
    badgeId: int
    code: str
    category: str
    levelCode: str
    title: str
    description: str | None = None
    iconUrl: str | None = None
    contextValue: str | None = None
    earnedAt: datetime
    progressSnapshot: dict[str, Any] | None = None


class UserBadgeListResponse(BaseModel):
    badges: list[UserBadgeItem]


class BadgeRecalculateResponse(BaseModel):
    ok: bool
    newlyAwarded: int
    totalBadges: int
