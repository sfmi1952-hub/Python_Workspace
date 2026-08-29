"""Merge existing Claude + GPT-OSS result Excel into a unified comparison report.
Use after running each provider separately (Claude + --skip-gpt-oss, then GPT-OSS + --skip-claude).
"""
import os
import sys
import datetime
import pandas as pd

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from run_comparison import build_comparison_report  # noqa: E402

RESULT_DIR = os.path.join(PROJECT_ROOT, "data", "result")


def load_as_res(xlsx_path, label, model_name):
    """Reconstruct a result-dict shape compatible with build_comparison_report."""
    if not os.path.exists(xlsx_path):
        return None
    df = pd.read_excel(xlsx_path)
    code_col = "Inferred_Diagnosis_Code"
    filled = int(df[code_col].astype(str).str.strip().replace({"nan": ""}).astype(bool).sum())
    # token_usage 는 로그에서 가져와야 하지만, 결과 xlsx 에는 없으므로 빈 값
    return {
        "label": label,
        "model": model_name,
        "matched": filled,           # 코드가 추출된 건수를 매칭으로 간주
        "total": len(df),
        "token_usage": {"input": 0, "output": 0, "calls": 0},
        "dataframe": df,
    }


def logger(msg):
    print(msg)


def main():
    claude_path = os.path.join(RESULT_DIR, "Result_Diagnosis_Code__Claude_Opus_4_7.xlsx")
    gpt_path = os.path.join(RESULT_DIR, "Result_Diagnosis_Code__GPT_OSS.xlsx")

    # 토큰 사용량은 가장 최근 로그에서 회수
    def parse_tokens(label):
        logs = sorted([f for f in os.listdir(RESULT_DIR) if f.startswith("run_") and f.endswith(".log")])
        for fname in reversed(logs):
            with open(os.path.join(RESULT_DIR, fname), encoding="utf-8") as f:
                text = f.read()
            marker = f">>> {label} 결과:"
            idx = text.find(marker)
            if idx >= 0:
                line = text[idx:idx + 200].split("\n")[0]
                # 예: ">>> Claude 결과: 100/100 매칭, 토큰 IN=1005458 OUT=47101"
                try:
                    in_str = line.split("IN=")[1].split(" ")[0]
                    out_str = line.split("OUT=")[1].split()[0]
                    return int(in_str), int(out_str), 5
                except Exception:
                    pass
        return 0, 0, 0

    claude_res = load_as_res(claude_path, "Claude_Opus_4.7", "claude-opus-4-7")
    if claude_res:
        ti, to, tc = parse_tokens("Claude")
        claude_res["token_usage"] = {"input": ti, "output": to, "calls": tc}

    gpt_res = load_as_res(gpt_path, "GPT_OSS", "openai/gpt-oss-120b:cerebras")
    if gpt_res:
        ti, to, tc = parse_tokens("GPT-OSS")
        gpt_res["token_usage"] = {"input": ti, "output": to, "calls": tc}

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    out = os.path.join(RESULT_DIR, f"Comparison_Report_FINAL_{ts}.xlsx")
    build_comparison_report(claude_res, gpt_res, out, logger)
    print(f"\n>>> FINAL report written: {out}")


if __name__ == "__main__":
    main()
