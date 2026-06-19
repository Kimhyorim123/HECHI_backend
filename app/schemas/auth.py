from pydantic import BaseModel, EmailStr

class LoginRequest(BaseModel):
    login_id: str
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


class LoginIdCheckResponse(BaseModel):
    exists: bool
    available: bool


class VerifyEmailRequest(BaseModel):
    email: EmailStr
    code: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class VerificationStatusResponse(BaseModel):
    ok: bool
    email_verified: bool
    detail: str | None = None
