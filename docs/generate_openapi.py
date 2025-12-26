"""Generate pretty OpenAPI spec (v1.1.0) with rich success & error examples.

Adds:
 - Schema-aware success examples (real field samples instead of {"ok": true})
 - 422 validation error example
 - Generic 400 & 404 ErrorResponse examples auto-injected when absent
 - Endpoint summary markdown (docs/endpoint-summary.md) including 200/201, 400, 404, 422 examples

Usage:
    python docs/generate_openapi.py
"""
from pathlib import Path
import json
from typing import Any, Dict, Optional
import sys

# Ensure project root on sys.path when executed from subfolder
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # ensures routers registered

SPEC_VERSION = "1.1.0"

# Schema-level success examples. Key = schema name in components.
SCHEMA_SUCCESS_EXAMPLES: Dict[str, Dict[str, Any]] = {
    "UserRead": {
        "id": 1,
        "email": "user@example.com",
        "name": "홍길동",
        "nickname": "gildong",
        "created_at": "2025-11-26T12:00:00Z",
    },
    "TokenPair": {
        "access_token": "<access.jwt>",
        "refresh_token": "<refresh.jwt>",
        "token_type": "bearer",
    },
    "BookResponse": {
        "id": 10,
        "isbn": "9781234567890",
        "title": "예시 책 제목",
        "publisher": "예시출판사",
        "published_date": "2025-01-01",
        "language": "ko",
        "category": "Fiction",
        "total_pages": 320,
    },
    "BookDetailResponse": {
        "id": 10,
        "isbn": "9781234567890",
        "title": "예시 책 제목",
        "publisher": "예시출판사",
        "published_date": "2025-01-01",
        "language": "ko",
        "category": "Fiction",
        "total_pages": 320,
        "authors": ["작가 A", "작가 B"],
        "average_rating": 4.6,
        "review_count": 12,
    },
    "ReviewResponse": {
        "id": 5,
        "user_book_id": 3,
        "user_id": 1,
        "book_id": 10,
        "rating": 5,
        "content": "엄청 재미있었어요",
        "like_count": 0,
        "is_spoiler": False,
        "created_date": "2025-11-26",
        "is_my_review": True,
        "is_liked": True,
    },
    "CommentResponse": {
        "id": 1,
        "review_id": 5,
        "user_id": 1,
        "content": "동의합니다!",
        "created_at": "2025-11-26T12:34:56Z",
    },
    "BookRatingSummary": {
        "book_id": 10,
        "average_rating": 4.25,
        "review_count": 20,
    },
    "BookmarkResponse": {
        "id": 9,
        "user_book_id": 3,
        "page": 14,
        "memo": "다시 볼 부분",
        "created_date": "2025-11-26",
    },
    "HighlightResponse": {
        "id": 8,
        "user_book_id": 3,
        "page": 13,
        "sentence": "기억하고 싶은 문장",
        "is_public": True,
        "memo": "문장에 대한 개인 메모",
        "created_date": "2025-11-26",
    },
    "NoteResponse": {
        "id": 7,
        "user_book_id": 3,
        "content": "중요한 부분",
        "created_date": "2025-11-26",
    },
    "CalendarMonthResponse": {
        "year": 2025,
        "month": 11,
        "total_read_count": 17,
        "top_genre": "소설",
        "days": [
            {"date": "2025-11-04", "items": [{"book_id": 1483, "title": "급류", "thumbnail": "https://..."}]},
            {"date": "2025-11-07", "items": [{"book_id": 1497, "title": "프로젝트 헤일메리", "thumbnail": "https://..."}]}
        ],
    },
    "ReadingEventResponse": {
        "id": 1,
        "event_type": "PAGE_TURN",
        "page": 15,
        "occurred_at": "2025-11-26T12:15:00Z",
    },
    "ReadingSessionResponse": {
        "id": 2,
        "user_id": 1,
        "book_id": 10,
        "start_time": "2025-11-26T12:00:00Z",
        "end_time": "2025-11-26T12:30:00Z",
        "start_page": 1,
        "end_page": 30,
        "total_seconds": 1800,
        "events": [
            {
                "id": 1,
                "event_type": "PAGE_TURN",
                "page": 15,
                "occurred_at": "2025-11-26T12:15:00Z",
            }
        ],
    },
    "FAQResponse": {
        "id": 1,
        "question": "어떻게 사용하나요?",
        "answer": "이렇게 사용합니다.",
        "is_pinned": True,
    },
    "TicketResponse": {
        "id": 4,
        "user_id": 1,
        "title": "문의 제목",
        "description": "문의 상세 내용",
        "status": "open",
        "created_at": "2025-11-26T12:00:00Z",
    },
}

GENERIC_SUCCESS = {"ok": True}
VALIDATION_ERROR_EXAMPLE = {
    "detail": [
        {"loc": ["body", "field"], "msg": "Invalid value", "type": "value_error"}
    ]
}
BAD_REQUEST_EXAMPLE = {"detail": "Bad Request"}
NOT_FOUND_EXAMPLE = {"detail": "Not Found"}

# Build base spec from FastAPI
spec: Dict[str, Any] = app.openapi()
# Bump version
spec["info"]["version"] = SPEC_VERSION

