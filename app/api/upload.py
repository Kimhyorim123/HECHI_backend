from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, Any
import boto3
from botocore.client import Config as BotoConfig

from app.core.auth import get_current_user
from app.core.config import get_settings

router = APIRouter(prefix="/uploads", tags=["uploads"]) 

@router.post("/presign", summary="S3 presigned POST 생성")
def create_presigned_post(
    filename: str = Query(..., description="원본 파일명(확장자 포함)"),
    contentType: Optional[str] = Query(None, description="MIME 타입"),
    acl: str = Query("public-read", description="S3 ACL"),
    ) -> Dict[str, Any]:
    settings = get_settings()
    if not (settings.aws_access_key_id and settings.aws_secret_access_key and settings.s3_bucket and settings.aws_region):
        raise HTTPException(status_code=501, detail="S3 not configured")

    s3 = boto3.client(
        "s3",
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        region_name=settings.aws_region,
        config=BotoConfig(signature_version="s3v4"),
    )

    import uuid, os
    ext = os.path.splitext(filename)[1].lower()
    key = f"uploads/{uuid.uuid4().hex}{ext}"

    fields = {"acl": acl}
    conditions = [["content-length-range", 1, 5 * 1024 * 1024]]  # 1..5MB
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
    file_url = f"{public_base}/{key}" if public_base else f"https://{settings.s3_bucket}.s3.{settings.aws_region}.amazonaws.com/{key}"

    return {"url": post["url"], "fields": post["fields"], "key": key, "fileUrl": file_url}
