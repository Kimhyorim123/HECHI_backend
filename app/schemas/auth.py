from pydantic import BaseModel, EmailStr
from typing import Optional

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    # 자동로그인(영구 쿠키) 여부. true이면 refresh 토큰을 HttpOnly 쿠키로 설정
    remember_me: bool = False

class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class RefreshRequest(BaseModel):
    refresh_token: str


class EmailCheckResponse(BaseModel):
    exists: bool
    available: bool
