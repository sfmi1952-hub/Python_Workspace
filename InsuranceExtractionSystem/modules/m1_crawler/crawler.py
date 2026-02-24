"""
M1: 약관 수집 모듈 (policy-crawler)
삼성화재 공시 웹페이지에서 약관 PDF 자동 다운로드

- 공시정보 페이지 크롤링 (HPIF0103)
- 상품유형별 분류 (건강/자동차/화재/생명 등)
- 신규 출시·개정 약관 자동 감지 (diff 비교)
- 메타데이터 기록
"""
import os
import hashlib
import datetime
from pathlib import Path
from dataclasses import dataclass

from config.settings import settings


@dataclass
class CrawlResult:
    product_code: str
    product_name: str
    product_type: str
    version: str
    pdf_path: str
    source_url: str
    is_new: bool
    crawled_at: datetime.datetime


class PolicyCrawler:
    """약관 PDF 크롤러 (삼성화재 공시페이지)"""

    PRODUCT_TYPES = ["건강보험", "자동차보험", "화재보험", "생명보험", "상해보험"]

    def __init__(self, download_dir: Path = None):
        self.download_dir = download_dir or settings.storage_dir
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.target_url = settings.crawler_target_url

    async def crawl(self, product_type: str = None, logger=print) -> list[CrawlResult]:
        """
        공시페이지에서 약관 PDF 목록을 수집합니다.
        운영 시 playwright 기반 실제 크롤링 구현 필요.
        """
        logger(f"[M1] 크롤링 시작: {self.target_url}")

        # TODO: Playwright 기반 실제 크롤링 구현
        # 현재는 로컬 디렉토리의 PDF를 스캔하는 스텁 구현
        results = []

        for pdf_file in self.download_dir.rglob("*.pdf"):
            rel_path = pdf_file.relative_to(self.download_dir)
            parts = rel_path.parts

            # 폴더 구조에서 상품 정보 추론
            p_type = parts[0] if len(parts) > 1 else "미분류"
            p_name = pdf_file.stem
            p_code = self._generate_code(p_name)
            version = self._detect_version(pdf_file)

            results.append(CrawlResult(
                product_code=p_code,
                product_name=p_name,
                product_type=p_type,
                version=version,
                pdf_path=str(pdf_file),
                source_url=f"{self.target_url}/policy/{p_code}",
                is_new=True,  # diff 비교 후 결정
                crawled_at=datetime.datetime.now(),
            ))

        logger(f"  > 수집 완료: {len(results)}건")
        return results

    def detect_new_policies(self, existing_hashes: set, logger=print) -> list[CrawlResult]:
        """기존 해시와 비교하여 신규/변경 약관만 반환"""
        all_results = []

        for pdf_file in self.download_dir.rglob("*.pdf"):
            file_hash = self._compute_hash(str(pdf_file))
            if file_hash not in existing_hashes:
                all_results.append(CrawlResult(
                    product_code=self._generate_code(pdf_file.stem),
                    product_name=pdf_file.stem,
                    product_type=self._infer_type(pdf_file),
                    version=self._detect_version(pdf_file),
                    pdf_path=str(pdf_file),
                    source_url="",
                    is_new=True,
                    crawled_at=datetime.datetime.now(),
                ))

        logger(f"  > 신규/변경 감지: {len(all_results)}건")
        return all_results

    @staticmethod
    def _generate_code(name: str) -> str:
        return hashlib.md5(name.encode()).hexdigest()[:8].upper()

    @staticmethod
    def _compute_hash(file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @staticmethod
    def _detect_version(pdf_path: Path) -> str:
        mtime = datetime.datetime.fromtimestamp(pdf_path.stat().st_mtime)
        return mtime.strftime("v%y%m")

    @staticmethod
    def _infer_type(pdf_path: Path) -> str:
        name = pdf_path.name.lower()
        type_map = {
            "건강": "건강보험", "암": "건강보험", "질병": "건강보험",
            "자동차": "자동차보험", "차량": "자동차보험",
            "화재": "화재보험", "재물": "화재보험",
            "생명": "생명보험", "사망": "생명보험",
            "상해": "상해보험", "재해": "상해보험",
        }
        for keyword, ptype in type_map.items():
            if keyword in name:
                return ptype
        return "미분류"
