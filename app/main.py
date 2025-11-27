# app/main.py (헬스체크용)
from fastapi import FastAPI
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException
from sqlalchemy import text
from fastapi.middleware.cors import CORSMiddleware

from .core.config import get_settings
from .api import auth as auth_router
from .api import reading as reading_router
from .api import note as note_router
from .api import highlight as highlight_router
from .api import bookmark as bookmark_router
from .api import review as review_router
from .api import book as book_router
from .api import support as support_router
from .api import reading_status as reading_status_router
from .api import taste as taste_router
from .api import password_reset as password_reset_router
from .api import analytics as analytics_router
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
    allow_headers=["*"],
)

app.include_router(auth_router.router)
app.include_router(reading_router.router)
app.include_router(note_router.router)
app.include_router(highlight_router.router)
app.include_router(bookmark_router.router)
app.include_router(review_router.router)
app.include_router(book_router.router)
app.include_router(support_router.router)
app.include_router(reading_status_router.router)
app.include_router(taste_router.router)
app.include_router(password_reset_router.router)
app.include_router(analytics_router.router)

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
