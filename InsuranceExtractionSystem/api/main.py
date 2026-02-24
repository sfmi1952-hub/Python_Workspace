"""
FastAPI 메인 애플리케이션
통합 진입점 — 모든 라우트 등록, CORS, 미들웨어
"""
import os
import sys
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

# 프로젝트 루트를 Python 경로에 추가
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 생명주기 관리 — 시작 시 DB 초기화"""
    from db.session import init_db
    init_db()
    print("[App] Database initialized")
    yield
    print("[App] Shutting down")


app = FastAPI(
    title="보험약관 정보추출 시스템",
    description="Insurance Policy Information Extraction System — AI 기반 약관 정보 자동 추출·검증·적재",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우트 등록 ──────────────────────────────────────────────
from api.routes.extraction import router as extraction_router
from api.routes.review import router as review_router
from api.routes.pipeline import router as pipeline_router
from api.routes.admin import router as admin_router

app.include_router(extraction_router, prefix="/api")
app.include_router(review_router, prefix="/api")
app.include_router(pipeline_router, prefix="/api")
app.include_router(admin_router, prefix="/api")


# ── 헬스체크 ─────────────────────────────────────────────────
@app.get("/")
def root():
    return {"service": "InsuranceExtractionSystem", "version": "1.0.0", "status": "running"}


@app.get("/health")
def health():
    return {"status": "ok"}


# ── 정적 파일 (React 빌드) ────────────────────────────────────
web_ui_dist = PROJECT_ROOT / "web_ui" / "dist"
if web_ui_dist.exists():
    app.mount("/", StaticFiles(directory=str(web_ui_dist), html=True), name="static")
