
import unittest
from unittest.mock import MagicMock
import sys
import os
import numpy as np


# Add root to path so we can import src as package
sys.path.append(os.getcwd())

# Mock word_utils to avoid dependency issues
sys.modules['src.word_utils'] = MagicMock()
sys.modules['src.word_utils'].WordHandler = MagicMock()
sys.modules['src.word_utils'].wdCollapseEnd = 0
sys.modules['src.word_utils'].wdCollapseStart = 1
sys.modules['src.word_utils'].wdSectionBreakOddPage = 2

try:
    from src.print_dambo import PrintDambo, DamboAttributes
    from src.data_loader import DataLoader
except ImportError as e:
    print(f"Could not import src modules: {e}")
    # Fallback for direct import if package import fails
    sys.path.append(os.path.join(os.getcwd(), 'src'))
    try:
        from print_dambo import PrintDambo, DamboAttributes
        from data_loader import DataLoader
    except ImportError:
         print("Failed validation import completely.")

class TestSemboFix(unittest.TestCase):
    
    def test_sembo_population(self):
        """Test if 세부보장명_list is populated from PGM codes."""
        
        # 1. Setup Mock DataLoader
        data_loader = DataLoader()
        data_loader.product_code = "P123"
        data_loader.독립특약 = 0
        
        # Mock arrays
        # PGM Main: [None, DamboCode, ... ExpansionNumber at loc 0?] 
        # Actually loc_확장번호 is usually determined dynamically.
        # Let's check _read_pgm_loop logic.
        # It needs loc_확장번호.
        
        # Mock 담보매핑: [RepresentativeCode, RepName, Code, Name, ...]
        data_loader.arr_담보매핑 = np.array([
            ["R1", "Rep1", "SC001", "SubCoverage1", "Type"],
            ["R1", "Rep1", "SC002", "SubCoverage2", "Type"],
        ], dtype=object)
        
        # Mock PGM Main
        # We need to set indices.
        # Let's say loc_확장번호 is 2.
        # Row 10: [None, "D123", "01", ...]
        data_loader.arr_pgm_main = np.array([
            ["H", "Header", "Header"],
            ["D", "D123", "01"], # m_point row
        ], dtype=object)
        
        # Mock 보장구조
        # Key: "P123_01" (ProductCode_ExpansionNumber)
        # Row: ["P123_01", ..., ..., Code]
        # loc_세부담보순번, loc_세부담보코드 needed.
        data_loader.arr_보장구조 = np.array([
            ["P123_01", 1, "SC001"], # Row 1
            ["P123_01", 2, "SC002"], # Row 2
        ], dtype=object)
        
        # Mock 보장배수 (needed to avoid errors)
        data_loader.arr_보장배수 = np.array([["Key", "0", "0", "0"]], dtype=object)

        # 2. Setup PrintDambo
        pd = PrintDambo(data_loader)
        
        # Set column locations manually
        pd.loc_확장번호 = 2
        pd.loc_세부담보순번 = 1
        pd.loc_세부담보코드 = 2
        pd.loc_보장배수 = 0 # Dummy
        pd.loc_면책기간 = 99
        pd.loc_감액기간 = 99
        pd.loc_지급률 = 99
        
        # Mock needed methods
        pd._read_pgm_보기납기 = MagicMock()
        
        # 3. Test execution
        dambo_att = DamboAttributes()
        dambo_att.담보코드 = "D123"
        dambo_att.세부보장명_list = [] # Initially empty
        
        # Execute _read_pgm_loop
        # loop index 0
        
        # DEBUG: Check iteration manually
        print(f"DEBUG: arr_pgm_main len: {len(data_loader.arr_pgm_main)}")
        for i, row in enumerate(data_loader.arr_pgm_main):
            val = str(row[1] if len(row) > 1 else "").strip()
            print(f"DEBUG: Row {i} Col 1: '{val}' == 'D123'? {val == 'D123'}")
        
        pd._read_pgm_loop("D123", dambo_att, 0)
        
        # 4. Assertions
        print(f"m_point: {pd.m_point}")
        print(f"Key expected: P123_01")
        print(f"세부담보코드List: {pd.세부담보코드List}")
        print(f"Result 세부보장명_list: {dambo_att.세부보장명_list}")
        
        self.assertEqual(len(dambo_att.세부보장명_list), 2)
        self.assertEqual(dambo_att.세부보장명_list[0], "SubCoverage1")
        self.assertEqual(dambo_att.세부보장명_list[1], "SubCoverage2")

if __name__ == '__main__':
    unittest.main()
