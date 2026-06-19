from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


ALLOWED_MAX_MEMBERS = {10, 50, 100, 200, 300}

GROUP_REPORT_REASON_OPTIONS = [
    {"code": "ABUSIVE", "label": "욕설/비방"},
    {"code": "SPAM", "label": "도배/스팸"},
    {"code": "ADVERTISEMENT", "label": "광고/홍보"},
    {"code": "OFF_TOPIC", "label": "주제와 무관한 내용"},
    {"code": "HATE", "label": "혐오/차별 표현"},
    {"code": "SEXUAL", "label": "성적인 내용"},
    {"code": "INAPPROPRIATE", "label": "부적절한 표현"},
    {"code": "OTHER", "label": "기타"},
]


class GroupCreateRequest(BaseModel):
    name: str
    groupId: str = Field(..., min_length=3, max_length=50)
    backgroundImage: Optional[str] = None
    maxMembers: int
    description: Optional[str] = None
    isPrivate: bool = False
    password: Optional[str] = None
    passwordConfirm: Optional[str] = None


class GroupCreateResponse(BaseModel):
    groupId: str
    name: str
    createdAt: datetime
    leaderName: Optional[str] = None
    memberCount: int
    maxMembers: int
    description: Optional[str] = None
    isPrivate: bool
    isJoined: bool


class GroupUpdateRequest(BaseModel):
    backgroundImage: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    maxMembers: Optional[int] = None
    isPrivate: Optional[bool] = None


class GroupUpdateResponse(BaseModel):
    groupId: str
    name: str
    backgroundImage: str | None = None
    description: str | None = None
    maxMembers: int | None = None
    isPrivate: bool


class GroupIdCheckResponse(BaseModel):
    exists: bool
    available: bool


class GroupMissionBookInfo(BaseModel):
    bookId: int
    isbn13: str | None = None
    title: str
    authors: list[str]
    thumbnail: str | None = None
    totalPages: int | None = None
    groupAverageProgressPercent: float
    myProgressPercent: float


class GroupMemberInfo(BaseModel):
    memberId: int
    nickname: str
    profileImage: str | None = None
    profileImageUrl: str | None = None
    missionProgressPercent: float


class GroupDetailResponse(BaseModel):
    groupId: str
    name: str
    backgroundImage: str | None = None
    createdAt: datetime
    leaderId: int | None = None
    leaderName: str | None = None
    memberCount: int
    maxMembers: int | None = None
    description: str | None = None
    isPrivate: bool
    isJoined: bool
    isLeader: bool
    currentMissionBook: GroupMissionBookInfo | None = None
    missionBooks: list[GroupMissionBookInfo] = []
    members: list[GroupMemberInfo] = []


class MissionBookUpdateRequest(BaseModel):
    isbn: str


class MissionBookHistoryItem(BaseModel):
    month: str
    bookId: int
    isbn13: str | None = None
    title: str
    thumbnail: str | None = None
    boardType: str = "MISSION"
    boardBookId: int


class MissionBookHistoryResponse(BaseModel):
    items: list[MissionBookHistoryItem]


class GroupBoardItem(BaseModel):
    boardKey: str
    boardType: str
    label: str
    isArchived: bool = False
    bookId: int | None = None
    isbn13: str | None = None
    title: str | None = None
    thumbnail: str | None = None


class GroupBoardListResponse(BaseModel):
    boards: list[GroupBoardItem]


class GroupPostRecordItem(BaseModel):
    recordType: str
    recordId: int


class GroupPostBase(BaseModel):
    postId: int
    groupId: str
    type: str
    title: str | None = None
    content: str
    bookId: int | None = None
    createdAt: datetime
    isPinned: bool = False
    pinnedAt: datetime | None = None
    authorId: int
    authorName: str
    profileImageUrl: str | None = None
    likeCount: int
    commentCount: int
    isLiked: bool
    records: list[GroupPostRecordItem] = []
    discussion: dict | None = None


