"""Inspect the ground-truth Excel in PoC_Step1."""
import pandas as pd

ANSWER_PATH = r"C:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step1\data\new\무배당_삼성화재_건강보험_마이헬스_파트너(2508.12)_4종_일반형_SAMPLE.xlsx"

xls = pd.ExcelFile(ANSWER_PATH)
print(f"Sheets: {xls.sheet_names}\n")

for sheet in xls.sheet_names:
    df = pd.read_excel(ANSWER_PATH, sheet_name=sheet)
    print(f"=== Sheet: {sheet} (rows={len(df)}, cols={len(df.columns)}) ===")
    print(f"Columns: {list(df.columns)}")
    print(df.head(8).to_string(index=False))
    print()
