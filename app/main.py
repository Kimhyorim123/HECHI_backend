# app/main.py (헬스체크용)
from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
import os

from .core.config import get_settings
from .api import auth as auth_router
# from .api import reading as reading_router  # corrupted in workspace, use fixed version
from .api import reading_fixed as reading_router
from .api import note as note_router
from .api import highlight as highlight_router
from .api import bookmark as bookmark_router
from .api import review as review_router
from .api import book as book_router
from .api import support as support_router
from .api import customer_service as customer_service_router
from .api import reading_status as reading_status_router
from .api import taste as taste_router
from .api import password_reset as password_reset_router
from .api import analytics as analytics_router
from .api import search as search_router
from .api import library as library_router
from .api import recommend as recommend_router
from .api import recommend_for_you as recommend_for_you_router
from .api import wishlist as wishlist_router
from .api import upload as upload_router
from .api import notifications as notifications_router
from .api import library as library_router
from .schemas.error import ErrorResponse
from .database import engine

settings = get_settings()

app = FastAPI(title="BookStopper API", version="0.1.0")

origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin"],
)

app.include_router(auth_router.router)
app.include_router(reading_router.router)
app.include_router(note_router.router)
app.include_router(highlight_router.router)
app.include_router(bookmark_router.router)
app.include_router(review_router.router)
app.include_router(book_router.router)
app.include_router(support_router.router)
app.include_router(customer_service_router.router)
app.include_router(reading_status_router.router)
app.include_router(taste_router.router)
app.include_router(password_reset_router.router)
app.include_router(analytics_router.router)
app.include_router(search_router.router)
app.include_router(library_router.router)
app.include_router(recommend_router.router)
app.include_router(recommend_for_you_router.router)
app.include_router(wishlist_router.router)
app.include_router(upload_router.router)
app.include_router(notifications_router.router)

# Serve uploaded files (customer-service attachments)
_upload_dir = os.environ.get("UPLOAD_DIR", os.path.abspath(os.path.join(os.getcwd(), "uploads")))
os.makedirs(_upload_dir, exist_ok=True)
app.mount("/static/uploads", StaticFiles(directory=_upload_dir), name="uploads")

@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok", "environment": settings.environment}


@app.get("/health/db", tags=["meta"])
def health_db():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "reachable"}
    except Exception as e:
        return {"status": "error", "database": "unreachable", "detail": str(e)}


# Global error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content=ErrorResponse(detail=str(exc.detail)).model_dump())


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content=ErrorResponse(detail="Validation Error").model_dump())


