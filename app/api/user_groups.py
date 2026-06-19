from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..core.auth import get_current_user
from ..database import get_db
from ..models import Group, GroupMember, GroupMonthlyBook, Book, User
from ..schemas.group import GroupBoardItem, MyGroupItem, MyGroupListResponse


router = APIRouter(prefix="/users", tags=["groups"])


def _group_boards(db: Session, group: Group) -> list[GroupBoardItem]:
    boards = [
        GroupBoardItem(boardKey="ANNOUNCEMENT", boardType="ANNOUNCEMENT", label="공지사항"),
        GroupBoardItem(boardKey="FREE", boardType="FREE", label="자유 게시판"),
    ]
    mission_rows = (
        db.query(GroupMonthlyBook, Book)
        .join(Book, GroupMonthlyBook.book_id == Book.id)
        .filter(GroupMonthlyBook.group_id == group.id)
        .order_by(GroupMonthlyBook.month.desc(), GroupMonthlyBook.book_id.desc())
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


@router.get("/me/groups", response_model=MyGroupListResponse, summary="내 그룹 목록")
def my_groups(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = (
        db.query(Group)
        .join(GroupMember, GroupMember.group_id == Group.id)
        .filter(GroupMember.user_id == current_user.id)
        .all()
    )
    items = [
        MyGroupItem(
            groupId=g.group_id,
            name=g.name,
            backgroundImage=g.background_image,
            boards=_group_boards(db, g),
        )
        for g in rows
    ]
    return MyGroupListResponse(groups=items)
