"""Inspect Claude/GPT-OSS results for quick overview."""
import os, sys
import pandas as pd

RESULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "result")

for name in ["Result_Diagnosis_Code__Claude_Opus_4_7.xlsx", "Result_Diagnosis_Code__GPT_OSS.xlsx"]:
    p = os.path.join(RESULT_DIR, name)
    if not os.path.exists(p):
        print(f"-- {name} : NOT FOUND")
        continue
    df = pd.read_excel(p)
    code_col = "Inferred_Diagnosis_Code"
    filled = df[code_col].astype(str).str.strip().replace({"nan": ""}).astype(bool).sum()
    high = (df["Confidence"].astype(str).str.lower() == "high").sum()
    med = (df["Confidence"].astype(str).str.lower() == "medium").sum()
    low = (df["Confidence"].astype(str).str.lower() == "low").sum()
    print(f"\n=== {name} ===")
    print(f"  rows           : {len(df)}")
    print(f"  filled codes   : {filled} ({filled/len(df)*100:.1f}%)")
    print(f"  Confidence high/med/low : {high}/{med}/{low}")
    print(f"  Sources        : {df['Source'].value_counts().to_dict()}")
    print(f"  Top 5 codes    : {df[code_col].value_counts().head().to_dict()}")
    print(f"  Sample rows (first 5):")
    cols = ["담보명_출력물명칭", "세부담보템플릿명", code_col, "Confidence", "Source"]
    cols = [c for c in cols if c in df.columns]
    print(df[cols].head(5).to_string(index=False))
