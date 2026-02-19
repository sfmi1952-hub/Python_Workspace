"""
MainSheet_Subfunction Module - Python Port
Contains file utilities and filename matching functions.
"""
import os
import datetime
from typing import List, Tuple, Optional

def get_filenames(folder_path: str) -> List[Tuple[str, datetime.datetime]]:
    """
    Mirrors VBA GetFilenames function.
    Returns a list of tuples: (filename, last_modified_datetime)
    Excludes files starting with '~' (temp files).
    """
    result = []
    if not os.path.exists(folder_path):
        print(f"Error: Folder not found: {folder_path}")
        return []
        
    try:
        with os.scandir(folder_path) as entries:
            for entry in entries:
                if entry.is_file() and not entry.name.startswith('~'):
                    stats = entry.stat()
                    dt = datetime.datetime.fromtimestamp(stats.st_mtime)
                    result.append((entry.name, dt))
    except Exception as e:
        print(f"Error accessing folder {folder_path}: {e}")
        return []
        
    return result

def find_most_recent_file(file_list: List[Tuple[str, datetime.datetime]], 
                          search_term: str) -> Tuple[str, Optional[datetime.datetime]]:
    """
    Mirrors VBA TestGetFileNames / GetFileNames_base logic.
    Finds the most recently modified file containing the search term.
    Special handling for "상해" and "질병" to exclude "상해질병".
    Returns (filename, modified_date) or ("-", None) if not found.
    """
    most_recent_file = "-"
    most_recent_date = datetime.datetime(1900, 1, 1)
    
    for filename, file_date in file_list:
        if not filename:
            continue
            
        # Case-insensitive search
        if search_term.lower() in filename.lower():
            # Special handling for 상해/질병
            if search_term in ["상해", "질병"]:
                if "상해질병" in filename:
                    continue  # Skip combined term
            
            if file_date > most_recent_date:
                most_recent_date = file_date
                most_recent_file = filename
    
    if most_recent_file == "-":
        return ("-", None)
    return (most_recent_file, most_recent_date)

def get_independent_filenames(folder_path: str) -> List[dict]:
    """
    Mirrors VBA GetIndependFilenames function.
    Parses independent rider files and groups them by group key.
    Returns list of dicts with groupKey, normal_file, simple_file.
    """
    file_list = get_filenames(folder_path)
    result_dict = {}
    
    for filename, file_date in file_list:
        # Extract group key (number before first underscore)
        if "_" in filename:
            try:
                group_key = int(filename.split("_")[0].strip())
            except ValueError:
                group_key = -1
        else:
            group_key = -1
        
        # Determine category (간편 vs 일반)
        if "_간편_" in filename or "._간편_" in filename:
            category = "간편"
        else:
            category = "일반"
        
        # Initialize group if not exists
        if group_key not in result_dict:
            result_dict[group_key] = {
                "groupKey": group_key,
                "normal_file": "",
                "normal_date": datetime.datetime(2000, 1, 1),
                "simple_file": "",
                "simple_date": datetime.datetime(2000, 1, 1)
            }
        
        # Update based on category and date
        if category == "일반":
            if file_date > result_dict[group_key]["normal_date"]:
                result_dict[group_key]["normal_file"] = filename
                result_dict[group_key]["normal_date"] = file_date
        else:  # 간편
            if file_date > result_dict[group_key]["simple_date"]:
                result_dict[group_key]["simple_file"] = filename
                result_dict[group_key]["simple_date"] = file_date
    
    return list(result_dict.values())

class FilenameManager:
    """
    Manages file operations for the terms generation system.
    """
    def __init__(self, config_loader):
        self.config = config_loader
    
    def load_rider_filenames(self, log_callback=None):
        """
        Mirrors VBA TestGetFileNames subroutine.
        Finds most recent rider files and updates the Excel sheet.
        """
        try:
            folder_path = self.config.get_range_value("Ref_경로지정")
            if folder_path:
                folder_path = self.config.get_range_object("Ref_경로지정").Offset(1, 1).Value
            
            file_list = get_filenames(folder_path)
            
            # Get search range
            rng_search = self.config.get_range_object("Ref_종속특약")
            if not rng_search:
                if log_callback:
                    log_callback("Error: Ref_종속특약 range not found")
                return
            
            # Calculate max rows
            max_row = rng_search.End(-4121).Row - rng_search.Row + 1  # xlDown = -4121
            
            for i in range(max_row):
                search_term = str(rng_search.Offset(i, 0).Value or "").strip()
                if not search_term:
                    continue
                
                most_recent_file, _ = find_most_recent_file(file_list, search_term)
                rng_search.Offset(i, 1).Value = most_recent_file
                
                if log_callback:
                    log_callback(f"Found: {search_term} -> {most_recent_file}")
            
            if log_callback:
                log_callback("종속특약 약관 파일명 불러오기 완료!")
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error in load_rider_filenames: {e}")
    
    def load_base_filenames(self, log_callback=None):
        """
        Mirrors VBA GetFileNames_base subroutine.
        """
        try:
            folder_path = self.config.get_range_object("Ref_경로").Offset(0, 1).Value
            file_list = get_filenames(folder_path)
            
            rng_search = self.config.get_range_object("Ref_Base파일명")
            if not rng_search:
                if log_callback:
                    log_callback("Error: Ref_Base파일명 range not found")
                return
            
            max_row = rng_search.End(-4121).Row - rng_search.Row + 1
            
            for i in range(max_row):
                search_term = str(rng_search.Offset(i, 0).Value or "").strip()
                if not search_term:
                    continue
                
                most_recent_file, _ = find_most_recent_file(file_list, search_term)
                rng_search.Offset(i, 1).Value = most_recent_file
                
                if log_callback:
                    log_callback(f"Found: {search_term} -> {most_recent_file}")
            
            if log_callback:
                log_callback("Base파일명 불러오기 완료!")
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error in load_base_filenames: {e}")
