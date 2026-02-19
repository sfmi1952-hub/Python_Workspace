
import os
import sys
import pandas as pd
from logic.code_mapper import DiagnosisMapper
from logic.gemini_core import GeminiCore

# Mock the generate_content to avoid using real API credits if we want, 
# BUT seeing as we want to verify the *prompt structure* and *logic flow* works, 
# we can mock the RESPONSE, but we should let the code run.
# However, to avoid 'api key not found' error if not set, let's assume user will run this.
# For this automated run, I will mock the GeminiCore.model.generate_content to return a valid JSON.

# Mocking for verification without actual API call (which might fail in this headless env if key is not env var)
from unittest.mock import MagicMock

def test_step2_logic():
    print("Testing DiagnosisMapper...")
    
    # 1. Setup Paths
    base_dir = r"c:\Users\Shin-Nyum\Desktop\Python_Workspace\PoC_Step2\data"
    target_pdf = os.path.join(base_dir, "new", "target_policy.pdf")
    target_excel = os.path.join(base_dir, "new", "target_benefit_list.xlsx")
    code_mapping = os.path.join(base_dir, "code", "diagnosis_mapping.xlsx")
    
    # 2. Initialize Mapper with Dummy Key
    mapper = DiagnosisMapper(api_key="DUMMY_KEY")
    
    # 3. Mock Model
    mock_response = MagicMock()
    mock_response.text = """
    [
        {
            "benefit_name": "일반암진단비",
            "template_name": "암(유사암제외)진단",
            "inferred_code": "C00-C97",
            "mapping_reason": "약관 제3조에 따라 C00-C97을 암으로 정의함."
        },
        {
            "benefit_name": "유사암진단비",
            "template_name": "유사암진단",
            "inferred_code": "D00-D09",
            "mapping_reason": "약관 제4조에서 기타피부암, 갑상선암 등을 유사암으로 분류."
        }
    ]
    """
    mapper.client.model = MagicMock()
    mapper.client.model.generate_content.return_value = mock_response
    
    # Mock Upload (don't actually upload)
    mapper.client.upload_file = MagicMock(return_value=MagicMock(name="FileReference"))
    
    # 4. Run Process
    result = mapper.process(
        target_pdf=target_pdf,
        target_excel=target_excel,
        code_mapping_excel=code_mapping,
        logger=print
    )
    
    # 5. Verify Output
    if "error" in result:
        print(f"FAILED: {result['error']}")
        sys.exit(1)
        
    print("Success! Result Preview:")
    print(result.get("preview"))
    
    # Check if "Inferred_Diagnosis_Code" is populated in result file
    df_out = pd.read_excel(result["file_path"])
    if "Inferred_Diagnosis_Code" not in df_out.columns:
        print("FAILED: Output Excel missing 'Inferred_Diagnosis_Code' column")
        sys.exit(1)
        
    print("Verification Passed: Output file generated with correct columns.")
    
if __name__ == "__main__":
    test_step2_logic()
