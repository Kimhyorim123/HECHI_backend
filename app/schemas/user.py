from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    email: EmailStr
    name: str
    nickname: str

class UserCreate(UserBase):
    password: str

class UserRead(UserBase):
    id: int
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)
