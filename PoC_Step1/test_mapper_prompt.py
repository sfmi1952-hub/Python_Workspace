
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import tempfile
import os
import sys

# Ensure logic package can be imported
sys.path.append(os.path.join(os.getcwd(), 'logic'))

from logic.mapper import BenefitMapper

class TestBenefitMapper(unittest.TestCase):
    def setUp(self):
        self.mock_api_key = "dummy_key"
        self.mapper = BenefitMapper(self.mock_api_key)
        self.mapper.client = MagicMock()
        self.mapper.client.get_model_name.return_value = "gemini-mock"
        
        # Create dummy excel
        self.df = pd.DataFrame({
            '담보명_출력물명칭': ['Cancer Diagnosis', 'Death Benefit'],
            '세부담보템플릿명': ['Cancer Template', 'General Death']
        })
        self.fd, self.excel_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(self.fd)
        self.df.to_excel(self.excel_path, index=False)
        
        # Dummy PDF
        self.fd2, self.pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(self.fd2)
        with open(self.pdf_path, 'wb') as f:
            f.write(b"%PDF-1.4 mock pdf content")

    def tearDown(self):
        os.remove(self.excel_path)
        os.remove(self.pdf_path)

    def test_prompt_construction(self):
        # Mock upload
        mock_file_ref = MagicMock()
        mock_file_ref.name = "mock_file_uri"
        self.mapper.client.upload_file.return_value = mock_file_ref
        
        # Mock generation response
        mock_response = MagicMock()
        mock_response.text = '[]' # Return empty json to avoid parsing error
        self.mapper.client.model.generate_content.return_value = mock_response

        # Run process
        self.mapper.process(self.pdf_path, self.excel_path, ref_files=[])
        
        # Verify call args to generate_content
        # We expect 2 calls: one for rules (skipped here if no refs), one for mapping.
        # But wait, logic says "If refs exist". We passed empty list.
        # So only 1 call for Phase 2.
        
        args = self.mapper.client.model.generate_content.call_args
        prompt_sent = args[0][0][0] # First arg, list, first element is prompt string
        
        print("\n--- GENERATED PROMPT SNIPPET ---")
        print(prompt_sent[:500])
        print("--------------------------------")

        self.assertIn("Cancer Template", prompt_sent)
        self.assertIn("General Death", prompt_sent)
        self.assertIn("**Task**: 제공된 '담보명'과 '세부담보템플릿명' 쌍을 확인하고", prompt_sent)
        self.assertIn("**근거 문장(Reference Sentence)**을 찾으세요", prompt_sent)

if __name__ == '__main__':
    unittest.main()
