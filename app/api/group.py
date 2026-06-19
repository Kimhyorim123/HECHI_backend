import re
from datetime import datetime
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func

from ..database import get_db
from ..models import (
    Group,
    GroupMember,
    GroupRole,
    GroupMonthlyBook,
    GroupPost,
    GroupPostLike,
    GroupComment,
    GroupCommentLike,
    GroupCommentReport,
    GroupPostDiscussionVote,
    GroupPostType,
    GroupPostReport,
    User,
    Book,
    BookAuthor,
    Author,
    Note,
    ReadingSession,
    UserBook,
    NotificationType,
)
from ..core.auth import get_current_user
from ..core.security import hash_password, verify_password
from ..services.notify import create_notification
from ..schemas.group import (
    GroupCreateRequest,
    GroupCreateResponse,
    GroupUpdateRequest,
    GroupUpdateResponse,
    GroupBoardItem,
    GroupBoardListResponse,
    GroupIdCheckResponse,
    GroupDetailResponse,
    GroupMemberInfo,
    GroupMemberProfileMissionBookItem,
    GroupMemberProfileResponse,
    GroupMissionBookInfo,
    GroupPostBase,
    GroupPostCreateRequest,
    GroupPostRecordItem,
    GroupPostDetailResponse,
    GroupPostUpdateRequest,
    GroupPostListResponse,
    GroupCommentListResponse,
    GroupCommentCreateRequest,
    GroupCommentItem,
    GroupCommentReply,
    GroupDiscussionVoteRequest,
    GroupReportReasonItem,
    GroupReportReasonListResponse,
    GroupShareNotePrefillResponse,
    GroupShareNoteRequest,
    GroupSharePostRequest,
    MissionBookUpdateRequest,
    MissionBookHistoryResponse,
    MissionBookHistoryItem,
    GroupJoinRequest,
    GroupJoinResponse,
    GroupLeaveResponse,
    GroupDeleteResponse,
    GroupPinRequest,
    GroupReportRequest,
    GroupReportInboxResponse,
    GroupReportTargetItem,
    GroupRecommendationResponse,
    GroupRecommendationItem,
    GroupSearchResponse,
    GroupSearchItem,
    GROUP_REPORT_REASON_OPTIONS,
    ALLOWED_MAX_MEMBERS,
)


router = APIRouter(prefix="/groups", tags=["groups"])

_GROUP_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{3,50}$")


@router.get("/check-id", response_model=GroupIdCheckResponse, summary="그룹 ID 중복 확인")
def check_group_id(
    groupId: str = Query(..., min_length=3, max_length=50),
    db: Session = Depends(get_db),
):
    exists = db.query(Group.id).filter(Group.group_id == groupId).first() is not None
    return GroupIdCheckResponse(exists=exists, available=not exists)


@router.post("", response_model=GroupCreateResponse, status_code=status.HTTP_201_CREATED, summary="그룹 생성")
def create_group(
    payload: GroupCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not _GROUP_ID_RE.match(payload.groupId):
        raise HTTPException(status_code=400, detail="Invalid groupId format")
    if payload.maxMembers not in ALLOWED_MAX_MEMBERS:
        raise HTTPException(status_code=400, detail="Invalid maxMembers")
    existing = db.query(Group.id).filter(Group.group_id == payload.groupId).first()
    if existing:
        raise HTTPException(status_code=400, detail="Group ID already exists")
    if payload.isPrivate:
        if not payload.password or not payload.passwordConfirm:
            raise HTTPException(status_code=400, detail="Password required for private group")
        if payload.password != payload.passwordConfirm:
            raise HTTPException(status_code=400, detail="Password confirmation does not match")

    group = Group(
        name=payload.name.strip(),
        group_id=payload.groupId,
        background_image=payload.backgroundImage,
        max_members=payload.maxMembers,
        description=payload.description,
        is_private=payload.isPrivate,
        password_hash=hash_password(payload.password) if payload.isPrivate else None,
        leader_user_id=current_user.id,
    )
    db.add(group)
    db.flush()
    leader = GroupMember(
        group_id=group.id,
        user_id=current_user.id,
        role=GroupRole.LEADER,
    )
    db.add(leader)
    db.commit()
    db.refresh(group)

    return GroupCreateResponse(
        groupId=group.group_id,
        name=group.name,
        createdAt=group.created_at,
        leaderName=current_user.nickname,
        memberCount=1,
        maxMembers=group.max_members,
        description=group.description,
        isPrivate=group.is_private,
        isJoined=True,
    )


def _progress_percent(db: Session, user_id: int, book_id: int, total_pages: int | None) -> float:
    max_end_page = (
        db.query(func.max(ReadingSession.end_page))
        .filter(ReadingSession.user_id == user_id, ReadingSession.book_id == book_id)
        .scalar()
    )
    if not max_end_page or not total_pages:
        return 0.0
    return round((float(max_end_page) / float(total_pages)) * 100.0, 2)


def _require_member(db: Session, group: Group, user_id: int) -> GroupMember:
    member = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == user_id)
        .first()
    )
    if not member:
        raise HTTPException(status_code=403, detail="Not a group member")
    return member


def _current_mission_book(db: Session, group_id: int) -> GroupMonthlyBook | None:
    return (
        db.query(GroupMonthlyBook)
        .filter(GroupMonthlyBook.group_id == group_id)
        .order_by(GroupMonthlyBook.created_at.desc(), GroupMonthlyBook.id.desc())
        .first()
    )


def _group_member_user_ids(db: Session, group_id: int, *, exclude_user_id: int | None = None) -> list[int]:
    query = db.query(GroupMember.user_id).filter(GroupMember.group_id == group_id)
    if exclude_user_id is not None:
        query = query.filter(GroupMember.user_id != exclude_user_id)
    return [row[0] for row in query.all()]


def _default_profile_thumbnail(name: str) -> str:
    safe_name = quote(name or 'BookStopper')
    return f"https://ui-avatars.com/api/?name={safe_name}&background=EFE4D2&color=5B4636&size=256"


def _notify_group_members(
    db: Session,
    *,
    group: Group,
    recipient_user_ids: list[int],
    actor: User,
    notification_type: NotificationType,
    title: str,
    body: str,
    target_info: dict,
    thumbnail_url: str | None = None,
):
    for user_id in recipient_user_ids:
        if user_id == actor.id:
            continue
        payload = {"groupId": group.group_id, "actorId": actor.id, "actorName": actor.nickname, **target_info}
        resolved_thumbnail = thumbnail_url or _default_profile_thumbnail(actor.nickname)
        create_notification(
            db,
            user_id,
            title=title,
            body=body,
            notification_type=notification_type,
            target_info=payload,
            thumbnail_url=resolved_thumbnail,
            send_push=True,
            data=payload,
        )


