
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import tempfile
import os
import sys

# Ensure logic package can be imported
sys.path.append(os.path.join(os.getcwd(), 'logic'))

from logic.mapper import BenefitMapper

class TestBenefitMapperPairs(unittest.TestCase):
    def setUp(self):
        self.mock_api_key = "dummy_key"
        self.mapper = BenefitMapper(self.mock_api_key)
        self.mapper.client = MagicMock()
        self.mapper.client.get_model_name.return_value = "gemini-mock"
        
        # Create dummy excel with 25 items to trigger 2 batches (Batch Size 20)
        items = []
        for i in range(25):
            items.append({'담보명_출력물명칭': f'Benefit {i}', '세부담보템플릿명': f'Template {i}'})
            
        self.df = pd.DataFrame(items)
        self.fd, self.excel_path = tempfile.mkstemp(suffix=".xlsx")
        os.close(self.fd)
        self.df.to_excel(self.excel_path, index=False)
        
        # Dummy Target PDF
        self.fd2, self.pdf_path = tempfile.mkstemp(suffix=".pdf")
        os.close(self.fd2)
        with open(self.pdf_path, 'wb') as f:
            f.write(b"%PDF-1.4 target pdf")

        # Create dummy references (2 Groups)
        # We need IDENTICAL basenames for grouping to work (RefA.pdf, RefA.xlsx)
        self.test_dir = tempfile.mkdtemp()
        self.refs = []
        
        # Group 1: RefA
        p1 = os.path.join(self.test_dir, "RefA.pdf")
        with open(p1, 'wb') as f: f.write(b"dummy pdf")
        self.refs.append(p1)
        
        p2 = os.path.join(self.test_dir, "RefA.xlsx")
        with open(p2, 'wb') as f: f.write(b"dummy xlsx")
        self.refs.append(p2)
        
        # Group 2: RefB
        p3 = os.path.join(self.test_dir, "RefB.pdf")
        with open(p3, 'wb') as f: f.write(b"dummy pdf")
        self.refs.append(p3)

    def tearDown(self):
        os.remove(self.excel_path)
        os.remove(self.pdf_path)
        if os.path.exists(self.test_dir):
            import shutil
            shutil.rmtree(self.test_dir)

    def test_grouping_logic(self):
        groups = self.mapper._group_files_by_pair(self.refs)
        print(f"\nGroups Found: {groups.keys()}")
        
        # Check if RefA is grouped
        keys = list(groups.keys())
        self.assertTrue(any("RefA" in k for k in keys))
        self.assertTrue(any("RefB" in k for k in keys))
        
        # Check count
        ref_a_key = next(k for k in keys if "RefA" in k)
        self.assertEqual(len(groups[ref_a_key]), 2) # pdf + xlsx

    def test_process_multiple_groups(self):
        # Mock upload
        mock_file_ref = MagicMock()
        mock_file_ref.name = "mock_file_uri"
        self.mapper.client.upload_file.return_value = mock_file_ref
        
        # Mock response behaviors
        def side_effect_generate(contents):
            # Check context to see if it's Phase 1 or Phase 2
            input_text = str(contents)
            response = MagicMock()
            if "규칙" in input_text and "가이드라인" in input_text:
                # This is Phase 1
                response.text = "RULE_EXTRACTED_FROM_GROUP"
            else:
                # This is Phase 2 (Application) - Returns JSON list
                # We need to return dummy JSON matching the input size or generic
                # Since we don't parse input strictly in mock, just return empty list or dummy
                response.text = '[{"benefit_name": "Test", "input_template_name": "TestTmpl"}]'
            return response

        self.mapper.client.model.generate_content.side_effect = side_effect_generate

        # Run process
        self.mapper.process(self.pdf_path, self.excel_path, ref_files=self.refs)

        # Verification
        # Expect calls:
        # 1. Uploads: RefA output (2 files) is grouped, RefB output (1 file) is grouped, Target PDF (1)
        # 2. Generate Content: 
        #    - Phase 1 (Group A) -> 1 call
        #    - Phase 1 (Group B) -> 1 call
        #    - Phase 2 (Batch 1: items 0-19) -> 1 call
        #    - Phase 2 (Batch 2: items 20-24) -> 1 call
        #    Total = 4 calls
        
        call_count = self.mapper.client.model.generate_content.call_count
        print(f"\nGenerate Content Call Count: {call_count}")
        self.assertEqual(call_count, 4) 

        # Verify Final Prompt contains aggregated rules
        final_call_args = self.mapper.client.model.generate_content.call_args_list[-1]
        final_prompt = final_call_args[0][0][0]
        
        self.assertIn("RULE_EXTRACTED_FROM_GROUP", final_prompt)
        print("\n--- FINAL PROMPT CONTAINS AGGREGATED RULES ---")

if __name__ == '__main__':
    unittest.main()
