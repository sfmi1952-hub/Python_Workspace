"""PoC Step 5: Adobe PDF Services API vs Baseline Comparison CLI.

2단계 실행 구조:
  --phase convert  : 문서 → 마크다운 변환만 수행
  --phase extract  : 마크다운 → LLM 추출 + 정답 비교
  --phase all      : convert + extract 전체 실행 (기본값)
"""

import argparse
import logging
from datetime import datetime

from logic.config import Settings
from logic.pipeline import ComparisonPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

log_buffer = []


def log(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry)
    log_buffer.append(entry)


def main():
    parser = argparse.ArgumentParser(
        description="PoC Step 5: PDF Table Extraction - Adobe vs Baseline Comparison"
    )
    parser.add_argument(
        "--phase",
        choices=["convert", "extract", "all"],
        default="all",
        help="Execution phase: 'convert' (doc→md only), 'extract' (md→LLM+eval), 'all' (both)",
    )
    parser.add_argument(
        "--docx",
        required=False,
        help="Path to source .docx file (Method 1 input)",
    )
    parser.add_argument(
        "--pdf",
        required=False,
        help="Path to source .pdf file (Method 2 input)",
    )
    parser.add_argument(
        "--ground-truth",
        required=False,
        help="Path to ground truth .xlsx (required for extract/all phase)",
    )
    parser.add_argument(
        "--method",
        choices=["both", "method1", "method2"],
        default="both",
        help="Which method(s) to run (default: both)",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of coverages per LLM batch (default: 100)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    # Validation
    if args.phase in ("convert", "all"):
        if args.method in ("both", "method1") and not args.docx:
            parser.error("--docx is required for method1 conversion")
        if args.method in ("both", "method2") and not args.pdf:
            parser.error("--pdf is required for method2 conversion")

    if args.phase in ("extract", "all"):
        if not args.ground_truth:
            parser.error("--ground-truth is required for extract phase")

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    settings = Settings()
    settings.ensure_dirs()

    log("=" * 60)
    log("PoC Step 5: Adobe PDF Services API vs Baseline Comparison")
    log("=" * 60)
    log(f"Phase: {args.phase}")
    log(f"Method: {args.method}")
    log(f"LLM Model: {settings.openai_model}")
    log(f"Batch Size: {args.batch_size}")
    if args.docx:
        log(f"DOCX Input: {args.docx}")
    if args.pdf:
        log(f"PDF Input: {args.pdf}")
    if args.ground_truth:
        log(f"Ground Truth: {args.ground_truth}")
    log("")

    pipeline = ComparisonPipeline(settings)
    pipeline.extractor.batch_size = args.batch_size

    # ── Phase 1: Convert ──────────────────────────────────
    if args.phase in ("convert", "all"):
        log("=" * 40)
        log("PHASE 1: Document → Markdown Conversion")
        log("=" * 40)
        convert_result = pipeline.run_convert(
            docx_path=args.docx or "",
            pdf_path=args.pdf or "",
            method=args.method,
            log=log,
        )

        log("")
        log("--- Phase 1 Summary ---")
        for key in ("method1", "method2"):
            if key in convert_result:
                r = convert_result[key]
                md = r.get("md_path", "N/A")
                t = r.get("timing", {}).get("conversion", 0)
                log(f"  {key}: {md} (time: {t:.2f}s)")

    # ── Phase 2: Extract ──────────────────────────────────
    if args.phase in ("extract", "all"):
        log("")
        log("=" * 40)
        log("PHASE 2: LLM Extraction + Evaluation")
        log("=" * 40)
        result = pipeline.run_extract(
            ground_truth_path=args.ground_truth,
            method=args.method,
            log=log,
        )

        # Print summary
        log("")
        log("=" * 60)
        log("COMPARISON RESULTS")
        log("=" * 60)

        for method_key, label in [("method1", "Method 1 (Baseline - python-docx)"),
                                   ("method2", "Method 2 (Adobe PDF Services)")]:
            if method_key not in result:
                continue
            m = result[method_key]["metrics"]
            log(f"{label}:")
            log(f"  정답 행 수: {m.total_rows_expected}")
            log(f"  추출 행 수: {m.total_rows_extracted}")
            log(f"  행 일치 수 (집합 교집합): {m.total_rows_matched}")
            log(f"  행 일치율: {m.row_match_rate:.1%}")
            log(f"  담보 수: {m.total_coverages}")
            log(f"  담보 완전일치: {m.perfect_coverages}/{m.total_coverages} "
                f"({m.coverage_perfect_rate:.1%})")
            log(f"  담보 커버리지: {m.coverage_completeness:.1%}")
            log(f"  누락 행: {len(m.missing_rows)}, 초과 행: {len(m.extra_rows)}")
            if m.field_accuracy:
                log("  필드별 정확도:")
                for fld, acc in m.field_accuracy.items():
                    log(f"    {fld}: {acc:.1%}")
            if result[method_key].get("excel_path"):
                log(f"  Result Excel: {result[method_key]['excel_path']}")

        if "winner" in result:
            log("")
            log(f"WINNER: {result['winner']}")

        if "comparison_report" in result:
            log(f"Comparison Report: {result['comparison_report']}")

        log("=" * 60)


if __name__ == "__main__":
    main()