def _notify_group_post_interaction(
    db: Session,
    *,
    group: Group,
    actor: User,
    post: GroupPost,
    notification_type: NotificationType,
    body: str,
    comment: GroupComment | None = None,
):
    recipients: set[int] = set()
    if post.user_id != actor.id:
        recipients.add(post.user_id)
    if comment is not None and comment.user_id != actor.id:
        recipients.add(comment.user_id)
    if not recipients:
        return

    target_info = {"groupId": group.group_id, "postId": post.id, "actorId": actor.id, "actorName": actor.nickname}
    thumbnail_url = _default_profile_thumbnail(actor.nickname)
    if comment is not None:
        target_info["commentId"] = comment.id

    for user_id in recipients:
        create_notification(
            db,
            user_id,
            title=actor.nickname,
            body=body,
            notification_type=notification_type,
            target_info=target_info,
            thumbnail_url=thumbnail_url,
            send_push=True,
            data=target_info,
        )


def _build_group_boards(db: Session, group: Group) -> list[GroupBoardItem]:
    boards = [
        GroupBoardItem(
            boardKey="ANNOUNCEMENT",
            boardType="ANNOUNCEMENT",
            label="공지사항",
        ),
        GroupBoardItem(
            boardKey="FREE",
            boardType="FREE",
            label="자유 게시판",
        ),
    ]

    mission_rows = (
        db.query(GroupMonthlyBook, Book)
        .join(Book, GroupMonthlyBook.book_id == Book.id)
        .filter(GroupMonthlyBook.group_id == group.id)
        .order_by(GroupMonthlyBook.created_at.desc(), GroupMonthlyBook.id.desc())
        .all()
    )
    for index, (_, book) in enumerate(mission_rows):
        boards.append(
            GroupBoardItem(
                boardKey=f"MISSION:{book.id}",
                boardType="MISSION",
                label=f"{book.title} 게시판",
                isArchived=index != 0,
                bookId=book.id,
                isbn13=book.isbn_13,
                title=book.title,
                thumbnail=book.thumbnail,
            )
        )
    return boards


