"""
MappingCheck Module - Python Port
Contains logic for checking coverage code mappings.
"""
from typing import List, Any, Dict, Optional
from .public_functions import find_row_in_array

class MappingChecker:
    def __init__(self, config_loader):
        self.config = config_loader
        self.varArray_담보매핑 = []
        
    def run_mapping_check(self, log_callback=None):
        """
        Mirrors VBA Mapping_Check subroutine.
        Checks and maps coverage codes from PGM to the mapping table.
        """
        if log_callback:
            log_callback("Starting Mapping Check...")
        
        try:
            # Read Loop Start/End
            loop_start = int(self.config.get_range_value("출력시작") or 0)
            loop_end = int(self.config.get_range_value("출력종료") or 0)
            
            if log_callback:
                log_callback(f"Processing range: {loop_start} to {loop_end}")
            
            # Get reference ranges
            ref_point = self.config.get_range_object("Ref_Point")
            
            # Get mapping sheet data
            mapping_sheet = self.config.wb.Sheets("담보매핑")
            
            # Turn off AutoFilter if on
            if mapping_sheet.AutoFilterMode:
                mapping_sheet.AutoFilterMode = False
            
            ref_대표담보코드 = mapping_sheet.Range("Ref_대표담보코드")
            ref_담보매핑결과 = self.config.get_range_object("Ref_담보매핑결과")
            
            # Calculate max row and column for mapping table
            max_row = mapping_sheet.Cells(mapping_sheet.Rows.Count, 1).End(-4162).Row - ref_대표담보코드.Row + 1  # xlUp = -4162
            max_col = ref_대표담보코드.End(-4161).Column - ref_대표담보코드.Column + 1  # xlToRight = -4161
            
            # Load mapping array
            self.varArray_담보매핑 = ref_대표담보코드.Resize(max_row, max_col).Value
            
            if log_callback:
                log_callback(f"Loaded mapping table: {max_row} rows x {max_col} cols")
            
            # Main Loop
            for loop_point in range(loop_start, loop_end + 1):
                dambo_code = ref_point.Offset(loop_point, 1).Value
                특별약관명 = str(ref_point.Offset(loop_point, 2).Value or "").strip()
                
                # 새 CSV 컬럼 구조: 대표담보코드(0), 대표담보명(약관)(1), 담보코드(2), 담보명(3), 구분(4)
                # Find in mapping array (column 3 = 담보코드, right 7 chars)
                search_key = str(dambo_code)[-7:] if dambo_code else ""
                num_row = self._find_row_in_array(3, search_key)  # 담보코드 컬럼 (1-indexed: 3)
                
                if num_row == -999:
                    ref_담보매핑결과.Offset(loop_point + 1, 0).Value = "찾기에러"
                    ref_담보매핑결과.Offset(loop_point + 1, 1).Value = ""
                else:
                    # 인덱스: 0=대표담보코드, 4=구분
                    dambo_category = str(self.varArray_담보매핑[num_row - 1][4]).strip() if len(self.varArray_담보매핑[num_row - 1]) > 4 else ""
                    대표담보코드 = str(self.varArray_담보매핑[num_row - 1][0]).strip() if self.varArray_담보매핑[num_row - 1] else ""
                    
                    ref_담보매핑결과.Offset(loop_point + 1, 0).Value = 대표담보코드
                    ref_담보매핑결과.Offset(loop_point + 1, 1).Value = dambo_category
                
                if loop_point % 10 == 0 and log_callback:
                    log_callback(f"Processed {loop_point}...")

            if log_callback:
                log_callback("담보매핑 체크완료!")
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error during mapping check: {e}")
            import traceback
            traceback.print_exc()
    
    def _find_row_in_array(self, col_index: int, search_value: str) -> int:
        """
        Finds a row in the mapping array by column value.
        Returns 1-based index or -999 if not found.
        """
        if not self.varArray_담보매핑:
            return -999
        
        for i, row in enumerate(self.varArray_담보매핑):
            if row and len(row) >= col_index:
                cell_value = str(row[col_index - 1]).strip() if row[col_index - 1] else ""
                if cell_value == search_value:
                    return i + 1
        return -999
    
    def run_mapping_check_temp(self, log_callback=None):
        """
        Mirrors VBA mapping_check_temp subroutine.
        Alternative mapping check using dictionary for duplicate detection.
        """
        if log_callback:
            log_callback("Starting Mapping Check (Temp)...")
        
        try:
            loop_start = int(self.config.get_range_value("출력시작") or 0)
            loop_end = int(self.config.get_range_value("출력종료") or 0)
            
            ref_point = self.config.get_range_object("Ref_Point")
            ref_담보매핑결과 = self.config.get_range_object("Ref_담보매핑결과")
            
            mapping_sheet = self.config.wb.Sheets("담보매핑")
            if mapping_sheet.AutoFilterMode:
                mapping_sheet.AutoFilterMode = False
            
            # Get the range of column C in mapping sheet
            last_row = mapping_sheet.Cells(mapping_sheet.Rows.Count, 3).End(-4162).Row
            
            for loop_point in range(loop_start, loop_end + 1):
                # Check if already filled
                if ref_담보매핑결과.Offset(loop_point + 1, 0).Value and ref_담보매핑결과.Offset(loop_point + 2, 0).Value:
                    continue
                
                dict_대표담보코드 = {}
                dambo_code = str(ref_point.Offset(loop_point, 1).Value or "").strip()
                dambo_category = ""
                
                # 새 CSV 컬럼 구조: 대표담보코드(1), 대표담보명(약관)(2), 담보코드(3), 담보명(4), 구분(5)
                # Search in mapping sheet column C (담보코드)
                for row_num in range(3, last_row + 1):
                    cell_value = str(mapping_sheet.Cells(row_num, 3).Value or "").strip()  # 담보코드
                    
                    if cell_value == dambo_code:
                        대표담보코드 = str(mapping_sheet.Cells(row_num, 1).Value or "")  # 대표담보코드
                        dambo_category = str(mapping_sheet.Cells(row_num, 5).Value or "")  # 구분
                        
                        if 대표담보코드 not in dict_대표담보코드:
                            dict_대표담보코드[대표담보코드] = dambo_code
                
                # Set results based on found codes
                if len(dict_대표담보코드) == 0:
                    ref_담보매핑결과.Offset(loop_point + 1, 0).Value = "찾기에러"
                    ref_담보매핑결과.Offset(loop_point + 1, 1).Value = ""
                elif len(dict_대표담보코드) == 1:
                    ref_담보매핑결과.Offset(loop_point + 1, 0).Value = list(dict_대표담보코드.keys())[0]
                    ref_담보매핑결과.Offset(loop_point + 1, 1).Value = dambo_category
                else:
                    ref_담보매핑결과.Offset(loop_point + 1, 1).Value = dambo_category
                    ref_담보매핑결과.Offset(loop_point + 1, 2).Value = ",".join(dict_대표담보코드.keys())
                
                if loop_point % 10 == 0 and log_callback:
                    log_callback(f"Processed {loop_point}...")

            if log_callback:
                log_callback("담보매핑 체크완료!")
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error during mapping check temp: {e}")
            import traceback
            traceback.print_exc()
