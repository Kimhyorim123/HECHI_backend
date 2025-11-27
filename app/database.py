from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from .core.config import get_settings

# 동기 엔진 사용 (초기 단순화). 후에 async 엔진(aiomysql)로 전환 가능.
settings = get_settings()
DATABASE_URL = settings.database_url

engine = create_engine(
	DATABASE_URL,
	echo=(settings.environment == "local"),
	future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Generator[Session, None, None]:
	db = SessionLocal()
	try:
		yield db
	finally:
		db.close()

