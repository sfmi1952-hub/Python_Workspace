"""
사외 SOTA LLM (Claude Opus 4.7) vs 사내 sLM (GPT-OSS) 진단코드 추출 성능 비교.

PoC_Step3 의 입력/참조/매핑 데이터·프롬프트·파이프라인을 100% 동일하게 유지하고,
LLM 호출 부분만 두 모델로 swap 하여 같은 조건에서 추출 결과를 비교합니다.

사용:
    python run_comparison.py
    python run_comparison.py --target alpha       # 알파Plus 약관 사용
    python run_comparison.py --skip-gpt-oss       # Claude 만 실행
    python run_comparison.py --skip-claude        # GPT-OSS 만 실행
"""
import os
import sys
import json
import glob
import argparse
import datetime
import traceback
from pathlib import Path

import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from logic.code_mapper import DiagnosisComparator, DIAGNOSIS_CONFIG  # noqa: E402


# ─────────────────────────────────────────────────────────────────────────────
# 입력 데이터 세팅 (PoC_Step3 와 동일한 입력)
# ─────────────────────────────────────────────────────────────────────────────
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
CODE_DIR = os.path.join(DATA_DIR, "code")        # 매핑 테이블 (진단분류코드 등)
NEW_DIR = os.path.join(DATA_DIR, "new")          # 타겟 약관 PDF + 입력 템플릿 Excel
RAG_DIR = os.path.join(DATA_DIR, "rag")          # 참조 약관 (Phase 1 로직 학습용)
RESULT_DIR = os.path.join(DATA_DIR, "result")


TARGET_PRESETS = {
    "health": {
        "label": "마이헬스 파트너 (건강보험)",
        "pdf": "무배당 삼성화재 건강보험 마이헬스 파트너(2508.12) 4종(일반형)-807-821_SAMPLE_w_별표.pdf",
        "excel": "무배당_삼성화재_건강보험_마이헬스_파트너(2508.12)_4종_일반형_SAMPLE.xlsx",
    },
    "alpha": {
        "label": "알파Plus 보장보험",
        "pdf": "무배당 알파Plus보장보험2601약관-210-894_SAMPLE.pdf",
        "excel": "무배당 알파Plus보장보험2601약관_SAMPLE.xlsx",
    },
}


def collect_mapping_files():
    """진단분류코드 매핑 파일만 골라서 반환 (진단코드 비교이므로)."""
    files = sorted(glob.glob(os.path.join(CODE_DIR, "*.xlsx")))
    return [f for f in files if "진단분류" in os.path.basename(f) or "FCDF131" in os.path.basename(f)] or files


def collect_ref_files():
    """RAG 디렉토리의 참조 약관(PDF+Excel) 페어를 폴더 단위로 묶어 반환."""
    pdfs = sorted(glob.glob(os.path.join(RAG_DIR, "*.pdf")))
    xlsxs = sorted(glob.glob(os.path.join(RAG_DIR, "*.xlsx")))
    return pdfs + xlsxs


def make_logger(log_path):
    log_lines = []

    def logger(msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}"
        print(line)
        log_lines.append(line)
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception:
            pass

    return logger, log_lines


