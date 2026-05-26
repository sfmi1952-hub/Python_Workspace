"""PoC Step 5 파이프라인 - 2단계 구조.

Phase 1 (convert):
  - Method 1: Word(.docx) → markdown (python-docx)
  - Method 2: PDF → markdown (Adobe PDF Extract API)
  - 결과: data/output/method1_baseline/converted.md, method2_adobe/converted.md

Phase 2 (extract):
  - 레이아웃 Excel에서 담보 로드 → markdown 매칭 → LLM 배치 추출
"""

import logging
import time
from pathlib import Path
from typing import Callable, Dict, List

from .config import Settings
from .openai_core import OpenAICore
from .converters.base_converter import BaseConverter, ConversionResult
from .converters.docx_converter import DocxConverter
from .converters.adobe_converter import AdobeConverter
from .extraction.llm_extractor import LLMExtractor, ExtractionRow

logger = logging.getLogger(__name__)


class ComparisonPipeline:
    """2단계 파이프라인 오케스트레이터.

    Phase 1: convert  → Word/PDF → markdown 변환만 수행
    Phase 2: extract  → layout + markdown → LLM 추출
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        settings.ensure_dirs()

        self.openai = OpenAICore(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        self.extractor = LLMExtractor(self.openai)

    # ══════════════════════════════════════════════════════════
    # Phase 1: Document → Markdown 변환
    # ══════════════════════════════════════════════════════════

    def run_convert(
        self,
        docx_path: str = "",
        pdf_path: str = "",
        method: str = "both",
        log: Callable = print,
    ) -> dict:
        """Phase 1: 문서 → 마크다운 변환만 수행.

        Returns:
            {"method1": {"md_path": ..., "timing": ...}, "method2": {...}}
        """
        result = {}

        if method in ("both", "method1"):
            log("\n===== [Phase 1] Method 1: Word(docx) -> python-docx -> Markdown =====")
            output_dir = self.settings.output_dir / "method1_baseline"
            md_path, timing = self._convert_single(
                DocxConverter(), docx_path, output_dir, log
            )
            result["method1"] = {"md_path": str(md_path) if md_path else None, "timing": timing}

        if method in ("both", "method2"):
            log("\n===== [Phase 1] Method 2: PDF -> Adobe Extract API -> Markdown =====")
            output_dir = self.settings.output_dir / "method2_adobe"
            md_path_check = output_dir / "converted.md"

            # Adobe API: 캐시 있으면 스킵
            if md_path_check.exists() and md_path_check.stat().st_size > 0:
                log(f"[Cache] Adobe converted.md already exists ({md_path_check.stat().st_size:,} bytes), skipping API call")
                result["method2"] = {
                    "md_path": str(md_path_check),
                    "timing": {"conversion": 0.0},
                }
            elif not self.settings.adobe_client_id or not self.settings.adobe_client_secret:
                log("[WARN] Adobe API credentials not configured and no cached markdown")
                result["method2"] = {"md_path": None, "timing": {}}
            else:
                converter = AdobeConverter(
                    client_id=self.settings.adobe_client_id,
                    client_secret=self.settings.adobe_client_secret,
                )
                md_path, timing = self._convert_single(
                    converter, pdf_path, output_dir, log
                )
                result["method2"] = {"md_path": str(md_path) if md_path else None, "timing": timing}

        return result

    def _convert_single(
        self,
        converter: BaseConverter,
        file_path: str,
        output_dir: Path,
        log: Callable,
    ) -> tuple:
        """단일 변환기 실행. Returns (md_path, timing_dict)."""
        timing = {}
        output_dir.mkdir(parents=True, exist_ok=True)
        md_path = output_dir / "converted.md"

        # 기존 converted.md가 있으면 스킵
        if md_path.exists() and md_path.stat().st_size > 0:
            log(f"[Cache] Found existing converted.md ({md_path.stat().st_size:,} bytes), skipping")
            timing["conversion"] = 0.0
            return md_path, timing

        log(f"[Convert] {converter.name()}: {file_path}")
        t0 = time.time()
        conversion = converter.convert(file_path)
        timing["conversion"] = time.time() - t0

        if conversion.errors:
            for err in conversion.errors:
                log(f"[WARN] {err}")

        if conversion.markdown_text:
            md_path.write_text(conversion.markdown_text, encoding="utf-8")
            log(f"[Convert] Saved: {md_path} ({len(conversion.markdown_text):,} chars)")
        else:
            log("[ERROR] No markdown content generated")
            return None, timing

        log(f"[Convert] Done in {timing['conversion']:.2f}s")
        return md_path, timing

    # ══════════════════════════════════════════════════════════
    # Phase 2: Layout → 매칭 → LLM 추출
    # ══════════════════════════════════════════════════════════

    def run_extract(
        self,
        layout_path: str,
        method: str = "both",
        log: Callable = print,
    ) -> dict:
        """Phase 2: 레이아웃 기반 LLM 추출.

        Returns:
            {"method1": {"excel_path": ..., "timing": ...}, ...}
        """
        result = {}

        # 레이아웃에서 담보 목록 로드
        log("[Load] Loading coverage list from layout...")
        layout_info = LLMExtractor.load_coverage_from_layout(layout_path)
        raw_coverages = layout_info["coverages"]
        type_label = layout_info["type_label"]
        log(f"[Load] {len(raw_coverages)} coverages loaded from layout")
        log(f"[Load] Type: {type_label}")

        if method in ("both", "method1"):
            log("\n===== [Phase 2] Method 1: LLM Extraction (Baseline) =====")
            output_dir = self.settings.output_dir / "method1_baseline"
            md_path = output_dir / "converted.md"
            r = self._extract_single(
                md_path, raw_coverages, output_dir, type_label, "Method 1", log
            )
            result["method1"] = r

        if method in ("both", "method2"):
            log("\n===== [Phase 2] Method 2: LLM Extraction (Adobe) =====")
            output_dir = self.settings.output_dir / "method2_adobe"
            md_path = output_dir / "converted.md"
            r = self._extract_single(
                md_path, raw_coverages, output_dir, type_label, "Method 2", log
            )
            result["method2"] = r

        return result

    def _extract_single(
        self,
        md_path: Path,
        raw_coverages: List[Dict[str, str]],
        output_dir: Path,
        type_label: str,
        method_label: str,
        log: Callable,
    ) -> dict:
        """단일 메서드의 LLM 추출."""
        timing = {}

        if not md_path.exists() or md_path.stat().st_size == 0:
            log(f"[ERROR] {method_label}: converted.md not found at {md_path}")
            log("[HINT] Run --phase convert first")
            return {"excel_path": None, "timing": {}}

        markdown_text = md_path.read_text(encoding="utf-8")
        log(f"[{method_label}] Loaded markdown: {len(markdown_text):,} chars from {md_path}")

        # 종별 마크다운 필터링
        log(f"[{method_label}] Filtering markdown for type: {type_label}")
        filtered_md = LLMExtractor.filter_markdown_by_type(
            markdown_text, type_label, log=log
        )

        # 레이아웃 담보를 filtered markdown과 매칭
        log(f"[{method_label}] Matching {len(raw_coverages)} coverages against filtered markdown...")
        coverages, unmatched = LLMExtractor.match_coverages_against_markdown(
            raw_coverages, filtered_md, log=log
        )

        # unmatched coverages를 별도 텍스트 파일로 저장
        if unmatched:
            unmatched_path = output_dir / "unmatched_coverages.txt"
            with open(unmatched_path, "w", encoding="utf-8") as f:
                f.write(f"Unmatched Coverages: {len(unmatched)}/{len(raw_coverages)}\n")
                f.write(f"{'=' * 60}\n\n")
                for i, u in enumerate(unmatched, 1):
                    f.write(f"{i:3d}. [{u['담보PMID']}] {u['담보명']}\n")
            log(f"[{method_label}] Saved {len(unmatched)} unmatched coverages to {unmatched_path}")

        if not coverages:
            log(f"[{method_label}] WARN: No coverages matched in markdown")
            # 매칭 안 된 담보도 input 필드만 유지하여 출력
            if unmatched:
                rows = [
                    ExtractionRow(
                        상품코드=u["상품코드"], 담보PMID=u["담보PMID"], 담보명=u["담보명"]
                    )
                    for u in unmatched
                ]
                excel_path = str(output_dir / "extraction_result.xlsx")
                LLMExtractor.export_to_excel(rows, excel_path)
                log(f"[{method_label}] Saved {len(rows)} unmatched rows (input fields only) to {excel_path}")
                return {"excel_path": excel_path, "timing": timing}
            return {"excel_path": None, "timing": timing}

        # LLM 배치 추출
        log(f"")
        log(f"[{method_label}] Starting LLM extraction: {len(coverages)} coverages via {self.openai.primary_model}")
        log(f"[{method_label}] Batch size: {self.extractor.batch_size}")
        t0 = time.time()
        rows = self.extractor.extract_with_batches(
            coverages=coverages,
            document_markdown=filtered_md,
            log=log,
        )
        timing["llm_extraction"] = time.time() - t0

        # 매칭 안 된 담보는 input 필드만 유지하여 추가
        if unmatched:
            log(f"[{method_label}] Adding {len(unmatched)} unmatched coverages (input fields only)")
            for u in unmatched:
                rows.append(ExtractionRow(
                    상품코드=u["상품코드"], 담보PMID=u["담보PMID"], 담보명=u["담보명"]
                ))

        log(f"[{method_label}] Total {len(rows)} rows generated in {timing['llm_extraction']:.2f}s")

        if not rows:
            log(f"[{method_label}] WARN: No rows extracted by LLM")
            return {"excel_path": None, "timing": timing}

        # 엑셀 저장
        excel_path = str(output_dir / "extraction_result.xlsx")
        LLMExtractor.export_to_excel(rows, excel_path)
        log(f"[{method_label}] Saved {len(rows)} rows to {excel_path}")

        timing["total"] = sum(timing.values())
        return {"excel_path": excel_path, "timing": timing}
