import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


@dataclass
class Settings:
    # OpenAI
    openai_api_key: Optional[str] = field(
        default_factory=lambda: os.getenv("OPENAI_API_KEY")
    )
    openai_model: str = field(
        default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-5.2")
    )

    # Adobe PDF Services
    adobe_client_id: Optional[str] = field(
        default_factory=lambda: os.getenv("ADOBE_CLIENT_ID")
    )
    adobe_client_secret: Optional[str] = field(
        default_factory=lambda: os.getenv("ADOBE_CLIENT_SECRET")
    )

    # Paths
    project_root: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent.parent
    )

    @property
    def input_dir(self) -> Path:
        return self.project_root / "data" / "input"

    @property
    def output_dir(self) -> Path:
        return self.project_root / "data" / "output"

    @property
    def cache_dir(self) -> Path:
        return self.project_root / "data" / "cache"

    def ensure_dirs(self) -> None:
        dirs = [
            self.input_dir / "docx",
            self.input_dir / "pdf",
            self.input_dir / "ground_truth",
            self.output_dir / "method1_baseline",
            self.output_dir / "method2_adobe",
            self.output_dir / "comparison",
            self.cache_dir,
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