def build_comparison_report(claude_res, gpt_oss_res, report_path, logger):
    """두 결과 DataFrame 을 담보별로 나란히 비교한 Excel 리포트 생성."""

    cfg = DIAGNOSIS_CONFIG
    code_col = cfg["key"]

    def _slim(res, suffix):
        if not res or "dataframe" not in res:
            return None
        df = res["dataframe"].copy()
        keep = [
            "담보명_출력물명칭",
            "세부담보템플릿명",
            code_col,
            "Confidence",
            "Source",
            "Ref_Page",
            "Code_Mapping_Reason",
        ]
        keep = [c for c in keep if c in df.columns]
        df = df[keep].rename(
            columns={
                code_col: f"진단코드_{suffix}",
                "Confidence": f"Confidence_{suffix}",
                "Source": f"Source_{suffix}",
                "Ref_Page": f"Ref_Page_{suffix}",
                "Code_Mapping_Reason": f"근거_{suffix}",
            }
        )
        return df

    df_c = _slim(claude_res, "Claude")
    df_g = _slim(gpt_oss_res, "GPTOSS")

    if df_c is not None and df_g is not None:
        merged = pd.merge(
            df_c, df_g,
            on=["담보명_출력물명칭", "세부담보템플릿명"],
            how="outer",
        )
        merged["코드_일치여부"] = merged.apply(
            lambda r: "일치" if str(r.get("진단코드_Claude", "")).strip() == str(r.get("진단코드_GPTOSS", "")).strip() and str(r.get("진단코드_Claude", "")).strip() != "" else ("불일치" if str(r.get("진단코드_Claude", "")).strip() != str(r.get("진단코드_GPTOSS", "")).strip() else "양쪽 미추론"),
            axis=1,
        )
    elif df_c is not None:
        merged = df_c
    elif df_g is not None:
        merged = df_g
    else:
        logger("비교할 결과가 없습니다.")
        return None

    # ── 요약 시트 작성 ─────────────────────────────────────────────────────
    summary_rows = []

    def _stat(res, label):
        if not res or "error" in res:
            return {"모델": label, "추출_시도": 0, "매칭_성공": 0, "추론_성공률(%)": 0, "Confidence_high(%)": 0, "API_호출수": 0, "Input_Tokens": 0, "Output_Tokens": 0, "모델명": "", "비고": res.get("error", "결과 없음") if res else "스킵"}
        df = res["dataframe"]
        total = len(df)
        filled = int(df[code_col].astype(str).str.strip().replace({"nan": ""}).astype(bool).sum())
        high_conf = int((df["Confidence"].astype(str).str.lower() == "high").sum())
        usage = res.get("token_usage", {})
        return {
            "모델": label,
            "추출_시도": total,
            "매칭_성공": res.get("matched", 0),
            "코드_추출_완료": filled,
            "추론_성공률(%)": round(filled / total * 100, 1) if total else 0,
            "Confidence_high(%)": round(high_conf / total * 100, 1) if total else 0,
            "API_호출수": usage.get("calls", 0),
            "Input_Tokens": usage.get("input", 0),
            "Output_Tokens": usage.get("output", 0),
            "모델명": res.get("model", ""),
            "비고": "",
        }

    if claude_res:
        summary_rows.append(_stat(claude_res, "Claude Opus 4.7 (사외 SOTA)"))
    if gpt_oss_res:
        summary_rows.append(_stat(gpt_oss_res, "GPT-OSS (사내 sLM)"))

    df_summary = pd.DataFrame(summary_rows)

    # 일치율 계산
    agreement_rows = []
    if df_c is not None and df_g is not None and "코드_일치여부" in merged.columns:
        vc = merged["코드_일치여부"].value_counts()
        total = int(vc.sum())
        for k in ["일치", "불일치", "양쪽 미추론"]:
            cnt = int(vc.get(k, 0))
            agreement_rows.append({"구분": k, "건수": cnt, "비율(%)": round(cnt / total * 100, 1) if total else 0})
        agreement_rows.append({"구분": "총합", "건수": total, "비율(%)": 100.0})
    df_agreement = pd.DataFrame(agreement_rows)

    with pd.ExcelWriter(report_path, engine="openpyxl") as xw:
        df_summary.to_excel(xw, sheet_name="요약", index=False)
        if not df_agreement.empty:
            df_agreement.to_excel(xw, sheet_name="모델간_일치율", index=False)
        merged.to_excel(xw, sheet_name="담보별_비교", index=False)
        if df_c is not None:
            df_c.to_excel(xw, sheet_name="Claude_원본", index=False)
        if df_g is not None:
            df_g.to_excel(xw, sheet_name="GPTOSS_원본", index=False)

    logger(f"비교 리포트 저장: {report_path}")
    return report_path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=list(TARGET_PRESETS.keys()), default="health")
    parser.add_argument("--skip-claude", action="store_true")
    parser.add_argument("--skip-gpt-oss", action="store_true")
    args = parser.parse_args()

    preset = TARGET_PRESETS[args.target]
    target_pdf = os.path.join(NEW_DIR, preset["pdf"])
    target_excel = os.path.join(NEW_DIR, preset["excel"])

    if not os.path.exists(target_pdf):
        raise FileNotFoundError(f"타겟 PDF 없음: {target_pdf}")
    if not os.path.exists(target_excel):
        raise FileNotFoundError(f"타겟 Excel 없음: {target_excel}")

    mapping_files = collect_mapping_files()
    ref_files = collect_ref_files()

    os.makedirs(RESULT_DIR, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(RESULT_DIR, f"run_{args.target}_{ts}.log")
    logger, _ = make_logger(log_path)

    logger("=" * 70)
    logger(f"PoC_Step6 진단코드 추출 모델 비교 실험 시작")
    logger(f"타겟 약관 : {preset['label']}")
    logger(f"  - PDF   : {os.path.basename(target_pdf)}")
    logger(f"  - Excel : {os.path.basename(target_excel)}")
    logger(f"매핑 파일 ({len(mapping_files)}): {[os.path.basename(m) for m in mapping_files]}")
    logger(f"참조 파일 ({len(ref_files)}): {len(ref_files)} 개")
    logger("=" * 70)

    claude_res = None
    gpt_oss_res = None

    # ── 1) Claude Opus 4.7 ─────────────────────────────────────────────────
    if not args.skip_claude:
        try:
            logger("\n>>> Claude Opus 4.7 (사외 SOTA LLM) 호출 시작")
            from logic.claude_core import ClaudeCore
            claude_provider = ClaudeCore()
            comp = DiagnosisComparator(claude_provider, "Claude_Opus_4.7")
            claude_res = comp.process(
                target_pdf, target_excel, mapping_files,
                ref_files=ref_files, result_dir=RESULT_DIR, logger=logger,
            )
            logger(f">>> Claude 결과: {claude_res.get('matched', 0)}/{claude_res.get('total', 0)} 매칭, "
                   f"토큰 IN={claude_res.get('token_usage', {}).get('input', 0)} OUT={claude_res.get('token_usage', {}).get('output', 0)}")
        except Exception as e:
            logger(f">>> Claude 실행 실패: {e}")
            logger(traceback.format_exc())
            claude_res = {"error": str(e), "label": "Claude_Opus_4.7"}

    # ── 2) GPT-OSS (사내 sLM) ──────────────────────────────────────────────
    if not args.skip_gpt_oss:
        try:
            logger("\n>>> GPT-OSS (사내 sLM) 호출 시작")
            from logic.gpt_oss_core import GPTOSSCore
            gpt_provider = GPTOSSCore()
            comp = DiagnosisComparator(gpt_provider, "GPT_OSS")
            gpt_oss_res = comp.process(
                target_pdf, target_excel, mapping_files,
                ref_files=ref_files, result_dir=RESULT_DIR, logger=logger,
            )
            logger(f">>> GPT-OSS 결과: {gpt_oss_res.get('matched', 0)}/{gpt_oss_res.get('total', 0)} 매칭, "
                   f"토큰 IN={gpt_oss_res.get('token_usage', {}).get('input', 0)} OUT={gpt_oss_res.get('token_usage', {}).get('output', 0)}")
        except Exception as e:
            logger(f">>> GPT-OSS 실행 실패: {e}")
            logger(traceback.format_exc())
            gpt_oss_res = {"error": str(e), "label": "GPT_OSS"}

    # ── 3) 비교 리포트 생성 ────────────────────────────────────────────────
    report_path = os.path.join(RESULT_DIR, f"Comparison_Report_{args.target}_{ts}.xlsx")
    try:
        build_comparison_report(claude_res, gpt_oss_res, report_path, logger)
    except Exception as e:
        logger(f"리포트 생성 실패: {e}")
        logger(traceback.format_exc())

    logger("\n" + "=" * 70)
    logger("실험 완료")
    logger(f"  - 로그       : {log_path}")
    logger(f"  - 리포트     : {report_path}")
    if claude_res and "result_path" in claude_res:
        logger(f"  - Claude 결과: {claude_res['result_path']}")
    if gpt_oss_res and "result_path" in gpt_oss_res:
        logger(f"  - GPT-OSS 결과: {gpt_oss_res['result_path']}")
    logger("=" * 70)


if __name__ == "__main__":
    main()