# Helper to extract schema ref name
def _extract_ref_schema(media_obj: Dict[str, Any]) -> Optional[str]:
    schema = media_obj.get("schema")
    if isinstance(schema, dict) and "$ref" in schema:
        ref: str = schema["$ref"]
        if ref.startswith("#/components/schemas/"):
            return ref.split("/")[-1]
    return None

# Inject examples
for path, methods in spec.get("paths", {}).items():
    for method_name, op in methods.items():
        if not isinstance(op, dict):
            continue
        # Inject request body examples for specific endpoints
        if method_name.lower() == "post" and path == "/notes/":
            rb = op.get("requestBody") or {}
            content = rb.get("content") or {}
            json_ct = content.get("application/json") or {}
            # notes는 페이지 없이 생성 예시를 제공
            json_ct["example"] = {"book_id": 10, "content": "중요한 부분"}
            content["application/json"] = json_ct
            rb["content"] = content
            op["requestBody"] = rb
        if method_name.lower() == "put" and path.startswith("/bookmarks/"):
            rb = op.get("requestBody") or {}
            content = rb.get("content") or {}
            json_ct = content.get("application/json") or {}
            json_ct["example"] = {"page": 120, "memo": "수정된 메모"}
            content["application/json"] = json_ct
            rb["content"] = content
            op["requestBody"] = rb
        if method_name.lower() == "put" and path.startswith("/highlights/"):
            rb = op.get("requestBody") or {}
            content = rb.get("content") or {}
            json_ct = content.get("application/json") or {}
            # 하이라이트 수정: 메모 갱신 예시
            json_ct["example"] = {"page": 45, "memo": "수정된 하이라이트 메모"}
            content["application/json"] = json_ct
            rb["content"] = content
            op["requestBody"] = rb
        responses = op.get("responses", {})
        # Inject example for calendar-month
        if method_name.lower() == "get" and path == "/analytics/calendar-month":
            ok = responses.get("200") or {}
            content = ok.get("content") or {}
            json_ct = content.get("application/json") or {}
            json_ct["example"] = SCHEMA_SUCCESS_EXAMPLES.get("CalendarMonthResponse")
            content["application/json"] = json_ct
            ok["content"] = content
            responses["200"] = ok
            op["responses"] = responses
        # Ensure common error responses present (skip if already defined)
        def ensure_error(code: str, example: Dict[str, Any], description: str):
            if code not in responses:
                responses[code] = {
                    "description": description,
                    "content": {
                        "application/json": {
                            "schema": {"$ref": "#/components/schemas/ErrorResponse"},
                            "example": example,
                        }
                    },
                }

        ensure_error("400", BAD_REQUEST_EXAMPLE, "Bad Request")
        ensure_error("404", NOT_FOUND_EXAMPLE, "Not Found")

        for status_code, resp in responses.items():
            if not isinstance(resp, dict):
                continue
            content = resp.get("content")
            if not content:
                continue
            # Success responses (2xx & 201 etc)
            if status_code.startswith("2"):
                for media_type, media_obj in content.items():
                    if isinstance(media_obj, dict):
                        ref_name = _extract_ref_schema(media_obj)
                        example = SCHEMA_SUCCESS_EXAMPLES.get(ref_name, GENERIC_SUCCESS)
                        media_obj.setdefault("example", example)
            # Validation error (422)
            if status_code == "422":
                for media_type, media_obj in content.items():
                    if isinstance(media_obj, dict):
                        media_obj.setdefault("example", VALIDATION_ERROR_EXAMPLE)

# Write file
out_path = Path("docs/openapi-v1.1.json")
out_path.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {out_path} (paths={len(spec.get('paths', {}))})")

# Build endpoint summary markdown
summary_lines = [
    "| Method | Path | Auth | Success Code | Success Example | 400 Example | 404 Example | 422 Example |",
    "|--------|------|------|--------------|-----------------|-------------|-------------|-------------|",
]
for path, methods in spec.get("paths", {}).items():
    for method_name, op in methods.items():
        if method_name.lower() not in {"get", "post", "put", "delete", "patch"}:
            continue
        auth = "Yes" if op.get("security") else "No"
        responses = op.get("responses", {})
        success_code = next((c for c in responses.keys() if c.startswith("2")), "")
        def extract_example(code: str) -> str:
            r = responses.get(code)
            if not r:
                return ""
            content = r.get("content", {})
            mt = next(iter(content.keys()), None)
            if not mt:
                return ""
            ex = content[mt].get("example")
            if isinstance(ex, dict):
                return json.dumps(ex, ensure_ascii=False)
            return str(ex) if ex is not None else ""
        success_example = extract_example(success_code)
        ex400 = extract_example("400")
        ex404 = extract_example("404")
        ex422 = extract_example("422")
        summary_lines.append(
            f"| {method_name.upper()} | {path} | {auth} | {success_code} | {success_example} | {ex400} | {ex404} | {ex422} |"
        )

summary_md = "# Endpoint Summary (v1.1.0)\n\n" + "\n".join(summary_lines) + "\n"
Path("docs/endpoint-summary.md").write_text(summary_md, encoding="utf-8")
print("Wrote docs/endpoint-summary.md (rows=", len(summary_lines) - 2, ")")
