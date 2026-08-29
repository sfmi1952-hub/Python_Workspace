"""Check that PoC_Step6 input Excel matches answer schema."""
import pandas as pd

paths = {
    "Step6 input": r"C:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step6\data\new\무배당_삼성화재_건강보험_마이헬스_파트너(2508.12)_4종_일반형_SAMPLE.xlsx",
    "Step1 answer": r"C:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step1\data\new\무배당_삼성화재_건강보험_마이헬스_파트너(2508.12)_4종_일반형_SAMPLE.xlsx",
    "Claude result": r"C:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step6\data\result\Result_Diagnosis_Code__Claude_Opus_4_7.xlsx",
    "GPTOSS result": r"C:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step6\data\result\Result_Diagnosis_Code__GPT_OSS.xlsx",
}

for name, p in paths.items():
    df = pd.read_excel(p)
    print(f"=== {name} (rows={len(df)}) ===")
    print(f"  Columns: {list(df.columns)}")
    print()
