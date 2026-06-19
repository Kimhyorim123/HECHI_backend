import os
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import boto3
from botocore.client import Config as BotoConfig
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from app.core.config import get_settings

router = APIRouter(prefix="/uploads", tags=["uploads"])

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
ALLOWED_DIRECTORIES = {"uploads", "group-images", "profile-images"}
MAX_SIZE_BYTES = 5 * 1024 * 1024
UPLOAD_DIR = os.environ.get("UPLOAD_DIR", os.path.abspath(os.path.join(os.getcwd(), "uploads")))
STATIC_BASE_URL = os.environ.get("STATIC_BASE_URL", "/static/uploads/")


def _ext_ok(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(status_code=400, detail="Only jpg, jpeg, png, webp allowed")
    return ext


def _external_base_url(request: Request) -> str:
    forwarded_proto = request.headers.get("x-forwarded-proto")
    forwarded_host = request.headers.get("x-forwarded-host")
    if forwarded_proto and forwarded_host:
        return f"{forwarded_proto}://{forwarded_host}".rstrip("/")
    if forwarded_proto:
        return f"{forwarded_proto}://{request.headers.get('host', '')}".rstrip("/")
    return str(request.base_url).rstrip("/")


def _public_file_url(request: Request, key: str) -> str:
    if STATIC_BASE_URL.startswith("http://") or STATIC_BASE_URL.startswith("https://"):
        return f"{STATIC_BASE_URL.rstrip('/')}/{key}"
    return _external_base_url(request) + f"{STATIC_BASE_URL}{key}"


def _local_upload_url(request: Request) -> str:
    return _external_base_url(request) + "/uploads/local"


def _safe_local_key(key: str) -> str:
    normalized = key.strip().lstrip("/")
    if not normalized:
        raise HTTPException(status_code=400, detail="Missing key")
    path = Path(normalized)
    if path.is_absolute() or ".." in path.parts:
        raise HTTPException(status_code=400, detail="Invalid key")
    return normalized


def _resolve_directory(directory: str) -> str:
    normalized = (directory or "uploads").strip().strip("/")
    if normalized not in ALLOWED_DIRECTORIES:
        raise HTTPException(status_code=400, detail="Unsupported upload directory")
    return normalized


def _local_presign_payload(request: Request, filename: str, content_type: Optional[str], acl: str, directory: str) -> Dict[str, Any]:
    ext = _ext_ok(filename)
    key = f"{directory}/{uuid.uuid4().hex}{ext}"
    public_url = _public_file_url(request, key)
    fields: Dict[str, str] = {"key": key, "acl": acl}
    if content_type:
        fields["Content-Type"] = content_type
    return {
        "url": _local_upload_url(request),
        "fields": fields,
        "key": key,
        "fileUrl": public_url,
        "publicUrl": public_url,
        "uploadMethod": "local",
    }


@router.post("/presign", summary="S3 presigned POST 생성")
def create_presigned_post(
    request: Request,
    filename: str = Query(..., description="원본 파일명(확장자 포함)"),
    contentType: Optional[str] = Query(None, description="MIME 타입"),
    acl: str = Query("public-read", description="S3 ACL"),
    directory: str = Query("uploads", description="업로드 폴더: uploads | group-images | profile-images"),
) -> Dict[str, Any]:
    settings = get_settings()
    resolved_directory = _resolve_directory(directory)
    if not (settings.aws_access_key_id and settings.aws_secret_access_key and settings.s3_bucket and settings.aws_region):
        return _local_presign_payload(request, filename, contentType, acl, resolved_directory)

    ext = _ext_ok(filename)
    key = f"{resolved_directory}/{uuid.uuid4().hex}{ext}"
    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
        config=BotoConfig(signature_version="s3v4"),
    )

    fields = {"acl": acl}
    conditions = [["content-length-range", 1, MAX_SIZE_BYTES]]
    if contentType:
        fields["Content-Type"] = contentType
        conditions.append({"Content-Type": contentType})

    post = s3.generate_presigned_post(
        Bucket=settings.s3_bucket,
        Key=key,
        Fields=fields,
        Conditions=conditions,
        ExpiresIn=300,
    )

    public_base = settings.s3_public_base_url.rstrip("/") if settings.s3_public_base_url else None
    public_url = (
        f"{public_base}/{key}"
        if public_base
        else f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"
    )

    return {
        "url": post["url"],
        "fields": post["fields"],
        "key": key,
        "fileUrl": public_url,
        "publicUrl": public_url,
        "uploadMethod": "s3",
    }


@router.post("/local", summary="로컬 업로드 폴백")
async def upload_local_file(
    request: Request,
    key: str = Form(...),
    acl: str = Form("public-read"),
    content_type: Optional[str] = Form(None, alias="Content-Type"),
    file: UploadFile = File(...),
):
    del acl
    del content_type
    safe_key = _safe_local_key(key)
    _ext_ok(file.filename or safe_key)

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    dest_path = Path(UPLOAD_DIR) / safe_key
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    size = 0
    try:
        with dest_path.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_SIZE_BYTES:
                    raise HTTPException(status_code=413, detail="File too large")
                out.write(chunk)
    except Exception:
        try:
            dest_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise

    public_url = _public_file_url(request, safe_key)
    return JSONResponse(
        status_code=201,
        content={"ok": True, "key": safe_key, "fileUrl": public_url, "publicUrl": public_url},
    )
