
import sys
import os

# Ensure we can import from current directory
sys.path.append(os.getcwd())

try:
    print("Attempting to import DiagnosisMapper...")
    from logic.code_mapper import DiagnosisMapper
    print("Import successful (OpenAI GPT version).")
    
    print("Attempting to initialize DiagnosisMapper with dummy key...")
    mapper = DiagnosisMapper("dummy_key")
    print("Initialization successful.")

except Exception as e:
    print(f"CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
