from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.database import get_db
from app.models import FCMToken, Notification, NotificationTabCategory, NotificationType, User
from app.schemas.notification import (
    DeleteNotificationsResponse,
    MarkReadResponse,
    NotificationItemResponse,
    NotificationListResponse,
    NotificationSettingsResponse,
    NotificationSettingsUpdateRequest,
    RegisterTokenRequest,
    SendTestRequest,
    SendTestResponse,
    UnreadCountResponse,
)
from app.services.notifications import send_to_token
from app.services.notify import build_fcm_payload, get_or_create_notification_settings, notification_dedupe_key, normalize_target_info

router = APIRouter(tags=['notifications'])


KST = timezone(timedelta(hours=9))


def _notification_created_at_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(KST)


def _notification_payload(notification: Notification) -> dict:
    return normalize_target_info(notification.target_info, notification.data)


_USER_ACTION_NOTIFICATION_TYPES = {
    NotificationType.SOCIAL_LIKE,
    NotificationType.SOCIAL_COMMENT,
    NotificationType.REVIEW_REACTION,
    NotificationType.COLLECTION_REACTION,
}


def _sender_name(db: Session, notification: Notification) -> str | None:
    payload = _notification_payload(notification)
    event_kind = str(payload.get("eventKind") or "")
    if notification.type == NotificationType.GROUP_NOTICE and event_kind not in {"GROUP_JOIN", "GROUP_LEAVE"}:
        return None
    if notification.type not in _USER_ACTION_NOTIFICATION_TYPES and not (notification.type == NotificationType.GROUP_NOTICE and event_kind in {"GROUP_JOIN", "GROUP_LEAVE"}):
        return None
    actor_name = payload.get("actorName")
    if actor_name:
        return str(actor_name)
    actor_id = payload.get("actorId")
    if not actor_id:
        return None
    actor = db.query(User).filter(User.id == int(actor_id)).first()
    return actor.nickname if actor and actor.nickname else None


def _sender_profile_image_url(db: Session, notification: Notification) -> str | None:
    payload = _notification_payload(notification)
    event_kind = str(payload.get("eventKind") or "")
    if notification.type == NotificationType.GROUP_NOTICE and event_kind not in {"GROUP_JOIN", "GROUP_LEAVE"}:
        return None
    if notification.type not in _USER_ACTION_NOTIFICATION_TYPES and not (notification.type == NotificationType.GROUP_NOTICE and event_kind in {"GROUP_JOIN", "GROUP_LEAVE"}):
        return None
    actor_id = payload.get("actorId")
    if not actor_id:
        return None
    actor = db.query(User).filter(User.id == int(actor_id)).first()
    return actor.profile_image_url if actor and actor.profile_image_url else None




def _notification_response_type(notification: Notification) -> str:
    payload = _notification_payload(notification)
    event_kind = str(payload.get("eventKind") or "")
    if notification.type == NotificationType.COLLECTION_REACTION:
        return "REVIEW_REACTION"
    if notification.type == NotificationType.SOCIAL_COMMENT:
        return "GROUP_COMMENT"
    if notification.type == NotificationType.SOCIAL_LIKE:
        return "GROUP_COMMENT" if payload.get("commentId") else "GROUP_LIKE"
    if notification.type == NotificationType.GROUP_NOTICE:
        if event_kind == "GROUP_JOIN":
            return "GROUP_JOIN"
        if event_kind == "GROUP_LEAVE":
            return "GROUP_LEAVE"
        if event_kind == "GROUP_DELETED":
            return "GROUP_DELETED"
    return notification.type.value

def _serialize_notification(db: Session, notification: Notification) -> NotificationItemResponse:
    return NotificationItemResponse(
        notificationId=str(notification.id),
        tabCategory=notification.tab_category.value,
        type=_notification_response_type(notification),
        title=notification.title,
        message=notification.body,
        thumbnailUrl=notification.thumbnail_url,
        senderName=_sender_name(db, notification),
        senderProfileImageUrl=_sender_profile_image_url(db, notification),
        isRead=notification.is_read,
        createdAt=_notification_created_at_kst(notification.created_at),
        targetInfo=_notification_payload(notification),
    )


def _dedupe_notifications(notifications: list[Notification], limit: int) -> tuple[list[Notification], bool]:
    seen: set[tuple] = set()
    items: list[Notification] = []
    has_next = False
    for notification in notifications:
        key = notification_dedupe_key(notification.type.value, _notification_payload(notification))
        if key in seen:
            continue
        seen.add(key)
        if len(items) < limit:
            items.append(notification)
        else:
            has_next = True
            break
    return items, has_next


