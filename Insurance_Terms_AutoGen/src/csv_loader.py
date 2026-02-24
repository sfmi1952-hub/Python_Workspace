"""
CSV Loader Module
Loads static CSV files for mapping tables.
"""
import os
import csv
from typing import List, Dict, Any


class CSVLoader:
    """Loads and manages CSV mapping files."""
    
    def __init__(self, data_path: str):
        self.data_path = data_path
        self.담보매핑_data = []
        self.참조_data = []
    
    def load_all(self, log_callback=None) -> bool:
        """
        Loads all CSV files from the data directory.
        Returns True if successful.
        """
        try:
            self.load_담보매핑(log_callback)
            self.load_참조(log_callback)
            return True
        except Exception as e:
            if log_callback:
                log_callback(f"❌ CSV 로드 오류: {e}")
            return False
    
    def load_담보매핑(self, log_callback=None) -> List[Dict[str, Any]]:
        """
        Loads the 담보매핑.csv file.
        Returns list of dictionaries with mapping data.
        """
        file_path = os.path.join(self.data_path, "담보매핑.csv")

        if not os.path.exists(file_path):
            if log_callback:
                log_callback(f"⚠️ 담보매핑.csv 파일이 없습니다: {file_path}")
            return []

        self.담보매핑_data = self._load_csv(file_path, log_callback)

        # Build dictionary indexes for O(1) lookup
        self._build_담보매핑_index()

        if log_callback:
            log_callback(f"✅ 담보매핑.csv 로드 완료: {len(self.담보매핑_data)}건")

        return self.담보매핑_data
    
    def load_참조(self, log_callback=None) -> List[Dict[str, Any]]:
        """
        Loads the 참조.csv file.
        Returns list of dictionaries with reference data.
        """
        file_path = os.path.join(self.data_path, "참조.csv")
        
        if not os.path.exists(file_path):
            if log_callback:
                log_callback(f"⚠️ 참조.csv 파일이 없습니다: {file_path}")
            return []
        
        self.참조_data = self._load_csv(file_path, log_callback)
        
        # Build index for fast lookup (O(1) instead of O(N))
        self._build_참조_index()
        
        if log_callback:
            log_callback(f"✅ 참조.csv 로드 완료: {len(self.참조_data)}건")
        
        return self.참조_data
    
    def _load_csv(self, file_path: str, log_callback=None) -> List[Dict[str, Any]]:
        """
        Generic CSV loader that returns list of dictionaries.
        Handles UTF-8 with BOM and various encodings.
        Supports both comma and tab delimiters.
        """
        data = []
        
        # Try different encodings (including UTF-16 for Excel exports)
        encodings = ['utf-8-sig', 'utf-8', 'utf-16', 'utf-16-le', 'cp949', 'euc-kr']
        delimiters = ['\t', ',']  # Try tab first, then comma
        
        for encoding in encodings:
            for delimiter in delimiters:
                try:
                    with open(file_path, 'r', encoding=encoding, newline='') as f:
                        reader = csv.DictReader(f, delimiter=delimiter)
                        data = [row for row in reader]
                        # Check if data was parsed correctly (has more than 1 column)
                        if data and len(data[0]) > 1:
                            break
                        data = []  # Reset if not parsed correctly
                except UnicodeDecodeError:
                    continue
                except Exception as e:
                    if log_callback:
                        log_callback(f"⚠️ CSV 읽기 오류 ({encoding}, {repr(delimiter)}): {e}")
                    continue
            if data:
                break
        
        return data
    
    def _build_담보매핑_index(self):
        """
        Build dictionary indexes for fast 담보매핑 lookup.
        Indexes by exact 담보코드 and last 7 characters for O(1) access.
        """
        self._담보매핑_exact = {}   # {담보코드: row}
        self._담보매핑_suffix7 = {} # {last_7_chars: row}

        for row in self.담보매핑_data:
            row_담보코드 = row.get('담보코드', '').strip()
            if not row_담보코드:
                continue
            # Exact match index
            if row_담보코드 not in self._담보매핑_exact:
                self._담보매핑_exact[row_담보코드] = row
            # Last 7 chars index
            if len(row_담보코드) >= 7:
                suffix = row_담보코드[-7:]
                if suffix not in self._담보매핑_suffix7:
                    self._담보매핑_suffix7[suffix] = row

    def find_대표담보코드(self, 담보코드: str) -> Dict[str, Any]:
        """
        Finds the 대표담보코드 for a given 담보코드.
        Uses pre-built dictionary index for O(1) lookup.
        """
        key = 담보코드.strip()

        # 1. Exact match (O(1))
        row = self._담보매핑_exact.get(key)
        if row:
            return self._normalize_row(row)

        # 2. Last 7 characters match (O(1))
        if len(key) >= 7:
            row = self._담보매핑_suffix7.get(key[-7:])
            if row:
                return self._normalize_row(row)

        return {}
    
    def _normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes column names for compatibility.
        Maps new column names to old names used in code.
        """
        normalized = dict(row)
        # Map new column names to old names for backward compatibility
        if '대표담보명(약관)' in row and '대표담보명' not in row:
            normalized['대표담보명'] = row['대표담보명(약관)']
        if '구분' in row and '구분값' not in row:
            normalized['구분값'] = row['구분']
        return normalized
    
    def _build_참조_index(self):
        """
        Build dictionary indexes for fast 참조 lookup.
        Structure: {코드명: [(담보속성, 적용구분, 약관문구), ...]}
        """
        self._참조_index = {}  # {코드명: [(담보속성, 적용구분_str, 약관문구), ...]}
        self._참조_담보속성_index = {}  # {담보속성: [row, ...]}

        for row in self.참조_data:
            # Get 코드명 (try multiple column name variants)
            row_코드명 = (row.get('코드명', '') or row.get('태그명', '') or row.get('태그명(코드명)', '')).strip()
            row_담보속성 = row.get('담보속성', '').strip()
            row_적용구분 = row.get('적용구분', '').strip()
            약관문구 = row.get('약관문구', '') or row.get('적용문구', '') or row.get('적용문구(약관문구)', '')

            if row_코드명:
                if row_코드명 not in self._참조_index:
                    self._참조_index[row_코드명] = []
                self._참조_index[row_코드명].append((row_담보속성, row_적용구분, 약관문구))

            # 담보속성 인덱스
            if row_담보속성:
                if row_담보속성 not in self._참조_담보속성_index:
                    self._참조_담보속성_index[row_담보속성] = []
                self._참조_담보속성_index[row_담보속성].append(row)
    
    def find_참조문구(self, 코드명: str, 담보속성: str = None, 적용구분: int = None) -> str:
        """
        Finds the 약관문구 for a given 코드명.
        Uses pre-built dictionary index for O(1) lookup.
        
        Args:
            코드명: Code name to search for (e.g., '{단체}', '{감액1}')
            담보속성: Optional filter by coverage attribute
            적용구분: Optional filter by application type (0 or 1)
        """
        entries = self._참조_index.get(코드명.strip(), [])
        if not entries:
            return ""
        
        for row_담보속성, row_적용구분, 약관문구 in entries:
            # Filter by 담보속성
            if 담보속성 is not None:
                if row_담보속성 != 담보속성.strip():
                    continue
            
            # 적용구분이 빈 값 → 태그 삭제 (빈 문자열 반환)
            if not row_적용구분:
                return ""
            
            # Filter by 적용구분
            if 적용구분 is not None:
                try:
                    if int(row_적용구분) != int(적용구분):
                        continue
                except (ValueError, TypeError):
                    continue
            
            return 약관문구
        return ""
    
    def get_담보매핑_as_array(self) -> List[List[Any]]:
        """
        Returns 담보매핑 data as 2D array for compatibility with VBA-style logic.
        """
        if not self.담보매핑_data:
            return []
        
        # Get headers from first row
        headers = list(self.담보매핑_data[0].keys())
        
        # Create 2D array
        result = [headers]  # Header row
        for row in self.담보매핑_data:
            result.append([row.get(h, '') for h in headers])
        
        return result
    
    def get_참조_as_dict(self) -> Dict[str, str]:
        """
        Returns 참조 data as a simple code->문구 dictionary.
        New structure: 코드명 -> 약관문구
        """
        result = {}
        for row in self.참조_data:
            # Try new column names first, then old names
            key = row.get('코드명', '') or row.get('태그명', '') or row.get('태그명(코드명)', '')
            value = row.get('약관문구', '') or row.get('적용문구', '') or row.get('적용문구(약관문구)', '')
            if key:
                result[key] = value
        return result
    
    def find_참조_by_담보속성(self, 담보속성: str) -> List[Dict[str, Any]]:
        """
        Returns all 참조 rows matching the given 담보속성.
        Uses pre-built index for O(1) lookup.
        """
        return self._참조_담보속성_index.get(담보속성.strip(), [])
