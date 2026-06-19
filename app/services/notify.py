from __future__ import annotations

from datetime import datetime
import json
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models import (
    FCMToken,
    Notification,
    NotificationTabCategory,
    NotificationType,
    UserNotificationSetting,
)
from app.services.notifications import send_to_token

_DEDUPE_TARGET_KEYS = (
    'actorId',
    'groupId',
    'postId',
    'commentId',
    'bookId',
    'inquiryId',
    'badgeCategory',
    'badgeLevel',
    'eventKind',
    'reminderType',
    'reminderDate',
    'reportKind',
    'reportYear',
    'reportMonth',
    'discussionEndsAt',
)


def infer_tab_category(notification_type: NotificationType) -> NotificationTabCategory:
    if notification_type in {
        NotificationType.GROUP_NOTICE,
        NotificationType.GROUP_ANNOUNCEMENT,
        NotificationType.GROUP_MISSION_UPDATE,
        NotificationType.GROUP_DISCUSSION,
        NotificationType.SOCIAL_LIKE,
        NotificationType.SOCIAL_COMMENT,
    }:
        return NotificationTabCategory.GROUP
    return NotificationTabCategory.GENERAL


def get_or_create_notification_settings(db: Session, user_id: int) -> UserNotificationSetting:
    settings = (
        db.query(UserNotificationSetting)
        .filter(UserNotificationSetting.user_id == user_id)
        .first()
    )
    if settings:
        return settings
    settings = UserNotificationSetting(user_id=user_id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def _push_allowed(settings: UserNotificationSetting, tab_category: NotificationTabCategory) -> bool:
    if not settings.push_enabled:
        return False
    if tab_category == NotificationTabCategory.GROUP:
        return settings.group_enabled
    return settings.general_enabled


def normalize_target_info(target_info: Optional[Dict[str, Any]], data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    if data:
        merged.update(data)
    if target_info:
        merged.update(target_info)
    return merged

def _fcm_type(notification_type: NotificationType, target_info: Dict[str, Any]) -> str:
    if target_info.get("type"):
        return str(target_info["type"])
    reminder_type = target_info.get("reminderType")
    event_kind = str(target_info.get("eventKind") or "")
    if reminder_type == "READING_REMINDER":
        return "REMINDER"
    if reminder_type == "READING_SLUMP":
        return "READING_SLUMP"
    if notification_type == NotificationType.GROUP_MISSION_UPDATE:
        return "GROUP_MISSION"
    if notification_type == NotificationType.GROUP_ANNOUNCEMENT:
        return "GROUP_NOTICE"
    if notification_type == NotificationType.GROUP_NOTICE:
        if event_kind == "GROUP_JOIN":
            return "GROUP_JOIN"
        if event_kind == "GROUP_LEAVE":
            return "GROUP_LEAVE"
        if event_kind == "GROUP_DELETED":
            return "GROUP_DELETED"
        return "GROUP_NOTICE"
    if notification_type == NotificationType.GROUP_DISCUSSION:
        return "GROUP_DISCUSSION"
    if notification_type == NotificationType.SOCIAL_COMMENT:
        return "GROUP_COMMENT"
    if notification_type == NotificationType.SOCIAL_LIKE:
        if target_info.get("commentId"):
            return "GROUP_COMMENT"
        return "GROUP_LIKE"
    if notification_type == NotificationType.AI_SUMMARY_READY:
        return "AI_SUMMARY"
    if notification_type == NotificationType.BOOK_RECOMMEND:
        return "RECOMMEND"
    if notification_type == NotificationType.BADGE_EARNED:
        return "BADGE"
    if notification_type == NotificationType.READING_REPORT:
        return "READING_REPORT"
    if notification_type == NotificationType.REVIEW_REACTION:
        return "REVIEW_REACTION"
    if notification_type == NotificationType.COLLECTION_REACTION:
        return "REVIEW_REACTION"
    if notification_type == NotificationType.CUSTOMER_SERVICE_ANSWERED:
        return "CUSTOMER_SERVICE"
    return notification_type.value


def build_fcm_payload(notification_type: NotificationType, target_info: Dict[str, Any]) -> Dict[str, str]:
    payload = dict(target_info or {})
    payload.pop("type", None)
    return {
        "type": _fcm_type(notification_type, target_info),
        "targetInfo": json.dumps(payload, ensure_ascii=False),
    }


def notification_dedupe_key(notification_type: NotificationType | str, target_info: Optional[Dict[str, Any]]) -> tuple[Any, ...]:
    source = target_info or {}
    return tuple([str(notification_type)] + [source.get(key) for key in _DEDUPE_TARGET_KEYS])


def _find_existing_notification(
    db: Session,
    *,
    user_id: int,
    notification_type: NotificationType,
    tab_category: NotificationTabCategory,
    target_info: Dict[str, Any],
    unread_only: bool = True,
) -> Notification | None:
    key = notification_dedupe_key(notification_type, target_info)
    query = db.query(Notification).filter(
        Notification.user_id == user_id,
        Notification.type == notification_type,
        Notification.tab_category == tab_category,
    )
    if unread_only:
        query = query.filter(Notification.is_read.is_(False))
    candidates = (
        query
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(30)
        .all()
    )
    for candidate in candidates:
        candidate_target_info = normalize_target_info(candidate.target_info, candidate.data)
        if notification_dedupe_key(candidate.type, candidate_target_info) == key:
            return candidate
    return None


def notify_user(
    db: Session,
    user_id: int,
    title: Optional[str],
    body: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    notification_type: NotificationType = NotificationType.GENERAL,
    tab_category: Optional[NotificationTabCategory] = None,
    thumbnail_url: Optional[str] = None,
    target_info: Optional[Dict[str, Any]] = None,
    send_push: bool = False,
) -> Notification:
    resolved_tab_category = tab_category or infer_tab_category(notification_type)
    resolved_target_info = normalize_target_info(target_info, data)
    dedupe_unread_only = notification_type != NotificationType.BADGE_EARNED
    existing = _find_existing_notification(
        db,
        user_id=user_id,
        notification_type=notification_type,
        tab_category=resolved_tab_category,
        target_info=resolved_target_info,
        unread_only=dedupe_unread_only,
    )

    if existing and notification_type == NotificationType.BADGE_EARNED:
        return existing

    if existing:
        existing.title = title
        existing.body = body
        existing.data = data or {}
        existing.target_info = resolved_target_info
        existing.thumbnail_url = thumbnail_url
        existing.is_read = False
        existing.created_at = datetime.utcnow()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        notification = existing
    else:
        notification = Notification(
            user_id=user_id,
            type=notification_type,
            tab_category=resolved_tab_category,
            title=title,
            body=body,
            data=data or {},
            thumbnail_url=thumbnail_url,
            target_info=resolved_target_info,
        )
        db.add(notification)
        db.commit()
        db.refresh(notification)

    if send_push:
        settings = get_or_create_notification_settings(db, user_id)
        if _push_allowed(settings, resolved_tab_category):
            tokens = (
                db.query(FCMToken)
                .filter(FCMToken.user_id == user_id, FCMToken.is_active.is_(True))
                .all()
            )
            for token in tokens:
                try:
                    send_to_token(token.token, title or body, body, build_fcm_payload(notification_type, resolved_target_info))
                    token.last_used_at = datetime.utcnow()
                except Exception:
                    continue
            db.commit()

    return notification


def create_notification(
    db: Session,
    user_id: int,
    title: Optional[str],
    body: str,
    data: Optional[Dict[str, Any]] = None,
    *,
    notification_type: NotificationType = NotificationType.GENERAL,
    tab_category: Optional[NotificationTabCategory] = None,
    thumbnail_url: Optional[str] = None,
    target_info: Optional[Dict[str, Any]] = None,
    send_push: bool = False,
) -> Notification:
    return notify_user(
        db,
        user_id,
        title,
        body,
        data,
        notification_type=notification_type,
        tab_category=tab_category,
        thumbnail_url=thumbnail_url,
        target_info=target_info,
        send_push=send_push,
    )
