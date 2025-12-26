from fastapi import APIRouter, Depends, HTTPException, status, Query, Response, Request, Body
from fastapi.responses import JSONResponse
from pydantic import EmailStr
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import User
from ..schemas.user import UserCreate, UserRead, UserUpdate
from ..schemas.auth import LoginRequest, TokenPair, RefreshRequest, EmailCheckResponse
from ..core.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from ..core.auth import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserRead, status_code=status.HTTP_201_CREATED)
def register(data: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user = User(
        email=data.email,
        password_hash=hash_password(data.password),
        name=data.name,
        nickname=data.nickname,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

@router.post("/login", response_model=TokenPair)
def login(data: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == data.email).first()
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    access = create_access_token(user.id)
    refresh = create_refresh_token(user.id)
    # remember_me가 true인 경우, refresh 토큰을 HttpOnly 쿠키로 설정하여 자동로그인 지원
    # 응답을 직접 구성하여 쿠키를 확실히 설정
    resp_body = TokenPair(access_token=access, refresh_token=refresh).model_dump()
    resp = JSONResponse(content=resp_body)
    if data.remember_me:
        from ..core.config import get_settings
        settings = get_settings()
        max_age = settings.refresh_token_exp_days * 24 * 60 * 60
        secure_flag = settings.environment != "local"
        resp.set_cookie(
            key="refresh_token",
            value=refresh,
            httponly=True,
            secure=secure_flag,
            samesite="lax",
            max_age=max_age,
            path="/",
        )
    return resp

@router.post("/refresh", response_model=TokenPair)
def refresh_token(request: Request, data: RefreshRequest | None = Body(default=None)):
    # 본문에 refresh_token이 없으면 쿠키에서 읽어 자동로그인 지원
    token = (data.refresh_token if data else None) or request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing refresh token")
    payload = decode_token(token, expected_type="refresh")
    user_id = int(payload["sub"])  # type: ignore
    return TokenPair(access_token=create_access_token(user_id), refresh_token=create_refresh_token(user_id))

@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="로그아웃 (refresh 쿠키 삭제)")
def logout(_: Response):
    resp = JSONResponse(content=None, status_code=status.HTTP_204_NO_CONTENT)
    # 표준 삭제
    resp.delete_cookie("refresh_token", path="/")
    # 일부 클라이언트/프록시 환경에서 delete_cookie가 누락될 수 있어 수동 헤더도 추가
    from ..core.config import get_settings
    settings = get_settings()
    secure_flag = settings.environment != "local"
    cookie = "refresh_token=; Max-Age=0; Path=/; SameSite=lax; HttpOnly"
    if secure_flag:
        cookie += "; Secure"
    resp.headers.append("Set-Cookie", cookie)
    return resp

@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserRead, summary="내 프로필 수정")
def update_me(
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    changed = False
    if payload.name is not None and payload.name.strip() != "" and payload.name != current_user.name:
        current_user.name = payload.name.strip()
        changed = True
    if payload.nickname is not None and payload.nickname.strip() != "" and payload.nickname != current_user.nickname:
        current_user.nickname = payload.nickname.strip()
        changed = True
    if payload.description is not None and payload.description != current_user.description:
        current_user.description = payload.description
        changed = True
    if changed:
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    return current_user


@router.get("/email-check", response_model=EmailCheckResponse, summary="이메일 존재/가용성 확인")
def email_check(
    email: EmailStr = Query(..., description="확인할 이메일 주소"),
    db: Session = Depends(get_db),
):
    # 존재 여부 확인
    exists = db.query(User.id).filter(User.email == email).first() is not None
    return EmailCheckResponse(exists=exists, available=not exists)
