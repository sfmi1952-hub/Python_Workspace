"""
전역 설정 — 환경변수 기반 (.env 또는 시스템 환경변수)
"""
import os
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# .env 파일 로드 (dotenv 선택 설치)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
STORAGE_DIR = DATA_DIR / "policy_storage"
CACHE_DIR = DATA_DIR / "rag_cache"
RESULT_DIR = DATA_DIR / "result"
EXPORT_DIR = DATA_DIR / "csv_export"
TRANSFER_DIR = DATA_DIR / "transfer"
RECEIVE_DIR = DATA_DIR / "received"


@dataclass
class Settings:
    # ── API Keys ──────────────────────────────────────────────────────────
    gemini_api_key: Optional[str] = field(default_factory=lambda: os.getenv("GEMINI_API_KEY"))
    openai_api_key: Optional[str] = field(default_factory=lambda: os.getenv("OPENAI_API_KEY"))
    anthropic_api_key: Optional[str] = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY"))

    # ── Model Configuration ───────────────────────────────────────────────
    # primary / secondary 모델 (Ensemble 교차검증에 사용)
    primary_provider: str = field(default_factory=lambda: os.getenv("PRIMARY_PROVIDER", "gemini"))
    secondary_provider: str = field(default_factory=lambda: os.getenv("SECONDARY_PROVIDER", "openai"))

    # ── Database ──────────────────────────────────────────────────────────
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", f"sqlite:///{PROJECT_ROOT / 'data' / 'extraction.db'}")
    )
    # 사내망 상품마스터DB (운영 시 설정)
    master_db_url: Optional[str] = field(default_factory=lambda: os.getenv("MASTER_DB_URL"))

    # ── Server ────────────────────────────────────────────────────────────
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    # ── Crawler ───────────────────────────────────────────────────────────
    crawler_target_url: str = field(
        default_factory=lambda: os.getenv("CRAWLER_TARGET_URL", "https://www.samsungfire.com")
    )

    # ── Gateway / SFTP ────────────────────────────────────────────────────
    sftp_host: Optional[str] = field(default_factory=lambda: os.getenv("SFTP_HOST"))
    sftp_port: int = field(default_factory=lambda: int(os.getenv("SFTP_PORT", "22")))
    sftp_user: Optional[str] = field(default_factory=lambda: os.getenv("SFTP_USER"))
    sftp_key_path: Optional[str] = field(default_factory=lambda: os.getenv("SFTP_KEY_PATH"))

    # ── Validation ────────────────────────────────────────────────────────
    auto_confirm_threshold: float = field(
        default_factory=lambda: float(os.getenv("AUTO_CONFIRM_THRESHOLD", "0.95"))
    )

    # ── Paths ─────────────────────────────────────────────────────────────
    project_root: Path = PROJECT_ROOT
    data_dir: Path = DATA_DIR
    storage_dir: Path = STORAGE_DIR
    cache_dir: Path = CACHE_DIR
    result_dir: Path = RESULT_DIR
    export_dir: Path = EXPORT_DIR
    transfer_dir: Path = TRANSFER_DIR
    receive_dir: Path = RECEIVE_DIR

    def ensure_dirs(self):
        for d in [
            self.data_dir, self.storage_dir, self.cache_dir,
            self.result_dir, self.export_dir, self.transfer_dir,
            self.receive_dir, self.data_dir / "mapping_tables",
        ]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.ensure_dirs()
