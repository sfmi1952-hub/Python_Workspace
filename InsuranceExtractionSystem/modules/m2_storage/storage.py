"""
M2: 약관 저장소 (policy-storage)
파일시스템 기반 저장소 — S3 호환 인터페이스

구조: /{상품유형}/{상품명}/v{YYMM}.{revision}/
  - 원본 PDF
  - 전처리 결과 (JSON, Markdown)
  - 메타데이터
"""
import os
import shutil
import json
import datetime
from pathlib import Path
from dataclasses import dataclass, asdict

from config.settings import settings


@dataclass
class PolicyMeta:
    product_code: str
    product_name: str
    product_type: str
    version: str
    pdf_filename: str
    total_pages: int = 0
    status: str = "stored"     # stored / preprocessed / extracted
    stored_at: str = ""
    last_extracted: str = ""


class PolicyStorage:
    """파일시스템 기반 약관 저장소"""

    def __init__(self, base_dir: Path = None):
        self.base_dir = base_dir or settings.storage_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_policy_dir(self, product_type: str, product_name: str, version: str) -> Path:
        safe_name = product_name.replace("/", "_").replace("\\", "_")
        return self.base_dir / product_type / safe_name / version

    def store(self, pdf_path: str, product_type: str, product_name: str,
              version: str, product_code: str, logger=print) -> PolicyMeta:
        """약관 PDF를 저장소에 저장합니다."""
        policy_dir = self._get_policy_dir(product_type, product_name, version)
        policy_dir.mkdir(parents=True, exist_ok=True)

        # PDF 복사
        dest = policy_dir / os.path.basename(pdf_path)
        shutil.copy2(pdf_path, str(dest))

        # 메타데이터 생성
        meta = PolicyMeta(
            product_code=product_code,
            product_name=product_name,
            product_type=product_type,
            version=version,
            pdf_filename=dest.name,
            stored_at=datetime.datetime.now().isoformat(),
        )

        # 메타데이터 저장
        meta_path = policy_dir / "meta.json"
        meta_path.write_text(json.dumps(asdict(meta), ensure_ascii=False, indent=2), encoding="utf-8")

        logger(f"[M2] 저장 완료: {product_type}/{product_name}/{version}")
        return meta

    def get_pdf_path(self, product_type: str, product_name: str, version: str) -> str | None:
        policy_dir = self._get_policy_dir(product_type, product_name, version)
        for f in policy_dir.glob("*.pdf"):
            return str(f)
        return None

    def get_meta(self, product_type: str, product_name: str, version: str) -> PolicyMeta | None:
        policy_dir = self._get_policy_dir(product_type, product_name, version)
        meta_path = policy_dir / "meta.json"
        if meta_path.exists():
            data = json.loads(meta_path.read_text(encoding="utf-8"))
            return PolicyMeta(**data)
        return None

    def list_products(self, product_type: str = None) -> list[PolicyMeta]:
        """저장된 약관 목록을 반환합니다."""
        results = []
        search_dir = self.base_dir / product_type if product_type else self.base_dir

        for meta_path in search_dir.rglob("meta.json"):
            try:
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                results.append(PolicyMeta(**data))
            except Exception:
                pass

        return sorted(results, key=lambda m: m.stored_at, reverse=True)

    def save_preprocessed(self, product_type: str, product_name: str,
                          version: str, preprocess_result: dict):
        """전처리 결과를 저장합니다."""
        policy_dir = self._get_policy_dir(product_type, product_name, version)
        policy_dir.mkdir(parents=True, exist_ok=True)

        # 구조화 결과 저장
        result_path = policy_dir / "preprocessed.json"
        result_path.write_text(
            json.dumps(preprocess_result, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )

        # 원문 Markdown 저장
        if "raw_text" in preprocess_result:
            md_path = policy_dir / "content.md"
            md_path.write_text(preprocess_result["raw_text"], encoding="utf-8")
