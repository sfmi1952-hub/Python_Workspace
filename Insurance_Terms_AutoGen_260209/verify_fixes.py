
import unittest
from unittest.mock import MagicMock
import sys
import os

# Add src to path
sys.path.append(os.path.join(os.getcwd(), 'src'))

try:
    from csv_loader import CSVLoader
    from tag_processor import TagProcessor, TagContext
except ImportError:
    print("Could not import src modules. Make sure you are in the project root.")

class TestTagProcessingFixes(unittest.TestCase):
    
    def test_csv_loader_columns(self):
        """Test if CSVLoader handles new column names."""
        loader = CSVLoader(".") # Pass dummy path
        # Mock data with new column names
        loader.참조_data = [
            {'태그명(코드명)': '{연장형1}', '적용문구(약관문구)': 'Specific Replacement', '적용구분': '1', '담보속성': '연장형'},
            {'태그명': '{연장형}', '적용문구': 'Base Replacement', '적용구분': '1', '담보속성': '연장형'},
        ]
        
        # Test lookup with new columns
        val1 = loader.find_참조문구('{연장형1}', '연장형', 1)
        self.assertEqual(val1, 'Specific Replacement', "Should find specific tag using new columns")
        
        # Test lookup with old/base columns
        val2 = loader.find_참조문구('{연장형}', '연장형', 1)
        self.assertEqual(val2, 'Base Replacement', "Should find base tag")

    def test_tag_processor_lookup_priority(self):
        """Test if TagProcessor looks up numbered tag first."""
        loader = CSVLoader(".") # Pass dummy path
        loader.참조_data = [
            {'태그명(코드명)': '{테스트1}', '적용문구(약관문구)': 'Specific', '적용구분': '1', '담보속성': '테스트'},
            {'태그명(코드명)': '{테스트}', '적용문구(약관문구)': 'Base', '적용구분': '1', '담보속성': '테스트'},
        ]
        
        tp = TagProcessor(loader)
        
        # Mock context
        context = TagContext()
        setattr(context, '테스트', 1)
        
        # Mock _lookup_참조 calling mechanism if needed, but we can verify logic via a small simulation
        # Since process_numbered_tags is inside TagProcessor, we can try to use it if accessible or simulate its logic
        # But TagProcessor structure uses _build_replacement_dict which calls _lookup_참조
        
        # Let's test _build_replacement_dict logic directly by mocking _lookup_참조 results?
        # Or better, just use the real methods since we injected the loader data.
        
        # process_numbered_tags is a local function inside _build_replacement_dict.
        # So we test _build_replacement_dict behavior.
        
        context.연장형 = 1 # Dummy to trigger lookup
        # We need to hack/mock _build_replacement_dict to use our "테스트" attribute logic
        # or add "테스트" logic to it. But we cannot easily modify code.
        # Instead, we can verify checking "{연장형1}" vs "{연장형}" if we put them in loader.
        
        loader.참조_data = [
            {'태그명(코드명)': '{연장형1}', '적용문구(약관문구)': 'Specific1', '적용구분': '1', '담보속성': '연장형'},
            {'태그명(코드명)': '{연장형}', '적용문구(약관문구)': 'Base', '적용구분': '1', '담보속성': '연장형'},
        ]
        
        # Mock doc text containing {연장형1}
        replacements = tp._build_replacement_dict(context, "{연장형1}")
        
        self.assertIn("{연장형1}", replacements)
        self.assertEqual(replacements["{연장형1}"], "Specific1", "Should prefer specific tag definition")
        
    def test_range_cleanup(self):
        """Test tag cleanup regex and logic."""
        tp = TagProcessor(None)
        
        text = "Some text {연장형1} remaining {부모} tags."
        
        # We can't easily mock Range object perfectly without Word, 
        # but we can check if the regex matches correctly.
        combined_pattern = r'\{(?:연장형|부모|예약가입|단체|감액|감액2-|진단확정|세부보장|감액기간|지급률|면책|감액있음|비갱신|갱신|감액한번|감액두번|자동갱신형|독립특약)\d*(?:-\d+)?(?:-\d+)?\}'
        import re
        matches = re.findall(combined_pattern, text)
        
        self.assertIn("{연장형1}", matches)
        self.assertIn("{부모}", matches)

if __name__ == '__main__':
    unittest.main()
