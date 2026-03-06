"""Quick check of environment before running pipeline."""
import sys
import os
import glob

sys.stdout.reconfigure(encoding="utf-8")

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

print("=== Input Files ===")
for d in ["data/input/docx", "data/input/pdf", "data/input/ground_truth"]:
    files = glob.glob(os.path.join(d, "*"))
    for f in files:
        size = os.path.getsize(f)
        print(f"  [{d}] {os.path.basename(f)} ({size:,} bytes)")

print()
print("=== .env Config ===")
print(f"  OPENAI_API_KEY: {'SET' if os.getenv('OPENAI_API_KEY') else 'MISSING'}")
model = os.getenv("OPENAI_MODEL", "not set, will use default")
print(f"  OPENAI_MODEL: {model}")
print(f"  ADOBE_CLIENT_ID: {'SET' if os.getenv('ADOBE_CLIENT_ID') else 'MISSING'}")
print(f"  ADOBE_CLIENT_SECRET: {'SET' if os.getenv('ADOBE_CLIENT_SECRET') else 'MISSING'}")

print()
print("=== Cached Markdown ===")
for p in ["data/output/method1_baseline/converted.md", "data/output/method2_adobe/converted.md"]:
    if os.path.exists(p):
        size = os.path.getsize(p)
        print(f"  {p}: EXISTS ({size:,} bytes)")
    else:
        print(f"  {p}: NOT FOUND")

print()
print("=== Ground Truth Stats ===")
import pandas as pd
gt_files = glob.glob("data/input/ground_truth/*.xlsx")
for f in gt_files:
    df = pd.read_excel(f, engine="openpyxl")
    unique_cov = df[["상품코드", "담보PMID", "담보명"]].drop_duplicates()
    print(f"  Total rows: {len(df)}")
    print(f"  Unique coverages: {len(unique_cov)}")
    print(f"  Columns: {list(df.columns)[:12]}")
