"""PoC Step 5: Adobe PDF Services API vs Baseline Comparison CLI.

2단계 실행 구조:
  --phase convert  : 문서 -> 마크다운 변환만 수행
  --phase extract  : 레이아웃 -> 매칭 -> LLM 추출
  --phase all      : convert + extract 전체 실행 (기본값)
"""

import argparse
import io
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from logic.config import Settings
from logic.pipeline import ComparisonPipeline

# cp949 인코딩 에러 방지: stdout을 UTF-8 래퍼로 교체
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)

log_buffer = []
_log_file = None


def log(message: str):
    timestamp = datetime.now().strftime("%H:%M:%S")
    entry = f"[{timestamp}] {message}"
    print(entry, flush=True)
    log_buffer.append(entry)
    if _log_file:
        _log_file.write(entry + "\n")
        _log_file.flush()


def main():
    parser = argparse.ArgumentParser(
        description="PoC Step 5: PDF Table Extraction - Adobe vs Baseline Comparison"
    )
    parser.add_argument(
        "--phase",
        choices=["convert", "extract", "all"],
        default="all",
        help="Execution phase: 'convert' (doc->md only), 'extract' (layout->match->LLM), 'all' (both)",
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
        "--layout",
        required=False,
        help="Path to layout .xlsx (required for extract/all phase)",
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
        if not args.layout:
            parser.error("--layout is required for extract phase")

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    settings = Settings()
    settings.ensure_dirs()

    # Log file for monitoring in a separate terminal
    global _log_file
    log_file_path = Path(settings.output_dir) / "extraction_log.txt"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    _log_file = open(log_file_path, "w", encoding="utf-8")

    # 로그 모니터링용 CMD 창 자동 오픈
    subprocess.Popen(
        ["powershell", "-Command",
         f"$Host.UI.RawUI.WindowTitle = 'Log Monitor'; "
         f"Write-Host '=== Real-time Log Monitor ===' -ForegroundColor Cyan; "
         f"Write-Host 'Log file: {log_file_path}' -ForegroundColor Yellow; "
         f"Write-Host ''; "
         f"Get-Content '{log_file_path}' -Wait -Tail 100"],
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )

    log("=" * 60)
    log("PoC Step 5: Adobe PDF Services API vs Baseline Comparison")
    log("=" * 60)
    log(f"Log file: {log_file_path}")
    log(f"Phase: {args.phase}")
    log(f"Method: {args.method}")
    log(f"LLM Model: {settings.openai_model}")
    log(f"Batch Size: {args.batch_size}")
    if args.docx:
        log(f"DOCX Input: {args.docx}")
    if args.pdf:
        log(f"PDF Input: {args.pdf}")
    if args.layout:
        log(f"Layout: {args.layout}")
    log("")

    pipeline = ComparisonPipeline(settings)
    pipeline.extractor.batch_size = args.batch_size

    # ── Phase 1: Convert ──────────────────────────────────
    if args.phase in ("convert", "all"):
        log("=" * 40)
        log("PHASE 1: Document -> Markdown Conversion")
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
        log("PHASE 2: Layout -> Matching -> LLM Extraction")
        log("=" * 40)
        result = pipeline.run_extract(
            layout_path=args.layout,
            method=args.method,
            log=log,
        )

        # Print summary
        log("")
        log("=" * 60)
        log("EXTRACTION RESULTS")
        log("=" * 60)

        for method_key, label in [("method1", "Method 1 (Baseline - python-docx)"),
                                   ("method2", "Method 2 (Adobe PDF Services)")]:
            if method_key not in result:
                continue
            r = result[method_key]
            log(f"{label}:")
            if r.get("excel_path"):
                log(f"  Result Excel: {r['excel_path']}")
            timing = r.get("timing", {})
            if timing.get("llm_extraction"):
                log(f"  LLM Extraction Time: {timing['llm_extraction']:.2f}s")
            log("")

        log("=" * 60)

    # Close log file
    if _log_file:
        _log_file.close()


if __name__ == "__main__":
    main()
