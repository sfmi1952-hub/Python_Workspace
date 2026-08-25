# -*- coding: utf-8 -*-
"""전역 설정값. 경로/정중함(rate-limit)/타임아웃/회사 레지스트리."""
from pathlib import Path
from datetime import date

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "downloads"
DB_PATH = BASE_DIR / "index.sqlite"
LOG_DIR = BASE_DIR / "logs"

# --- 정중함(politeness) / 안정성 ---
REQUEST_DELAY_SEC = 1.0          # 같은 호스트 PDF 다운로드 간 최소 간격(초)
NAV_TIMEOUT_MS = 45000           # 페이지 이동 타임아웃
SEARCH_WAIT_MS = 2800            # 검색/AJAX 렌더 대기
MAX_DOWNLOAD_MB = 200            # 비정상 대용량 방어

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# --- "판매시기별 전체 개정본" 수집을 위한 넓은 판매기간 범위 ---
SALE_PERIOD_FROM = "20100101"
def sale_period_to() -> str:
    return date.today().strftime("%Y%m%d")

# --- 회사 레지스트리 (key -> 메타/어댑터 클래스명) ---
COMPANIES = {
    "samsung_fire":   {"name": "삼성화재",   "category": "손해보험", "module": "adapters.samsung_fire",   "cls": "SamsungFireAdapter"},
    "samsung_life":   {"name": "삼성생명",   "category": "생명보험", "module": "adapters.samsung_life",   "cls": "SamsungLifeAdapter"},
    "meritz_fire":    {"name": "메리츠화재", "category": "손해보험", "module": "adapters.meritz_fire",    "cls": "MeritzFireAdapter"},
    "hyundai_marine": {"name": "현대해상",   "category": "손해보험", "module": "adapters.hyundai_marine", "cls": "HyundaiMarineAdapter"},
    "db_insurance":   {"name": "DB손해보험", "category": "손해보험", "module": "adapters.db_insurance",   "cls": "DBInsuranceAdapter"},
    "kb_insurance":   {"name": "KB손해보험", "category": "손해보험", "module": "adapters.kb_insurance",   "cls": "KBInsuranceAdapter"},
}

DEFAULT_ORDER = ["samsung_life", "db_insurance", "samsung_fire", "kb_insurance", "hyundai_marine", "meritz_fire"]
