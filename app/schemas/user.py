from pydantic import AliasChoices, BaseModel, ConfigDict, EmailStr, Field
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr
    login_id: str
    name: str
    nickname: str
    description: Optional[str] = None

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: int
    profileImageUrl: Optional[str] = Field(default=None, validation_alias=AliasChoices('profileImageUrl', 'profile_image_url'))
    created_at: Optional[datetime] = None
    taste_analyzed: bool | None = None
    email_verified: bool | None = None
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserUpdate(BaseModel):
    name: Optional[str] = None
    nickname: Optional[str] = None
    description: Optional[str] = None