def _normalize_records_payload(records: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for item in records or []:
        record_type = str(item.get("recordType") or "").strip().upper()
        record_id = item.get("recordId")
        if record_type not in {"BOOKMARK", "HIGHLIGHT", "NOTE"}:
            raise HTTPException(status_code=400, detail="Invalid recordType")
        if not isinstance(record_id, int) or record_id <= 0:
            raise HTTPException(status_code=400, detail="Invalid recordId")
        key = (record_type, record_id)
        if key in seen:
            continue
        seen.add(key)
        normalized.append({"recordType": record_type, "recordId": record_id})
    return normalized


def _serialize_group_post_records(post: GroupPost) -> list[GroupPostRecordItem]:
    items = post.records or []
    return [
        GroupPostRecordItem(recordType=str(item.get("recordType") or ""), recordId=int(item.get("recordId")))
        for item in items
        if item.get("recordType") and item.get("recordId")
    ]


def _normalize_discussion_payload(discussion: dict | None) -> dict | None:
    if discussion is None:
        return None
    question = (discussion.get("question") or discussion.get("topic") or "").strip()
    raw_options = discussion.get("options") or []
    if not question:
        raise HTTPException(status_code=400, detail="Discussion question is required")
    if not isinstance(raw_options, list) or len(raw_options) < 2:
        raise HTTPException(status_code=400, detail="Discussion options must have at least 2 items")

    normalized_options = []
    for idx, option in enumerate(raw_options, start=1):
        if isinstance(option, dict):
            label = (option.get("label") or option.get("text") or "").strip()
            option_id = option.get("optionId") or idx
        else:
            label = str(option).strip()
            option_id = idx
        if not label:
            raise HTTPException(status_code=400, detail="Discussion option label is required")
        normalized_options.append({"optionId": int(option_id), "label": label})

    ends_at = discussion.get("endsAt") or discussion.get("voteEndsAt")
    if ends_at:
        try:
            datetime.fromisoformat(str(ends_at).replace("Z", "+00:00"))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid discussion endsAt format") from exc

    return {
        "question": question,
        "options": normalized_options,
        "endsAt": ends_at,
    }


def _serialize_discussion(db: Session, post: GroupPost, user_id: int) -> dict | None:
    if not post.discussion:
        return None

    discussion = dict(post.discussion)
    options = discussion.get("options") or []
    option_ids = [int(option.get("optionId")) for option in options if option.get("optionId") is not None]
    votes = (
        db.query(GroupPostDiscussionVote)
        .filter(GroupPostDiscussionVote.post_id == post.id)
        .all()
    )
    vote_counts = {option_id: 0 for option_id in option_ids}
    my_vote = None
    for vote in votes:
        vote_counts[vote.option_id] = vote_counts.get(vote.option_id, 0) + 1
        if vote.user_id == user_id:
            my_vote = vote.option_id

    ends_at_raw = discussion.get("endsAt")
    is_closed = False
    if ends_at_raw:
        try:
            ends_at = datetime.fromisoformat(str(ends_at_raw).replace("Z", "+00:00"))
            is_closed = ends_at <= datetime.utcnow().astimezone(ends_at.tzinfo)
        except ValueError:
            is_closed = False

    return {
        "question": discussion.get("question"),
        "endsAt": ends_at_raw,
        "isClosed": is_closed,
        "myVoteOptionId": my_vote,
        "totalVotes": len(votes),
        "options": [
            {
                "optionId": int(option.get("optionId")),
                "label": option.get("label"),
                "voteCount": vote_counts.get(int(option.get("optionId")), 0),
            }
            for option in options
        ],
    }


_GROUP_REPORT_REASON_CODES = {item["code"] for item in GROUP_REPORT_REASON_OPTIONS}


def _validate_report_reason(payload: GroupReportRequest) -> None:
    if payload.reasonCode not in _GROUP_REPORT_REASON_CODES:
        raise HTTPException(status_code=400, detail="Invalid report reason code")
    if payload.reasonCode == "OTHER" and not (payload.reasonDetail or "").strip():
        raise HTTPException(status_code=400, detail="reasonDetail is required for OTHER")


@router.get("/search", response_model=GroupSearchResponse, summary="그룹 검색")
def search_groups(
    query: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    term = query.strip()
    groups = (
        db.query(Group)
        .filter(
            Group.name.ilike(f"%{term}%")
            | Group.group_id.ilike(f"%{term}%")
        )
        .all()
    )
    items = []
    for g in groups:
        member_count = db.query(GroupMember).filter(GroupMember.group_id == g.id).count()
        items.append(
            GroupSearchItem(
                groupId=g.group_id,
                name=g.name,
                backgroundImage=g.background_image,
                description=g.description,
                memberCount=member_count,
                maxMembers=g.max_members,
            )
        )
    return GroupSearchResponse(groups=items)



@router.get("/report-reasons", response_model=GroupReportReasonListResponse, summary="신고 사유 목록")
def list_group_report_reasons():
    return GroupReportReasonListResponse(
        reasons=[GroupReportReasonItem(**item) for item in GROUP_REPORT_REASON_OPTIONS]
    )



@router.get("/recommendations", response_model=GroupRecommendationResponse, summary="추천 그룹")
def group_recommendations(
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    groups = db.query(Group).filter(Group.is_private == False).all()  # noqa: E712
    scored = []
    for g in groups:
        member_count = db.query(GroupMember).filter(GroupMember.group_id == g.id).count()
        post_count = db.query(GroupPost).filter(GroupPost.group_id == g.id).count()
        comment_count = db.query(GroupComment).join(GroupPost, GroupComment.post_id == GroupPost.id).filter(GroupPost.group_id == g.id).count()
        score = member_count + post_count + comment_count
        scored.append((score, g, member_count))
    scored.sort(key=lambda x: x[0], reverse=True)
    items = [
        GroupRecommendationItem(
            groupId=g.group_id,
            name=g.name,
            backgroundImage=g.background_image,
            description=g.description,
            memberCount=member_count,
            maxMembers=g.max_members,
        )
        for _, g, member_count in scored[:limit]
    ]
    return GroupRecommendationResponse(groups=items)


@router.get("/{groupId}", response_model=GroupDetailResponse, summary="그룹 상세 조회")
def get_group_detail(
    groupId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    leader = db.query(User).filter(User.id == group.leader_user_id).first()

    members = (
        db.query(GroupMember, User)
        .join(User, GroupMember.user_id == User.id)
        .filter(GroupMember.group_id == group.id)
        .all()
    )
    member_infos: list[GroupMemberInfo] = []

    mission_rows = (
        db.query(GroupMonthlyBook, Book)
        .join(Book, GroupMonthlyBook.book_id == Book.id)
        .filter(GroupMonthlyBook.group_id == group.id)
        .order_by(GroupMonthlyBook.created_at.desc(), GroupMonthlyBook.id.desc())
        .all()
    )
    mission_books: list[GroupMissionBookInfo] = []
    current_mission_book_info: GroupMissionBookInfo | None = None
    current_mission_book = mission_rows[0][1] if mission_rows else None

    total_pages = current_mission_book.total_pages if current_mission_book else None

    for gm, user in members:
        progress = 0.0
        if current_mission_book:
            progress = _progress_percent(db, user.id, current_mission_book.id, total_pages)
        member_infos.append(
            GroupMemberInfo(
                memberId=user.id,
                nickname=user.nickname,
                profileImage=user.profile_image_url,
                profileImageUrl=user.profile_image_url,
                missionProgressPercent=progress,
            )
        )

    is_joined = any(m.user_id == current_user.id for m, _ in members)
    is_leader = group.leader_user_id == current_user.id

    for index, (_, mission_book) in enumerate(mission_rows):
        authors = (
            db.query(Author.name)
            .join(BookAuthor, BookAuthor.author_id == Author.id)
            .filter(BookAuthor.book_id == mission_book.id)
            .all()
        )
        author_names = [a[0] for a in authors]
        group_avg = 0.0
        progress_values = []
        for _, user in members:
            progress = _progress_percent(db, user.id, mission_book.id, mission_book.total_pages)
            progress_values.append(progress)
        if progress_values:
            group_avg = round(sum(progress_values) / len(progress_values), 2)
        my_progress = _progress_percent(db, current_user.id, mission_book.id, mission_book.total_pages)
        mission_info = GroupMissionBookInfo(
            bookId=mission_book.id,
            isbn13=mission_book.isbn_13,
            title=mission_book.title,
            authors=author_names,
            thumbnail=mission_book.thumbnail,
            totalPages=mission_book.total_pages,
            groupAverageProgressPercent=group_avg,
            myProgressPercent=my_progress,
        )
        if index == 0:
            current_mission_book_info = mission_info
        mission_books.append(mission_info)

    return GroupDetailResponse(
        groupId=group.group_id,
        name=group.name,
        backgroundImage=group.background_image,
        createdAt=group.created_at,
        leaderId=group.leader_user_id,
        leaderName=leader.nickname if leader else None,
        memberCount=len(member_infos),
        maxMembers=group.max_members,
        description=group.description,
        isPrivate=group.is_private,
        isJoined=is_joined,
        isLeader=is_leader,
        currentMissionBook=current_mission_book_info,
        missionBooks=mission_books,
        members=member_infos if is_joined else [],
    )


@router.patch("/{groupId}", response_model=GroupUpdateResponse, summary="그룹 정보 수정")
def update_group(
    groupId: str,
    payload: GroupUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.leader_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only leader can update group")

    if payload.maxMembers is not None and payload.maxMembers not in ALLOWED_MAX_MEMBERS:
        raise HTTPException(status_code=400, detail="Invalid maxMembers")

    if payload.name is not None:
        name = payload.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Group name cannot be blank")
        group.name = name

    if payload.backgroundImage is not None:
        group.background_image = payload.backgroundImage

    if payload.description is not None:
        group.description = payload.description.strip() or None

    if payload.maxMembers is not None:
        current_member_count = db.query(GroupMember).filter(GroupMember.group_id == group.id).count()
        if payload.maxMembers < current_member_count:
            raise HTTPException(status_code=400, detail="maxMembers cannot be smaller than current member count")
        group.max_members = payload.maxMembers

    if payload.isPrivate is not None:
        if payload.isPrivate and not group.is_private:
            raise HTTPException(status_code=400, detail="Switching to private group requires password setup")
        if not payload.isPrivate:
            group.is_private = False
            group.password_hash = None
        else:
            group.is_private = True

    db.commit()
    db.refresh(group)

    return GroupUpdateResponse(
        groupId=group.group_id,
        name=group.name,
        backgroundImage=group.background_image,
        description=group.description,
        maxMembers=group.max_members,
        isPrivate=group.is_private,
    )


@router.patch("/{groupId}/mission-book", summary="미션책 변경")
def update_mission_book(
    groupId: str,
    payload: MissionBookUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.leader_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only leader can update mission book")

    book = (
        db.query(Book)
        .filter((Book.isbn_13 == payload.isbn) | (Book.isbn_10 == payload.isbn))
        .first()
    )
    if not book:
        raise HTTPException(status_code=404, detail="Book not found")

    month = datetime.utcnow().strftime("%Y-%m")
    current = _current_mission_book(db, group.id)
    if current and current.book_id == book.id:
        return {"ok": True, "unchanged": True}

    db.add(GroupMonthlyBook(group_id=group.id, book_id=book.id, month=month))
    db.commit()

    member_user_ids = _group_member_user_ids(db, group.id, exclude_user_id=current_user.id)
    _notify_group_members(
        db,
        group=group,
        recipient_user_ids=member_user_ids,
        actor=current_user,
        notification_type=NotificationType.GROUP_MISSION_UPDATE,
        title=f"{group.name} 미션책 변경",
        body=f"이번 달 미션책이 '{book.title}'로 바뀌었어요.",
        target_info={"groupId": group.group_id, "bookId": book.id},
        thumbnail_url=book.thumbnail,
    )
    return {"ok": True, "unchanged": False}


@router.get("/{groupId}/mission-books/history", response_model=MissionBookHistoryResponse, summary="미션책 히스토리")
def mission_book_history(
    groupId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)

    rows = (
        db.query(GroupMonthlyBook, Book)
        .join(Book, GroupMonthlyBook.book_id == Book.id)
        .filter(GroupMonthlyBook.group_id == group.id)
        .order_by(GroupMonthlyBook.created_at.desc(), GroupMonthlyBook.id.desc())
        .all()
    )
    items = [
        MissionBookHistoryItem(
            month=gb.month,
            bookId=book.id,
            isbn13=book.isbn_13,
            title=book.title,
            thumbnail=book.thumbnail,
            boardBookId=book.id,
        )
        for gb, book in rows
    ]
    return MissionBookHistoryResponse(items=items)


@router.get("/{groupId}/boards", response_model=GroupBoardListResponse, summary="그룹 게시판 목록")
def list_group_boards(
    groupId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)
    return GroupBoardListResponse(boards=_build_group_boards(db, group))


@router.get("/{groupId}/members/{memberId}", response_model=GroupMemberProfileResponse, summary="그룹 멤버 상세 프로필")
def get_group_member_profile(
    groupId: str,
    memberId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)

    member = (
        db.query(GroupMember, User)
        .join(User, GroupMember.user_id == User.id)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == memberId)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    _, user = member
    mission_rows = (
        db.query(GroupMonthlyBook, Book)
        .join(Book, GroupMonthlyBook.book_id == Book.id)
        .filter(GroupMonthlyBook.group_id == group.id)
        .order_by(GroupMonthlyBook.created_at.desc(), GroupMonthlyBook.id.desc())
        .all()
    )
    mission_books = [
        GroupMemberProfileMissionBookItem(
            month=gb.month,
            bookId=book.id,
            isbn13=book.isbn_13,
            title=book.title,
            thumbnail=book.thumbnail,
            progressPercent=_progress_percent(db, user.id, book.id, book.total_pages),
            boardBookId=book.id,
        )
        for gb, book in mission_rows
    ]
    return GroupMemberProfileResponse(
        memberId=user.id,
        nickname=user.nickname,
        profileImage=user.profile_image_url,
        missionBooks=mission_books,
    )


@router.get("/{groupId}/announcements", response_model=GroupPostListResponse, summary="공지사항 리스트")
def list_announcements(
    groupId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)

    posts = (
        db.query(GroupPost)
        .filter(GroupPost.group_id == group.id, GroupPost.post_type == GroupPostType.ANNOUNCEMENT)
        .order_by(
            GroupPost.is_pinned.desc(),
            GroupPost.pinned_at.desc(),
            GroupPost.created_at.desc(),
            GroupPost.id.desc(),
        )
        .all()
    )
    results: list[GroupPostBase] = []
    for post in posts:
        like_count = db.query(GroupPostLike.id).filter(GroupPostLike.post_id == post.id).count()
        comment_count = db.query(GroupComment.id).filter(GroupComment.post_id == post.id).count()
        is_liked = (
            db.query(GroupPostLike.id)
            .filter(GroupPostLike.post_id == post.id, GroupPostLike.user_id == current_user.id)
            .first()
            is not None
        )
        author = db.query(User).filter(User.id == post.user_id).first()
        results.append(
            GroupPostBase(
                postId=post.id,
                groupId=group.group_id,
                type=post.post_type.value,
                title=post.title,
                content=post.content,
                bookId=post.book_id,
                createdAt=post.created_at,
                isPinned=post.is_pinned,
                pinnedAt=post.pinned_at,
                authorId=post.user_id,
                authorName=author.nickname if author else "",
                profileImageUrl=author.profile_image_url if author else None,
                likeCount=like_count,
                commentCount=comment_count,
                isLiked=is_liked,
                records=_serialize_group_post_records(post),
                discussion=_serialize_discussion(db, post, current_user.id),
            )
        )
    return GroupPostListResponse(posts=results)


@router.post("/{groupId}/announcements", response_model=GroupPostBase, summary="공지사항 작성")
def create_announcement(
    groupId: str,
    payload: GroupPostCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.leader_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only leader can post announcements")

    post = GroupPost(
        group_id=group.id,
        user_id=current_user.id,
        post_type=GroupPostType.ANNOUNCEMENT,
        title=payload.title,
        content=payload.content,
        discussion=_normalize_discussion_payload(payload.discussion),
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    member_user_ids = _group_member_user_ids(db, group.id, exclude_user_id=current_user.id)
    _notify_group_members(
        db,
        group=group,
        recipient_user_ids=member_user_ids,
        actor=current_user,
        notification_type=NotificationType.GROUP_ANNOUNCEMENT,
        title=f"{group.name} 공지사항",
        body="새 공지사항이 올라왔어요.",
        target_info={"groupId": group.group_id, "postId": post.id},
    )

    return GroupPostBase(
        postId=post.id,
        groupId=group.group_id,
        type=post.post_type.value,
        title=post.title,
        content=post.content,
        bookId=post.book_id,
        createdAt=post.created_at,
        isPinned=post.is_pinned,
        pinnedAt=post.pinned_at,
        authorId=current_user.id,
        authorName=current_user.nickname,
        profileImageUrl=current_user.profile_image_url,
        likeCount=0,
        commentCount=0,
        isLiked=False,
        records=_serialize_group_post_records(post),
    )


@router.patch("/posts/{postId}/pin", response_model=GroupPostDetailResponse, summary="공지사항 핀 고정/해제")
def pin_announcement(
    postId: int,
    payload: GroupPinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    if post.post_type != GroupPostType.ANNOUNCEMENT:
        raise HTTPException(status_code=400, detail="Pin is only available for announcements")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    if not group or group.leader_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only leader can pin announcements")

    post.is_pinned = payload.isPinned
    post.pinned_at = datetime.utcnow() if payload.isPinned else None
    db.add(post)
    db.commit()
    db.refresh(post)

    like_count = db.query(GroupPostLike.id).filter(GroupPostLike.post_id == post.id).count()
    comment_count = db.query(GroupComment.id).filter(GroupComment.post_id == post.id).count()
    is_liked = (
        db.query(GroupPostLike.id)
        .filter(GroupPostLike.post_id == post.id, GroupPostLike.user_id == current_user.id)
        .first()
        is not None
    )
    author = db.query(User).filter(User.id == post.user_id).first()
    return GroupPostDetailResponse(
        postId=post.id,
        groupId=group.group_id,
        type=post.post_type.value,
        title=post.title,
        content=post.content,
        bookId=post.book_id,
        createdAt=post.created_at,
        isPinned=post.is_pinned,
        pinnedAt=post.pinned_at,
        authorId=post.user_id,
        authorName=author.nickname if author else "",
        profileImageUrl=author.profile_image_url if author else None,
        likeCount=like_count,
        commentCount=comment_count,
        isLiked=is_liked,
        discussion=_serialize_discussion(db, post, current_user.id),
        recordId=post.record_id,
        records=_serialize_group_post_records(post),
    )


@router.get("/posts/{postId}", response_model=GroupPostDetailResponse, summary="게시글 상세")
def get_group_post_detail(
    postId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)

    like_count = db.query(GroupPostLike.id).filter(GroupPostLike.post_id == post.id).count()
    comment_count = db.query(GroupComment.id).filter(GroupComment.post_id == post.id).count()
    is_liked = (
        db.query(GroupPostLike.id)
        .filter(GroupPostLike.post_id == post.id, GroupPostLike.user_id == current_user.id)
        .first()
        is not None
    )
    author = db.query(User).filter(User.id == post.user_id).first()
    return GroupPostDetailResponse(
        postId=post.id,
        groupId=group.group_id,
        type=post.post_type.value,
        title=post.title,
        content=post.content,
        bookId=post.book_id,
        createdAt=post.created_at,
        isPinned=post.is_pinned,
        pinnedAt=post.pinned_at,
        authorId=post.user_id,
        authorName=author.nickname if author else "",
        profileImageUrl=author.profile_image_url if author else None,
        likeCount=like_count,
        commentCount=comment_count,
        isLiked=is_liked,
        discussion=_serialize_discussion(db, post, current_user.id),
        recordId=post.record_id,
        records=_serialize_group_post_records(post),
    )


@router.patch("/posts/{postId}", response_model=GroupPostDetailResponse, summary="게시글 수정")
def update_group_post(
    postId: int,
    payload: GroupPostUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)
    if post.post_type == GroupPostType.ANNOUNCEMENT:
        if group.leader_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only leader can update announcements")
    elif post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only author can update post")

    if payload.content is not None:
        post.content = payload.content
    if payload.title is not None:
        post.title = payload.title
    discussion_was_enabled = post.discussion is not None
    if payload.discussion is not None:
        post.discussion = _normalize_discussion_payload(payload.discussion)
    if payload.bookId is not None and post.post_type == GroupPostType.FREE:
        post.book_id = payload.bookId
    db.add(post)
    db.commit()
    db.refresh(post)

    if post.discussion and not discussion_was_enabled:
        _notify_group_members(
            db,
            group=group,
            recipient_user_ids=_group_member_user_ids(db, group.id, exclude_user_id=current_user.id),
            actor=current_user,
            notification_type=NotificationType.GROUP_DISCUSSION,
            title=f"{group.name} 토론",
            body='새로운 토론이 열렸어요.',
            target_info={'postId': post.id, 'eventKind': 'GROUP_DISCUSSION_OPEN'},
            thumbnail_url=post.book.thumbnail if post.book else None,
        )

    like_count = db.query(GroupPostLike.id).filter(GroupPostLike.post_id == post.id).count()
    comment_count = db.query(GroupComment.id).filter(GroupComment.post_id == post.id).count()
    is_liked = (
        db.query(GroupPostLike.id)
        .filter(GroupPostLike.post_id == post.id, GroupPostLike.user_id == current_user.id)
        .first()
        is not None
    )
    author = db.query(User).filter(User.id == post.user_id).first()
    return GroupPostDetailResponse(
        postId=post.id,
        groupId=group.group_id,
        type=post.post_type.value,
        title=post.title,
        content=post.content,
        bookId=post.book_id,
        createdAt=post.created_at,
        isPinned=post.is_pinned,
        pinnedAt=post.pinned_at,
        authorId=post.user_id,
        authorName=author.nickname if author else "",
        profileImageUrl=author.profile_image_url if author else None,
        likeCount=like_count,
        commentCount=comment_count,
        isLiked=is_liked,
        discussion=_serialize_discussion(db, post, current_user.id),
        recordId=post.record_id,
        records=_serialize_group_post_records(post),
    )


@router.delete("/posts/{postId}", summary="게시글 삭제")
def delete_group_post(
    postId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)
    if post.post_type == GroupPostType.ANNOUNCEMENT:
        if group.leader_user_id != current_user.id:
            raise HTTPException(status_code=403, detail="Only leader can delete announcements")
    elif post.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only author can delete post")
    db.delete(post)
    db.commit()
    return {"ok": True}


@router.get("/{groupId}/posts", response_model=GroupPostListResponse, summary="게시글 리스트")
def list_group_posts(
    groupId: str,
    type: str | None = Query(default=None, description="MISSION or FREE"),
    bookId: int | None = Query(default=None, description="미션 게시판용 bookId 필터"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)

    q = db.query(GroupPost).filter(GroupPost.group_id == group.id, GroupPost.post_type != GroupPostType.ANNOUNCEMENT)
    if type:
        type_upper = type.upper()
        if type_upper not in {"MISSION", "FREE"}:
            raise HTTPException(status_code=400, detail="Invalid post type")
        q = q.filter(GroupPost.post_type == GroupPostType[type_upper])
    if bookId is not None:
        q = q.filter(GroupPost.book_id == bookId)
    posts = q.order_by(GroupPost.created_at.desc(), GroupPost.id.desc()).all()

    results: list[GroupPostBase] = []
    for post in posts:
        like_count = db.query(GroupPostLike.id).filter(GroupPostLike.post_id == post.id).count()
        comment_count = db.query(GroupComment.id).filter(GroupComment.post_id == post.id).count()
        is_liked = (
            db.query(GroupPostLike.id)
            .filter(GroupPostLike.post_id == post.id, GroupPostLike.user_id == current_user.id)
            .first()
            is not None
        )
        author = db.query(User).filter(User.id == post.user_id).first()
        results.append(
            GroupPostBase(
                postId=post.id,
                groupId=group.group_id,
                type=post.post_type.value,
                title=post.title,
                content=post.content,
                bookId=post.book_id,
                createdAt=post.created_at,
                isPinned=post.is_pinned,
                pinnedAt=post.pinned_at,
                authorId=post.user_id,
                authorName=author.nickname if author else "",
                profileImageUrl=author.profile_image_url if author else None,
                likeCount=like_count,
                commentCount=comment_count,
                isLiked=is_liked,
                records=_serialize_group_post_records(post),
            )
        )
    return GroupPostListResponse(posts=results)


@router.post("/{groupId}/posts", response_model=GroupPostBase, summary="게시글 작성")
def create_group_post(
    groupId: str,
    payload: GroupPostCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)

    if not payload.type:
        raise HTTPException(status_code=400, detail="Post type required")
    post_type = payload.type.upper()
    if post_type not in {"MISSION", "FREE"}:
        raise HTTPException(status_code=400, detail="Invalid post type")

    book_id = payload.bookId
    if post_type == "MISSION":
        mission = _current_mission_book(db, group.id)
        if not mission:
            raise HTTPException(status_code=400, detail="Mission book not set")
        book_id = mission.book_id

    post = GroupPost(
        group_id=group.id,
        user_id=current_user.id,
        post_type=GroupPostType[post_type],
        title=payload.title,
        content=payload.content,
        book_id=book_id,
        record_id=None,
        records=_normalize_records_payload([item.model_dump() for item in (payload.records or [])]),
        discussion=_normalize_discussion_payload(payload.discussion),
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    if post.discussion:
        _notify_group_members(
            db,
            group=group,
            recipient_user_ids=_group_member_user_ids(db, group.id, exclude_user_id=current_user.id),
            actor=current_user,
            notification_type=NotificationType.GROUP_DISCUSSION,
            title=f"{group.name} 토론",
            body='새로운 토론이 열렸어요.',
            target_info={'postId': post.id, 'eventKind': 'GROUP_DISCUSSION_OPEN'},
            thumbnail_url=post.book.thumbnail if post.book else None,
        )

    return GroupPostBase(
        postId=post.id,
        groupId=group.group_id,
        type=post.post_type.value,
        title=post.title,
        content=post.content,
        bookId=post.book_id,
        createdAt=post.created_at,
        isPinned=post.is_pinned,
        pinnedAt=post.pinned_at,
        authorId=current_user.id,
        authorName=current_user.nickname,
        profileImageUrl=current_user.profile_image_url,
        likeCount=0,
        commentCount=0,
        isLiked=False,
        records=_serialize_group_post_records(post),
    )


@router.post("/{groupId}/posts/share", response_model=GroupPostBase, summary="독서기록 그룹 공유")
def share_group_post(
    groupId: str,
    payload: GroupSharePostRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)

    session = (
        db.query(ReadingSession)
        .filter(ReadingSession.id == payload.recordId, ReadingSession.user_id == current_user.id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Reading record not found")

    board_type = payload.boardType.upper()
    if board_type not in {"MISSION", "FREE"}:
        raise HTTPException(status_code=400, detail="Invalid boardType")

    book_id = session.book_id
    if board_type == "MISSION":
        mission = _current_mission_book(db, group.id)
        if not mission:
            raise HTTPException(status_code=400, detail="Mission book not set")
        if mission.book_id != session.book_id:
            raise HTTPException(status_code=400, detail="Reading record book does not match current mission book")
        book_id = mission.book_id

    post = GroupPost(
        group_id=group.id,
        user_id=current_user.id,
        post_type=GroupPostType[board_type],
        title=None,
        content=(payload.content or "독서기록을 공유했습니다.").strip(),
        book_id=book_id,
        record_id=session.id,
        discussion=_normalize_discussion_payload(payload.discussion),
    )
    db.add(post)
    db.commit()
    db.refresh(post)

    if post.discussion:
        _notify_group_members(
            db,
            group=group,
            recipient_user_ids=_group_member_user_ids(db, group.id, exclude_user_id=current_user.id),
            actor=current_user,
            notification_type=NotificationType.GROUP_DISCUSSION,
            title=f"{group.name} 토론",
            body='새로운 토론이 열렸어요.',
            target_info={'postId': post.id, 'eventKind': 'GROUP_DISCUSSION_OPEN'},
            thumbnail_url=post.book.thumbnail if post.book else None,
        )

    return GroupPostBase(
        postId=post.id,
        groupId=group.group_id,
        type=post.post_type.value,
        title=post.title,
        content=post.content,
        bookId=post.book_id,
        createdAt=post.created_at,
        isPinned=post.is_pinned,
        pinnedAt=post.pinned_at,
        authorId=current_user.id,
        authorName=current_user.nickname,
        profileImageUrl=current_user.profile_image_url,
        likeCount=0,
        commentCount=0,
        isLiked=False,
    )


@router.post(
    "/{groupId}/posts/share-note",
    response_model=GroupShareNotePrefillResponse,
    summary="개인 메모 그룹 글쓰기 초안 가져오기",
)
def share_group_note(
    groupId: str,
    payload: GroupShareNoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    _require_member(db, group, current_user.id)

    row = (
        db.query(Note, UserBook, Book)
        .join(UserBook, Note.user_book_id == UserBook.id)
        .join(Book, UserBook.book_id == Book.id)
        .filter(Note.id == payload.noteId, UserBook.user_id == current_user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Note not found")

    note, _, book = row
    board_type = payload.boardType.upper()
    if board_type not in {"MISSION", "FREE"}:
        raise HTTPException(status_code=400, detail="Invalid boardType")

    is_mission_matched = True
    if board_type == "MISSION":
        mission = _current_mission_book(db, group.id)
        if not mission:
            raise HTTPException(status_code=400, detail="Mission book not set")
        if mission.book_id != book.id:
            is_mission_matched = False
            raise HTTPException(status_code=400, detail="Note book does not match current mission book")

    return GroupShareNotePrefillResponse(
        groupId=group.group_id,
        boardType=board_type,
        noteId=note.id,
        page=note.page,
        title=None,
        content=note.content,
        bookId=book.id,
        isbn13=book.isbn_13,
        bookTitle=book.title,
        thumbnail=book.thumbnail,
        isMissionMatched=is_mission_matched,
    )


@router.post("/posts/{postId}/discussion/vote", summary="토론 투표")
def vote_group_discussion(
    postId: int,
    payload: GroupDiscussionVoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)
    if not post.discussion:
        raise HTTPException(status_code=400, detail="Discussion is not configured for this post")

    discussion = _serialize_discussion(db, post, current_user.id)
    option_map = {int(option["optionId"]): option for option in discussion["options"]}
    if payload.optionId not in option_map:
        raise HTTPException(status_code=400, detail="Invalid discussion option")
    if discussion["isClosed"]:
        raise HTTPException(status_code=400, detail="Discussion is closed")

    vote = (
        db.query(GroupPostDiscussionVote)
        .filter(
            GroupPostDiscussionVote.post_id == post.id,
            GroupPostDiscussionVote.user_id == current_user.id,
        )
        .first()
    )
    if vote:
        vote.option_id = payload.optionId
        db.add(vote)
    else:
        db.add(
            GroupPostDiscussionVote(
                post_id=post.id,
                user_id=current_user.id,
                option_id=payload.optionId,
            )
        )
    db.commit()
    db.refresh(post)
    return {
        "ok": True,
        "discussion": _serialize_discussion(db, post, current_user.id),
    }


@router.post("/posts/{postId}/like", summary="게시글 좋아요")
def like_post(
    postId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)
    exists = (
        db.query(GroupPostLike.id)
        .filter(GroupPostLike.post_id == post.id, GroupPostLike.user_id == current_user.id)
        .first()
    )
    if not exists:
        db.add(GroupPostLike(post_id=post.id, user_id=current_user.id))
        db.commit()
        _notify_group_post_interaction(
            db,
            group=group,
            actor=current_user,
            post=post,
            notification_type=NotificationType.SOCIAL_LIKE,
            body="내 게시글에 좋아요가 추가됐어요.",
        )
    return {"ok": True}


@router.delete("/posts/{postId}/like", summary="게시글 좋아요 취소")
def unlike_post(
    postId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)
    db.query(GroupPostLike).filter(
        GroupPostLike.post_id == post.id, GroupPostLike.user_id == current_user.id
    ).delete()
    db.commit()
    return {"ok": True}


@router.get("/posts/{postId}/comments", response_model=GroupCommentListResponse, summary="댓글 리스트")
def list_post_comments(
    postId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)

    comments = (
        db.query(GroupComment)
        .filter(GroupComment.post_id == post.id)
        .order_by(GroupComment.created_at.asc(), GroupComment.id.asc())
        .all()
    )
    by_parent: dict[int | None, list[GroupComment]] = {}
    for c in comments:
        by_parent.setdefault(c.parent_id, []).append(c)

    comment_user_ids = {c.user_id for c in comments}
    user_map = {
        u.id: u
        for u in db.query(User).filter(User.id.in_(comment_user_ids)).all()
    } if comment_user_ids else {}

    def build_item(c: GroupComment) -> GroupCommentItem:
        like_count = db.query(GroupCommentLike.id).filter(GroupCommentLike.comment_id == c.id).count()
        is_liked = (
            db.query(GroupCommentLike.id)
            .filter(GroupCommentLike.comment_id == c.id, GroupCommentLike.user_id == current_user.id)
            .first()
            is not None
        )
        user = user_map.get(c.user_id)
        replies = []
        for r in by_parent.get(c.id, []):
            r_like = db.query(GroupCommentLike.id).filter(GroupCommentLike.comment_id == r.id).count()
            r_is_liked = (
                db.query(GroupCommentLike.id)
                .filter(GroupCommentLike.comment_id == r.id, GroupCommentLike.user_id == current_user.id)
                .first()
                is not None
            )
            r_user = user_map.get(r.user_id)
            replies.append(
                GroupCommentReply(
                    commentId=r.id,
                    userId=r.user_id,
                    userName=r_user.nickname if r_user else "",
                    profileImageUrl=r_user.profile_image_url if r_user else None,
                    content=r.content,
                    createdAt=r.created_at,
                    likeCount=r_like,
                    isLiked=r_is_liked,
                )
            )
        return GroupCommentItem(
            commentId=c.id,
            userId=c.user_id,
            userName=user.nickname if user else "",
            profileImageUrl=user.profile_image_url if user else None,
            content=c.content,
            createdAt=c.created_at,
            likeCount=like_count,
            isLiked=is_liked,
            replies=replies,
        )

    items = [build_item(c) for c in by_parent.get(None, [])]
    return GroupCommentListResponse(comments=items)


@router.post("/posts/{postId}/comments", response_model=GroupCommentItem, summary="댓글 작성")
def create_post_comment(
    postId: int,
    payload: GroupCommentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)

    comment = GroupComment(post_id=post.id, user_id=current_user.id, content=payload.content)
    db.add(comment)
    db.commit()
    db.refresh(comment)

    _notify_group_post_interaction(
        db,
        group=group,
        actor=current_user,
        post=post,
        notification_type=NotificationType.SOCIAL_COMMENT,
        body="내 게시글에 새 댓글이 달렸어요.",
    )

    return GroupCommentItem(
        commentId=comment.id,
        userId=current_user.id,
        userName=current_user.nickname,
        profileImageUrl=current_user.profile_image_url,
        content=comment.content,
        createdAt=comment.created_at,
        likeCount=0,
        isLiked=False,
        replies=[],
    )


@router.post("/comments/{commentId}/replies", response_model=GroupCommentReply, summary="답글 작성")
def create_comment_reply(
    commentId: int,
    payload: GroupCommentCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    parent = db.query(GroupComment).filter(GroupComment.id == commentId).first()
    if not parent:
        raise HTTPException(status_code=404, detail="Comment not found")
    post = db.query(GroupPost).filter(GroupPost.id == parent.post_id).first()
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)

    reply = GroupComment(
        post_id=parent.post_id,
        user_id=current_user.id,
        parent_id=parent.id,
        content=payload.content,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    _notify_group_post_interaction(
        db,
        group=group,
        actor=current_user,
        post=post,
        comment=parent,
        notification_type=NotificationType.SOCIAL_COMMENT,
        body="내 댓글에 답글이 달렸어요.",
    )

    return GroupCommentReply(
        commentId=reply.id,
        userId=current_user.id,
        userName=current_user.nickname,
        profileImageUrl=current_user.profile_image_url,
        content=reply.content,
        createdAt=reply.created_at,
        likeCount=0,
        isLiked=False,
    )


@router.post("/{groupId}/join", response_model=GroupJoinResponse, summary="그룹 가입")
def join_group(
    groupId: str,
    payload: GroupJoinRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    existing = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id)
        .first()
    )
    if existing:
        member_count = db.query(GroupMember).filter(GroupMember.group_id == group.id).count()
        return GroupJoinResponse(ok=True, isJoined=True, memberCount=member_count)

    member_count = db.query(GroupMember).filter(GroupMember.group_id == group.id).count()
    if group.max_members and member_count >= group.max_members:
        raise HTTPException(status_code=400, detail="Group is full")

    if group.is_private:
        if not payload.password:
            raise HTTPException(status_code=400, detail="Password required")
        if not group.password_hash or not verify_password(payload.password, group.password_hash):
            raise HTTPException(status_code=403, detail="Invalid password")

    db.add(GroupMember(group_id=group.id, user_id=current_user.id, role=GroupRole.MEMBER))
    db.commit()
    member_count = db.query(GroupMember).filter(GroupMember.group_id == group.id).count()

    if group.leader_user_id and group.leader_user_id != current_user.id:
        payload = {
            "groupId": group.group_id,
            "actorId": current_user.id,
            "actorName": current_user.nickname,
            "eventKind": "GROUP_JOIN",
        }
        create_notification(
            db,
            group.leader_user_id,
            title=f"{group.name} 멤버 알림",
            body=f"{current_user.nickname}님이 그룹에 가입했어요.",
            notification_type=NotificationType.GROUP_NOTICE,
            target_info=payload,
            thumbnail_url=_default_profile_thumbnail(current_user.nickname),
            send_push=True,
            data=payload,
        )
    return GroupJoinResponse(ok=True, isJoined=True, memberCount=member_count)


@router.delete("/{groupId}", response_model=GroupDeleteResponse, summary="그룹 삭제 (그룹장 전용)")
def delete_group(
    groupId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    membership = _require_member(db, group, current_user.id)
    if group.leader_user_id != current_user.id or membership.role != GroupRole.LEADER:
        raise HTTPException(status_code=403, detail="Only leader can delete group")

    recipient_user_ids = _group_member_user_ids(db, group.id, exclude_user_id=current_user.id)
    deleted_group_id = group.group_id
    deleted_group_name = group.name

    db.delete(group)
    db.commit()

    _notify_group_members(
        db,
        group=group,
        recipient_user_ids=recipient_user_ids,
        actor=current_user,
        notification_type=NotificationType.GROUP_NOTICE,
        title=f"{deleted_group_name} 안내",
        body="그룹이 삭제되었어요.",
        target_info={"eventKind": "GROUP_DELETED"},
    )

    return GroupDeleteResponse(
        ok=True,
        deletedGroupId=deleted_group_id,
        notifiedMemberCount=len(recipient_user_ids),
    )


@router.delete("/{groupId}/leave", response_model=GroupLeaveResponse, summary="그룹 탈퇴")
def leave_group(
    groupId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    member = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == current_user.id)
        .first()
    )
    if not member:
        member_count = db.query(GroupMember).filter(GroupMember.group_id == group.id).count()
        return GroupLeaveResponse(ok=True, isJoined=False, memberCount=member_count)
    if group.leader_user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Leader cannot leave group")

    db.delete(member)
    db.commit()
    member_count = db.query(GroupMember).filter(GroupMember.group_id == group.id).count()

    if group.leader_user_id and group.leader_user_id != current_user.id:
        payload = {
            "groupId": group.group_id,
            "actorId": current_user.id,
            "actorName": current_user.nickname,
            "eventKind": "GROUP_MEMBER_LEFT",
        }
        create_notification(
            db,
            group.leader_user_id,
            title=f"{group.name} 멤버 알림",
            body=f"{current_user.nickname}님이 그룹을 탈퇴했어요.",
            notification_type=NotificationType.GROUP_NOTICE,
            target_info=payload,
            thumbnail_url=_default_profile_thumbnail(current_user.nickname),
            send_push=True,
            data=payload,
        )
    return GroupLeaveResponse(ok=True, isJoined=False, memberCount=member_count)


@router.post("/comments/{commentId}/like", summary="댓글 좋아요")
def like_comment(
    commentId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = db.query(GroupComment).filter(GroupComment.id == commentId).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    post = db.query(GroupPost).filter(GroupPost.id == comment.post_id).first()
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)
    exists = (
        db.query(GroupCommentLike.id)
        .filter(GroupCommentLike.comment_id == comment.id, GroupCommentLike.user_id == current_user.id)
        .first()
    )
    if not exists:
        db.add(GroupCommentLike(comment_id=comment.id, user_id=current_user.id))
        db.commit()
        _notify_group_post_interaction(
            db,
            group=group,
            actor=current_user,
            post=post,
            comment=comment,
            notification_type=NotificationType.SOCIAL_LIKE,
            body="내 댓글에 좋아요가 추가됐어요.",
        )
    return {"ok": True}


@router.delete("/comments/{commentId}/like", summary="댓글 좋아요 취소")
def unlike_comment(
    commentId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = db.query(GroupComment).filter(GroupComment.id == commentId).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    post = db.query(GroupPost).filter(GroupPost.id == comment.post_id).first()
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)
    db.query(GroupCommentLike).filter(
        GroupCommentLike.comment_id == comment.id, GroupCommentLike.user_id == current_user.id
    ).delete()
    db.commit()
    return {"ok": True}


@router.post("/posts/{postId}/report", summary="게시글 신고")
def report_post(
    postId: int,
    payload: GroupReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    post = db.query(GroupPost).filter(GroupPost.id == postId).first()
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)

    exists = (
        db.query(GroupPostReport.id)
        .filter(
            GroupPostReport.post_id == post.id,
            GroupPostReport.reporter_user_id == current_user.id,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Already reported")
    _validate_report_reason(payload)

    db.add(
        GroupPostReport(
            post_id=post.id,
            reporter_user_id=current_user.id,
            reason_code=payload.reasonCode,
            reason=payload.reasonDetail,
        )
    )
    db.commit()
    return {"ok": True}


@router.post("/comments/{commentId}/report", summary="댓글 신고")
def report_comment(
    commentId: int,
    payload: GroupReportRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    comment = db.query(GroupComment).filter(GroupComment.id == commentId).first()
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    post = db.query(GroupPost).filter(GroupPost.id == comment.post_id).first()
    group = db.query(Group).filter(Group.id == post.group_id).first()
    _require_member(db, group, current_user.id)

    exists = (
        db.query(GroupCommentReport.id)
        .filter(
            GroupCommentReport.comment_id == comment.id,
            GroupCommentReport.reporter_user_id == current_user.id,
        )
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Already reported")
    _validate_report_reason(payload)

    db.add(
        GroupCommentReport(
            comment_id=comment.id,
            reporter_user_id=current_user.id,
            reason_code=payload.reasonCode,
            reason=payload.reasonDetail,
        )
    )
    db.commit()
    return {"ok": True}


@router.get("/{groupId}/reports", response_model=GroupReportInboxResponse, summary="그룹 신고함")
def get_group_reports(
    groupId: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.leader_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only leader can view reports")

    post_rows = (
        db.query(
            GroupPost.id,
            GroupPost.user_id,
            User.nickname,
            GroupPost.content,
            func.count(GroupPostReport.id).label("report_count"),
            func.max(GroupPostReport.created_at).label("last_reported_at"),
        )
        .join(GroupPostReport, GroupPostReport.post_id == GroupPost.id)
        .join(User, User.id == GroupPost.user_id)
        .filter(GroupPost.group_id == group.id)
        .group_by(GroupPost.id, GroupPost.user_id, User.nickname, GroupPost.content)
        .order_by(func.count(GroupPostReport.id).desc(), func.max(GroupPostReport.created_at).desc())
        .all()
    )
    post_reason_rows = (
        db.query(
            GroupPostReport.post_id,
            GroupPostReport.reason_code,
        )
        .join(GroupPost, GroupPostReport.post_id == GroupPost.id)
        .filter(GroupPost.group_id == group.id)
        .all()
    )
    post_reason_map: dict[int, set[str]] = {}
    for row in post_reason_rows:
        post_reason_map.setdefault(int(row.post_id), set()).add(row.reason_code)

    comment_rows = (
        db.query(
            GroupComment.id,
            GroupComment.user_id,
            User.nickname,
            GroupComment.content,
            func.count(GroupCommentReport.id).label("report_count"),
            func.max(GroupCommentReport.created_at).label("last_reported_at"),
        )
        .join(GroupCommentReport, GroupCommentReport.comment_id == GroupComment.id)
        .join(User, User.id == GroupComment.user_id)
        .join(GroupPost, GroupPost.id == GroupComment.post_id)
        .filter(GroupPost.group_id == group.id)
        .group_by(GroupComment.id, GroupComment.user_id, User.nickname, GroupComment.content)
        .order_by(func.count(GroupCommentReport.id).desc(), func.max(GroupCommentReport.created_at).desc())
        .all()
    )
    comment_reason_rows = (
        db.query(
            GroupCommentReport.comment_id,
            GroupCommentReport.reason_code,
        )
        .join(GroupComment, GroupCommentReport.comment_id == GroupComment.id)
        .join(GroupPost, GroupPost.id == GroupComment.post_id)
        .filter(GroupPost.group_id == group.id)
        .all()
    )
    comment_reason_map: dict[int, set[str]] = {}
    for row in comment_reason_rows:
        comment_reason_map.setdefault(int(row.comment_id), set()).add(row.reason_code)

    return GroupReportInboxResponse(
        posts=[
            GroupReportTargetItem(
                targetId=row.id,
                targetType="POST",
                authorId=row.user_id,
                authorName=row.nickname,
                content=row.content,
                reportCount=int(row.report_count or 0),
                lastReportedAt=row.last_reported_at,
                reasonCodes=sorted(post_reason_map.get(int(row.id), set())),
            )
            for row in post_rows
        ],
        comments=[
            GroupReportTargetItem(
                targetId=row.id,
                targetType="COMMENT",
                authorId=row.user_id,
                authorName=row.nickname,
                content=row.content,
                reportCount=int(row.report_count or 0),
                lastReportedAt=row.last_reported_at,
                reasonCodes=sorted(comment_reason_map.get(int(row.id), set())),
            )
            for row in comment_rows
        ],
    )


@router.delete("/{groupId}/members/{memberId}", summary="그룹원 강퇴")
def remove_group_member(
    groupId: str,
    memberId: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(Group).filter(Group.group_id == groupId).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if group.leader_user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only leader can remove members")
    if memberId == group.leader_user_id:
        raise HTTPException(status_code=400, detail="Leader cannot be removed")

    member = (
        db.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == memberId)
        .first()
    )
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    db.delete(member)
    db.commit()
    return {"ok": True}
