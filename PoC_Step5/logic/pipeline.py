"""PoC Step 5 파이프라인 - 2단계 구조.

Phase 1 (convert):
  - Method 1: Word(.docx) → markdown (python-docx)
  - Method 2: PDF → markdown (Adobe PDF Extract API)
  - 결과: data/output/method1_baseline/converted.md, method2_adobe/converted.md

Phase 2 (extract):
  - 기존 converted.md를 읽어서 LLM 배치 추출
  - 정답지와 비교 → 리포트 생성
"""

import logging
import os
import time
from pathlib import Path
from typing import Callable, Dict, List

from .config import Settings
from .openai_core import OpenAICore
from .converters.base_converter import BaseConverter, ConversionResult
from .converters.docx_converter import DocxConverter
from .converters.adobe_converter import AdobeConverter
from .extraction.llm_extractor import LLMExtractor
from .evaluator.accuracy import AccuracyEvaluator, AccuracyMetrics
from .evaluator.report_generator import ReportGenerator

logger = logging.getLogger(__name__)


class ComparisonPipeline:
    """2단계 파이프라인 오케스트레이터.

    Phase 1: convert  → Word/PDF → markdown 변환만 수행
    Phase 2: extract  → markdown + 정답지 → LLM 추출 + 평가
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        settings.ensure_dirs()

        self.openai = OpenAICore(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
        )
        self.extractor = LLMExtractor(self.openai)
        self.evaluator = AccuracyEvaluator()
        self.reporter = ReportGenerator()

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
            log("\n===== [Phase 1] Method 1: Word(docx) → python-docx → Markdown =====")
            output_dir = self.settings.output_dir / "method1_baseline"
            md_path, timing = self._convert_single(
                DocxConverter(), docx_path, output_dir, log
            )
            result["method1"] = {"md_path": str(md_path) if md_path else None, "timing": timing}

        if method in ("both", "method2"):
            log("\n===== [Phase 1] Method 2: PDF → Adobe Extract API → Markdown =====")
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
    # Phase 2: LLM 추출 + 평가
    # ══════════════════════════════════════════════════════════

    def run_extract(
        self,
        ground_truth_path: str,
        method: str = "both",
        log: Callable = print,
    ) -> dict:
        """Phase 2: 기존 converted.md 기반 LLM 추출 + 정답 비교.

        Returns:
            {"method1": {"excel_path": ..., "metrics": ..., "timing": ...}, ...}
        """
        result = {}

        # 정답지에서 담보 목록 로드
        log("[Load] Loading coverage list from ground truth...")
        coverages = LLMExtractor.load_coverage_list(ground_truth_path)
        log(f"[Load] {len(coverages)} unique coverages loaded")

        if method in ("both", "method1"):
            log("\n===== [Phase 2] Method 1: LLM Extraction (Baseline) =====")
            output_dir = self.settings.output_dir / "method1_baseline"
            md_path = output_dir / "converted.md"
            r = self._extract_single(
                md_path, coverages, output_dir, ground_truth_path, "Method 1", log
            )
            result["method1"] = r

        if method in ("both", "method2"):
            log("\n===== [Phase 2] Method 2: LLM Extraction (Adobe) =====")
            output_dir = self.settings.output_dir / "method2_adobe"
            md_path = output_dir / "converted.md"
            r = self._extract_single(
                md_path, coverages, output_dir, ground_truth_path, "Method 2", log
            )
            result["method2"] = r

        # 비교 리포트
        if method == "both" and "method1" in result and "method2" in result:
            log("\n===== Generating Comparison Report =====")
            report_path = self.reporter.generate(
                method1_metrics=result["method1"]["metrics"],
                method2_metrics=result["method2"]["metrics"],
                method1_timing=result["method1"]["timing"],
                method2_timing=result["method2"]["timing"],
                output_dir=str(self.settings.output_dir / "comparison"),
            )
            result["comparison_report"] = report_path

            m1_rate = result["method1"]["metrics"].row_match_rate
            m2_rate = result["method2"]["metrics"].row_match_rate
            if m1_rate > m2_rate:
                result["winner"] = "Method 1 (Baseline)"
            elif m2_rate > m1_rate:
                result["winner"] = "Method 2 (Adobe)"
            else:
                result["winner"] = "Tie"

            log(f"[Report] Saved to: {report_path}")
            log(f"[Result] Winner: {result['winner']}")

        return result

    def _extract_single(
        self,
        md_path: Path,
        coverages: List[Dict[str, str]],
        output_dir: Path,
        ground_truth_path: str,
        method_label: str,
        log: Callable,
    ) -> dict:
        """단일 메서드의 LLM 추출 + 평가."""
        timing = {}

        if not md_path.exists() or md_path.stat().st_size == 0:
            log(f"[ERROR] {method_label}: converted.md not found at {md_path}")
            log("[HINT] Run --phase convert first")
            return {
                "excel_path": None,
                "metrics": AccuracyMetrics(),
                "timing": {},
            }

        markdown_text = md_path.read_text(encoding="utf-8")
        log(f"[{method_label}] Loaded markdown: {len(markdown_text):,} chars")

        # LLM 배치 추출
        log(f"[{method_label}] Filling parameters for {len(coverages)} coverages via GPT...")
        t0 = time.time()
        rows = self.extractor.extract_with_batches(
            coverages=coverages,
            document_markdown=markdown_text,
            log=log,
        )
        timing["llm_extraction"] = time.time() - t0
        log(f"[{method_label}] Total {len(rows)} rows generated in {timing['llm_extraction']:.2f}s")

        if not rows:
            log(f"[{method_label}] WARN: No rows extracted by LLM")
            return {
                "excel_path": None,
                "metrics": AccuracyMetrics(),
                "timing": timing,
            }

        # 엑셀 저장
        excel_path = str(output_dir / "extraction_result.xlsx")
        LLMExtractor.export_to_excel(rows, excel_path)
        log(f"[{method_label}] Saved {len(rows)} rows to {excel_path}")

        # 정답 비교
        log(f"[{method_label}] Comparing with ground truth...")
        metrics = self.evaluator.compare(excel_path, ground_truth_path)
        log(f"[{method_label}] Row match rate: {metrics.row_match_rate:.1%}")
        log(f"[{method_label}] Coverage perfect rate: {metrics.coverage_perfect_rate:.1%}")

        timing["total"] = sum(timing.values())
        return {
            "excel_path": excel_path,
            "metrics": metrics,
            "timing": timing,
        }

    # ══════════════════════════════════════════════════════════
    # Legacy: 한번에 실행 (하위 호환)
    # ══════════════════════════════════════════════════════════

    def run(
        self,
        docx_path: str = "",
        pdf_path: str = "",
        ground_truth_path: str = "",
        method: str = "both",
        skip_convert: bool = False,
        log: Callable = print,
    ) -> dict:
        """전체 실행 (Phase 1 + Phase 2)."""
        # Phase 1
        if not skip_convert:
            self.run_convert(
                docx_path=docx_path,
                pdf_path=pdf_path,
                method=method,
                log=log,
            )

        # Phase 2
        return self.run_extract(
            ground_truth_path=ground_truth_path,
            method=method,
            log=log,
        )
