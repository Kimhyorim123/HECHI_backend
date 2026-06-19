from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, Field


class NotificationItemResponse(BaseModel):
    notificationId: str
    tabCategory: str
    type: str
    title: str | None = None
    message: str
    thumbnailUrl: str | None = None
    senderName: str | None = None
    senderProfileImageUrl: str | None = None
    isRead: bool
    createdAt: datetime
    targetInfo: dict[str, Any] | None = None


class NotificationListResponse(BaseModel):
    notifications: list[NotificationItemResponse]
    limit: int
    offset: int
    hasNext: bool


class UnreadCountResponse(BaseModel):
    unreadCount: int


class MarkReadResponse(BaseModel):
    ok: bool
    notificationId: str | None = None


class DeleteNotificationsResponse(BaseModel):
    ok: bool
    deletedCount: int


class RegisterTokenRequest(BaseModel):
    fcm_token: str = Field(validation_alias=AliasChoices('fcm_token', 'fcmToken'))


class SendTestRequest(BaseModel):
    title: str
    body: str
    type: str | None = None
    data: dict[str, Any] | None = None


class SendTestResponse(BaseModel):
    sentCount: int
    messageIds: list[str | None]


class NotificationSettingsResponse(BaseModel):
    pushEnabled: bool
    generalEnabled: bool
    groupEnabled: bool
    marketingEnabled: bool


class NotificationSettingsUpdateRequest(BaseModel):
    pushEnabled: bool | None = None
    generalEnabled: bool | None = None
    groupEnabled: bool | None = None
    marketingEnabled: bool | None = None
