"""
InsuranceExtractionSystem 통합 실행 스크립트
Usage: python run.py
"""
import uvicorn
from config.settings import settings

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