@router.post('/notifications/register-token')
def register_token(
    payload: RegisterTokenRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing = db.query(FCMToken).filter(FCMToken.token == payload.fcm_token).first()
    if existing:
        existing.user_id = current_user.id
        existing.is_active = True
        existing.last_used_at = datetime.utcnow()
    else:
        db.add(
            FCMToken(
                user_id=current_user.id,
                token=payload.fcm_token,
                is_active=True,
                last_used_at=datetime.utcnow(),
            )
        )
    current_user.fcm_token = payload.fcm_token
    db.add(current_user)
    db.commit()
    return {'ok': True}


@router.post('/notifications/send-test', response_model=SendTestResponse)
def send_test(
    payload: SendTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tokens = (
        db.query(FCMToken)
        .filter(FCMToken.user_id == current_user.id, FCMToken.is_active.is_(True))
        .all()
    )
    unique_tokens = {token.token for token in tokens}
    if current_user.fcm_token:
        unique_tokens.add(current_user.fcm_token)
    if not unique_tokens:
        raise HTTPException(status_code=400, detail='No FCM token registered for user')

    target_info = dict(payload.data or {})
    if payload.type and 'type' not in target_info:
        target_info['type'] = payload.type
    fcm_payload = build_fcm_payload(NotificationType.GENERAL, target_info)

    message_ids: list[str | None] = []
    for token_value in unique_tokens:
        message_ids.append(send_to_token(token_value, payload.title, payload.body, fcm_payload))
    return SendTestResponse(sentCount=len(unique_tokens), messageIds=message_ids)


@router.get('/users/me/notifications', response_model=NotificationListResponse)
def list_notifications(
    tab_category: NotificationTabCategory | None = Query(default=None, alias='tabCategory'),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Notification).filter(Notification.user_id == current_user.id)
    if tab_category is not None:
        query = query.filter(Notification.tab_category == tab_category)
    notifications = (
        query.order_by(Notification.created_at.desc(), Notification.id.desc())
        .offset(offset)
        .limit(max(limit * 5, limit + 20))
        .all()
    )
    visible, has_next = _dedupe_notifications(notifications, limit)
    return NotificationListResponse(
        notifications=[_serialize_notification(db, notification) for notification in visible],
        limit=limit,
        offset=offset,
        hasNext=has_next,
    )


@router.get('/users/me/notifications/unread-count', response_model=UnreadCountResponse)
def unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )
    visible, _ = _dedupe_notifications(notifications, len(notifications) or 1)
    return UnreadCountResponse(unreadCount=len(visible))


@router.patch('/notifications/{notification_id}/read', response_model=MarkReadResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail='Notification not found')
    notification.is_read = True
    db.commit()
    return MarkReadResponse(ok=True, notificationId=str(notification.id))


@router.patch('/notifications/read-all', response_model=MarkReadResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.is_read.is_(False))
        .update({'is_read': True}, synchronize_session=False)
    )
    db.commit()
    return MarkReadResponse(ok=True)


@router.delete('/notifications/{notification_id}', response_model=DeleteNotificationsResponse)
def delete_notification(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    notification = (
        db.query(Notification)
        .filter(Notification.id == notification_id, Notification.user_id == current_user.id)
        .first()
    )
    if not notification:
        raise HTTPException(status_code=404, detail='Notification not found')

    dedupe_key = notification_dedupe_key(notification.type.value, _notification_payload(notification))
    candidates = (
        db.query(Notification)
        .filter(
            Notification.user_id == current_user.id,
            Notification.type == notification.type,
            Notification.tab_category == notification.tab_category,
        )
        .all()
    )
    delete_ids = [
        item.id
        for item in candidates
        if notification_dedupe_key(item.type.value, _notification_payload(item)) == dedupe_key
    ]
    if not delete_ids:
        delete_ids = [notification.id]

    deleted = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id, Notification.id.in_(delete_ids))
        .delete(synchronize_session=False)
    )
    db.commit()
    return DeleteNotificationsResponse(ok=True, deletedCount=deleted)


@router.delete('/notifications/all', response_model=DeleteNotificationsResponse)
def delete_all_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deleted = (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .delete(synchronize_session=False)
    )
    db.commit()
    return DeleteNotificationsResponse(ok=True, deletedCount=deleted)


@router.get('/users/me/notification-settings', response_model=NotificationSettingsResponse)
def get_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_notification_settings(db, current_user.id)
    return NotificationSettingsResponse(
        pushEnabled=settings.push_enabled,
        generalEnabled=settings.general_enabled,
        groupEnabled=settings.group_enabled,
        marketingEnabled=settings.marketing_enabled,
    )


@router.patch('/users/me/notification-settings', response_model=NotificationSettingsResponse)
def update_notification_settings(
    payload: NotificationSettingsUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    settings = get_or_create_notification_settings(db, current_user.id)
    updates = payload.model_dump(exclude_unset=True)
    field_map = {
        'pushEnabled': 'push_enabled',
        'generalEnabled': 'general_enabled',
        'groupEnabled': 'group_enabled',
        'marketingEnabled': 'marketing_enabled',
    }
    for request_field, model_field in field_map.items():
        if request_field in updates:
            setattr(settings, model_field, updates[request_field])
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return NotificationSettingsResponse(
        pushEnabled=settings.push_enabled,
        generalEnabled=settings.general_enabled,
        groupEnabled=settings.group_enabled,
        marketingEnabled=settings.marketing_enabled,
    )