class GroupPostCreateRequest(BaseModel):
    type: str | None = None
    title: str | None = None
    content: str
    bookId: int | None = None
    records: list[GroupPostRecordItem] = []
    discussion: dict | None = None


class GroupPostListResponse(BaseModel):
    posts: list[GroupPostBase]


class GroupPostDetailResponse(GroupPostBase):
    discussion: dict | None = None
    recordId: int | None = None


class GroupPostUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    bookId: int | None = None
    discussion: dict | None = None


class GroupJoinRequest(BaseModel):
    password: str | None = None


class GroupJoinResponse(BaseModel):
    ok: bool
    isJoined: bool
    memberCount: int


class GroupLeaveResponse(BaseModel):
    ok: bool
    isJoined: bool
    memberCount: int


class GroupDeleteResponse(BaseModel):
    ok: bool
    deletedGroupId: str
    notifiedMemberCount: int


class GroupPinRequest(BaseModel):
    isPinned: bool


class MyGroupItem(BaseModel):
    groupId: str
    name: str
    backgroundImage: str | None = None
    boards: list[GroupBoardItem] = []


class MyGroupListResponse(BaseModel):
    groups: list[MyGroupItem]


class GroupRecommendationItem(BaseModel):
    groupId: str
    name: str
    backgroundImage: str | None = None
    description: str | None = None
    memberCount: int
    maxMembers: int | None = None


class GroupRecommendationResponse(BaseModel):
    groups: list[GroupRecommendationItem]


class GroupSearchItem(BaseModel):
    groupId: str
    name: str
    backgroundImage: str | None = None
    description: str | None = None
    memberCount: int
    maxMembers: int | None = None


class GroupSearchResponse(BaseModel):
    groups: list[GroupSearchItem]


class GroupCommentReply(BaseModel):
    commentId: int
    userId: int
    userName: str
    profileImageUrl: str | None = None
    content: str
    createdAt: datetime
    likeCount: int
    isLiked: bool


class GroupCommentItem(BaseModel):
    commentId: int
    userId: int
    userName: str
    profileImageUrl: str | None = None
    content: str
    createdAt: datetime
    likeCount: int
    isLiked: bool
    replies: list[GroupCommentReply]


class GroupCommentListResponse(BaseModel):
    comments: list[GroupCommentItem]


class GroupCommentCreateRequest(BaseModel):
    content: str


class GroupSharePostRequest(BaseModel):
    boardType: str
    recordId: int
    content: str | None = None
    discussion: dict | None = None


class GroupShareNoteRequest(BaseModel):
    boardType: str
    noteId: int


class GroupShareNotePrefillResponse(BaseModel):
    groupId: str
    boardType: str
    noteId: int
    page: int | None = None
    title: str | None = None
    content: str
    bookId: int
    isbn13: str | None = None
    bookTitle: str
    thumbnail: str | None = None
    isMissionMatched: bool


class GroupDiscussionVoteRequest(BaseModel):
    optionId: int


class GroupReportRequest(BaseModel):
    reasonCode: str
    reasonDetail: str | None = None


class GroupReportReasonItem(BaseModel):
    code: str
    label: str


class GroupReportReasonListResponse(BaseModel):
    reasons: list[GroupReportReasonItem]


class GroupReportTargetItem(BaseModel):
    targetId: int
    targetType: str
    authorId: int
    authorName: str
    content: str
    reportCount: int
    lastReportedAt: datetime
    reasonCodes: list[str] = []


class GroupReportInboxResponse(BaseModel):
    posts: list[GroupReportTargetItem]
    comments: list[GroupReportTargetItem]


class GroupMemberProfileMissionBookItem(BaseModel):
    month: str
    bookId: int
    isbn13: str | None = None
    title: str
    thumbnail: str | None = None
    progressPercent: float
    boardType: str = "MISSION"
    boardBookId: int


class GroupMemberProfileResponse(BaseModel):
    memberId: int
    nickname: str
    profileImage: str | None = None
    missionBooks: list[GroupMemberProfileMissionBookItem]
