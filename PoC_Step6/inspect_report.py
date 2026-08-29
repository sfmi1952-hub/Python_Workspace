"""Inspect comparison report sheets."""
import os, sys
import pandas as pd

RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "result")
# 가장 최근 FINAL 리포트 우선
finals = sorted([f for f in os.listdir(RESULT_DIR) if f.startswith("Comparison_Report_FINAL_") and f.endswith(".xlsx")])
if finals:
    p = os.path.join(RESULT_DIR, finals[-1])
else:
    reports = sorted([f for f in os.listdir(RESULT_DIR) if f.startswith("Comparison_Report_") and f.endswith(".xlsx")])
    p = os.path.join(RESULT_DIR, reports[-1])
print(f"Report: {p}\n")

xls = pd.ExcelFile(p)
print(f"Sheets: {xls.sheet_names}\n")

for sheet in ["요약", "모델간_일치율"]:
    if sheet in xls.sheet_names:
        df = pd.read_excel(p, sheet_name=sheet)
        print(f"=== Sheet: {sheet} ===")
        print(df.to_string(index=False))
        print()

# 담보별_비교 의 불일치 case 일부
if "담보별_비교" in xls.sheet_names:
    df = pd.read_excel(p, sheet_name="담보별_비교")
    print(f"=== Sheet: 담보별_비교 (총 {len(df)}건) ===")
    if "코드_일치여부" in df.columns:
        print("\n[일치여부 분포]")
        print(df["코드_일치여부"].value_counts().to_string())
        # 불일치 case 5건
        mismatch = df[df["코드_일치여부"] == "불일치"].head(5)
        if not mismatch.empty:
            print("\n[불일치 샘플 5건 (Claude 추출 vs GPT-OSS 추출)]")
            cols = ["담보명_출력물명칭", "세부담보템플릿명", "진단코드_Claude", "진단코드_GPTOSS", "Source_Claude", "Source_GPTOSS"]
            cols = [c for c in cols if c in mismatch.columns]
            for _, row in mismatch.iterrows():
                print(f"\n  담보: {row.get('담보명_출력물명칭', '')[:40]}")
                print(f"  템플릿: {row.get('세부담보템플릿명', '')[:40]}")
                print(f"  Claude  : {row.get('진단코드_Claude', ''):<10} ({row.get('Source_Claude', '')})")
                print(f"  GPT-OSS : {row.get('진단코드_GPTOSS', ''):<10} ({row.get('Source_GPTOSS', '')})")
