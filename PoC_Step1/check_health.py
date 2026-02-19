import sys
import os
import requests
import traceback

print("--- Checking Mapper Import ---")
try:
    from logic.mapper import BenefitMapper
    print("✅ logic.mapper.BenefitMapper imported successfully.")
except Exception as e:
    print(f"❌ Failed to import logic.mapper: {e}")
    traceback.print_exc()

print("\n--- Checking Server Health (Port 8001) ---")
try:
    resp = requests.get("http://127.0.0.1:8001/api/logs", timeout=2)
    if resp.status_code == 200:
        print("✅ Server is responding (200 OK).")
    else:
        print(f"⚠️ Server responded with status: {resp.status_code}")
        print(resp.text)
except Exception as e:
    print(f"❌ Failed to connect to server: {e}")