# Customize OpenAPI to inject requestBody examples for specific endpoints
def _custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    # Build base OpenAPI schema without recursion
    spec = get_openapi(
        title=app.title,
        version=app.version,
        routes=app.routes,
    )
    # Inject request examples
    paths = spec.get("paths", {})
    for path, methods in paths.items():
        for method_name, op in methods.items():
            if not isinstance(op, dict):
                continue
            # customer-service examples
            if method_name.lower() == "get" and path == "/customer-service/faqs":
                responses = op.get("responses") or {}
                resp_200 = responses.get("200") or {}
                content = resp_200.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {
                    "faqs": [
                        {"faqId": 1, "question": "책 등록 방법", "answer": "등록 버튼 클릭 후 입력"},
                        {"faqId": 2, "question": "책 검색 방법", "answer": "검색창에 제목 입력"},
                    ]
                }
                content["application/json"] = json_ct
                resp_200["content"] = content
                responses["200"] = resp_200
                op["responses"] = responses
            if method_name.lower() == "get" and path == "/customer-service/my":
                responses = op.get("responses") or {}
                resp_200 = responses.get("200") or {}
                content = resp_200.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {
                    "inquiries": [
                        {
                            "inquiryId": 123,
                            "userId": 10,
                            "inquiryTitle": "책 등록 방법 문의",
                            "inquiryDescription": "어디서 등록하나요?",
                            "inquiryFileUrl": "https://cdn.example.com/file/12345.png",
                            "status": "waiting",
                            "inquiryAnswer": None,
                            "inquiryCreatedAt": "2025-11-25T12:34:56Z",
                        }
                    ]
                }
                content["application/json"] = json_ct
                resp_200["content"] = content
                responses["200"] = resp_200
                op["responses"] = responses
            if method_name.lower() == "post" and path == "/customer-service/my":
                responses = op.get("responses") or {}
                resp_201 = responses.get("201") or {}
                content = resp_201.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {
                    "inquiryId": 124,
                    "userId": 10,
                    "inquiryTitle": "앱 버그 신고",
                    "inquiryDescription": "화면이 멈춰요",
                    "inquiryFileUrl": None,
                    "status": "waiting",
                    "inquiryAnswer": None,
                    "inquiryCreatedAt": "2025-12-08T09:00:00Z",
                    "inquiryAnsweredAt": None,
                    "responderUserId": None,
                    "responderName": None,
                }
                content["application/json"] = json_ct
                resp_201["content"] = content
                responses["201"] = resp_201
                op["responses"] = responses
                # multipart request example
                rb = op.get("requestBody") or {}
                rb_content = rb.get("content") or {}
                mp = rb_content.get("multipart/form-data") or {}
                mp["example"] = {
                    "inquiryTitle": "책 등록 방법 문의",
                    "inquiryDescription": "책을 등록하고 싶은데 방법을 모르겠습니다.",
                    "inquiryFile": "(binary)",
                }
                rb_content["multipart/form-data"] = mp
                # also example with URL-only upload
                appjson = rb_content.get("application/json") or {}
                appjson["example"] = {
                    "inquiryTitle": "책 등록 방법 문의",
                    "inquiryDescription": "방법 문의",
                    "inquiryFileUrl": "https://cdn.example.com/uploads/abc.png",
                }
                rb_content["application/json"] = appjson
                rb["content"] = rb_content
                op["requestBody"] = rb
            if method_name.lower() == "get" and path == "/customer-service/admin":
                responses = op.get("responses") or {}
                resp_200 = responses.get("200") or {}
                content = resp_200.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {
                    "inquiries": [
                        {"inquiryId": 124, "userId": 10, "inquiryTitle": "앱 버그 신고", "inquiryDescription": "화면 멈춤", "inquiryFileUrl": None, "status": "answered", "inquiryAnswer": "조치 완료", "inquiryCreatedAt": "2025-12-08T09:00:00Z", "inquiryAnsweredAt": "2025-12-08T10:00:00Z", "responderUserId": 1, "responderName": "Admin"}
                    ]
                }
                content["application/json"] = json_ct
                resp_200["content"] = content
                responses["200"] = resp_200
                op["responses"] = responses
            if method_name.lower() == "get" and path == "/customer-service/admin/search":
                responses = op.get("responses") or {}
                resp_200 = responses.get("200") or {}
                content = resp_200.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {
                    "inquiries": [
                        {"inquiryId": 130, "userId": 12, "inquiryTitle": "검색: 등록", "inquiryDescription": "등록 방법", "inquiryFileUrl": None, "status": "waiting", "inquiryAnswer": None, "inquiryCreatedAt": "2025-12-08T12:00:00Z", "inquiryAnsweredAt": None, "responderUserId": None, "responderName": None}
                    ]
                }
                content["application/json"] = json_ct
                resp_200["content"] = content
                responses["200"] = resp_200
                op["responses"] = responses
            if method_name.lower() == "post" and path == "/uploads/presign":
                responses = op.get("responses") or {}
                resp_200 = responses.get("200") or {}
                content = resp_200.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {
                    "url": "https://s3.amazonaws.com/bucket",
                    "fields": {"key": "uploads/abc123.png", "acl": "public-read", "Policy": "...", "X-Amz-Signature": "..."},
                    "key": "uploads/abc123.png",
                    "fileUrl": "https://cdn.example.com/uploads/abc123.png",
                }
                content["application/json"] = json_ct
                resp_200["content"] = content
                responses["200"] = resp_200
                op["responses"] = responses
            # notes POST example without page
            if method_name.lower() == "post" and path == "/notes/":
                rb = op.get("requestBody") or {}
                content = rb.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {"book_id": 10, "content": "중요한 부분"}
                content["application/json"] = json_ct
                rb["content"] = content
                op["requestBody"] = rb
            # bookmarks PUT example with page+memo
            if method_name.lower() == "put" and path.startswith("/bookmarks/"):
                rb = op.get("requestBody") or {}
                content = rb.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {"page": 120, "memo": "수정된 메모"}
                content["application/json"] = json_ct
                rb["content"] = content
                op["requestBody"] = rb
            # highlights PUT example with page+memo
            if method_name.lower() == "put" and path.startswith("/highlights/"):
                rb = op.get("requestBody") or {}
                content = rb.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {"page": 45, "memo": "수정된 하이라이트 메모"}
                content["application/json"] = json_ct
                rb["content"] = content
                op["requestBody"] = rb
            # analytics calendar-month response example
            if method_name.lower() == "get" and path == "/analytics/calendar-month":
                responses = op.get("responses") or {}
                resp_200 = responses.get("200") or {}
                content = resp_200.get("content") or {}
                json_ct = content.get("application/json") or {}
                json_ct["example"] = {
                    "year": 2024,
                    "month": 11,
                    "total_read_count": 5,
                    "top_genre": "에세이",
                    "days": [
                        {"date": "2024-11-03", "items": [{"book_id": 101, "title": "나의 하루는 4시 30분"}]},
                        {"date": "2024-11-12", "items": [{"book_id": 202, "title": "작은 습관의 힘", "thumbnail": "https://example.com/202.jpg"}]},
                        {"date": "2024-11-20", "items": [{"book_id": 303, "title": "바깥은 여름"}]}
                    ],
                }
                content["application/json"] = json_ct
                resp_200["content"] = content
                responses["200"] = resp_200
                op["responses"] = responses
    # Also set component-level example for CalendarMonthResponse
    components = spec.get("components") or {}
    schemas = components.get("schemas") or {}
    cal_schema = schemas.get("CalendarMonthResponse") or {}
    if isinstance(cal_schema, dict):
        cal_schema["example"] = {
            "year": 2024,
            "month": 11,
            "total_read_count": 5,
            "top_genre": "에세이",
            "days": [
                {"date": "2024-11-03", "items": [{"book_id": 101, "title": "나의 하루는 4시 30분"}]},
                {"date": "2024-11-12", "items": [{"book_id": 202, "title": "작은 습관의 힘", "thumbnail": "https://example.com/202.jpg"}]},
                {"date": "2024-11-20", "items": [{"book_id": 303, "title": "바깥은 여름"}]}
            ],
        }
        schemas["CalendarMonthResponse"] = cal_schema
        components["schemas"] = schemas
        spec["components"] = components
    app.openapi_schema = spec
    return app.openapi_schema
# app.openapi = _custom_openapi
