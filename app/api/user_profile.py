from __future__ import annotations

import os
import uuid
from pathlib import Path

import boto3
from botocore.client import Config as BotoConfig
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.config import get_settings
from app.database import get_db
from app.models import User

router = APIRouter(tags=["users"])

class ProfileImageUrlUpdateRequest(BaseModel):
    profileImageUrl: str | None = None


class ProfileImageUrlResponse(BaseModel):
    profileImageUrl: str | None = None


ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_SIZE_BYTES = 5 * 1024 * 1024
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.abspath(os.path.join(os.getcwd(), "uploads")))
STATIC_BASE_URL = os.environ.get("STATIC_BASE_URL", "/static/uploads/")
PROFILE_PREFIX = "profile-images"


def _ext_ok(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, jpeg, png, webp allowed")
    return ext


def _public_file_url(request: Request, key: str) -> str:
    if STATIC_BASE_URL.startswith("http://") or STATIC_BASE_URL.startswith("https://"):
        return f"{STATIC_BASE_URL.rstrip('/')}/{key}"
    return str(request.base_url).rstrip("/") + f"{STATIC_BASE_URL}{key}"


async def _save_local_profile_image(request: Request, file: UploadFile) -> str:
    filename = file.filename or "profile-image"
    ext = _ext_ok(filename)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    key = f"{PROFILE_PREFIX}/{uuid.uuid4().hex}{ext}"
    dest_path = Path(UPLOAD_DIR) / key
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with dest_path.open("wb") as out:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_SIZE_BYTES:
                try:
                    dest_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise HTTPException(status_code=413, detail="File too large")
            out.write(chunk)
    return _public_file_url(request, key)


async def _upload_profile_image(request: Request, file: UploadFile) -> str:
    settings = get_settings()
    filename = file.filename or "profile-image"
    ext = _ext_ok(filename)
    if not (settings.aws_access_key_id and settings.aws_secret_access_key and settings.s3_bucket and settings.aws_region):
        return await _save_local_profile_image(request, file)

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="File too large")

    key = f"{PROFILE_PREFIX}/{uuid.uuid4().hex}{ext}"
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
        config=BotoConfig(signature_version="s3v4"),
    )
    extra_args = {"ContentType": file.content_type or "application/octet-stream", "ACL": "public-read"}
    s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=content, **extra_args)
    public_base = settings.s3_public_base_url.rstrip("/") if settings.s3_public_base_url else None
    return f"{public_base}/{key}" if public_base else f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"


@router.post("/users/me/profile-image", summary="프로필 이미지 업로드")
async def upload_profile_image(
    request: Request,
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile_image_url = await _upload_profile_image(request, image)
    current_user.profile_image_url = profile_image_url
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return {"profileImageUrl": profile_image_url}


@router.patch("/users/me/profile-image-url", response_model=ProfileImageUrlResponse, summary="프로필 이미지 URL 저장")
def update_profile_image_url(
    data: ProfileImageUrlUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    profile_image_url = (data.profileImageUrl or "").strip() or None
    if profile_image_url is not None and not (
        profile_image_url.startswith("http://") or profile_image_url.startswith("https://")
    ):
        raise HTTPException(status_code=400, detail="profileImageUrl must be an absolute http(s) URL")

    current_user.profile_image_url = profile_image_url
    db.add(current_user)
    db.commit()
    db.refresh(current_user)
    return ProfileImageUrlResponse(profileImageUrl=current_user.profile_image_url)
