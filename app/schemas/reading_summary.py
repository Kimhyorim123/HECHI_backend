from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ReadingSummaryStats(BaseModel):
    noteCount: int
    noteCharacterCount: int
    highlightCount: int
    bookmarkCount: int
    totalReadingSeconds: int
    startPage: int | None = None
    endPage: int | None = None


class ReadingSummaryContent(BaseModel):
    summary: str | None = None
    keyPoints: list[str] = []
    notesDigest: list[str] = []


class ReadingSummaryResponse(BaseModel):
    bookId: int
    status: str
    summaryDirty: bool
    autoEligible: bool
    stats: ReadingSummaryStats
    summaryText: list[str] = []
    summaryContent: ReadingSummaryContent
    lastSourceUpdatedAt: datetime | None = None
    lastSummarizedAt: datetime | None = None
    errorMessage: str | None = None


class ReadingSummaryGenerateResponse(BaseModel):
    bookId: int
    status: str
    summaryDirty: bool
    autoEligible: bool
    queued: bool
    reason: str | None = None


class ReadingSummaryPayload(BaseModel):
    summaryType: str
    bookId: int
    trigger: str
    stats: dict[str, Any]
    notes: list[str]
    highlights: list[str]
    bookmarks: list[str]
    bookTitle: str | None = None
    authors: list[str] = []


class ReadingSummaryDeleteResponse(BaseModel):
    bookId: int
    deleted: bool
    deletedJobs: int
    deletedNotifications: int
