"""
DB 세션 관리 — SQLite(개발) / PostgreSQL(운영)
"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from config.settings import settings
from .models import Base

engine = create_engine(
    settings.database_url,
    echo=False,
    # SQLite 전용: check_same_thread
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """테이블 생성 (개발 환경용)"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI Dependency — DB 세션 주입"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
