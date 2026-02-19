"""
PublicFunction Module - Python Port
Contains shared utility functions used across all modules.
"""
import re
from typing import List, Any, Optional, Tuple

def find_row_in_array(arr: List[List[Any]], col_index: int, search_value: str) -> int:
    """
    Mirrors VBA FindRowinArray function.
    Searches for a value in a specific column of a 2D array.
    Returns the row index (1-based like VBA) or -999 if not found.
    """
    if not arr:
        return -999
    
    for i, row in enumerate(arr):
        if len(row) > col_index - 1:  # col_index is 1-based
            if str(row[col_index - 1]).strip() == str(search_value).strip():
                return i + 1  # Return 1-based index
    return -999

def get_cross_ref_items(doc) -> List[str]:
    """
    Mirrors VBA GetCrossRefItems function.
    Returns a list of numbered paragraph items for cross-reference.
    """
    items = []
    try:
        for para in doc.ListParagraphs:
            items.append(para.Range.Text)
    except Exception as e:
        print(f"Error getting cross ref items: {e}")
    return items

def extr_betw_text(text: str, start_marker: str, end_marker: str) -> str:
    """
    Mirrors VBA ExtrBetwText function.
    Extracts text between two markers.
    """
    try:
        start_idx = text.find(start_marker)
        if start_idx == -1:
            return ""
        start_idx += len(start_marker)
        
        end_idx = text.find(end_marker, start_idx)
        if end_idx == -1:
            return text[start_idx:]
        
        return text[start_idx:end_idx]
    except:
        return ""

def copy_array_subset(arr: List[List[Any]], lookup_key: Any) -> List[Any]:
    """
    Mirrors VBA CopyArraySubset function.
    Returns a row from the array matching the lookup key in the first column.
    """
    for row in arr:
        if row and row[0] == lookup_key:
            return row
    return []

def clean_text(text: str) -> str:
    """
    Cleans text by removing special characters.
    Mirrors the VBA cleanText logic.
    """
    chars_to_remove = [
        chr(14), chr(13), chr(10), chr(160), chr(9), chr(12)
    ]
    result = text
    for char in chars_to_remove:
        result = result.replace(char, "")
    return result.strip()

def parse_comment_codes(comment_text: str) -> List[str]:
    """
    Parses comma-separated codes from a comment text.
    """
    return [code.strip() for code in comment_text.split(",")]

def get_num_mark_array() -> List[str]:
    """
    Returns circled number characters ① ② ③ etc.
    """
    return ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", 
            "⑪", "⑫", "⑬", "⑭", "⑮"]

def format_date_korean(dt) -> str:
    """Format date in Korean style YYYYMMDD"""
    return dt.strftime("%Y%m%d")

def format_time_korean(dt) -> str:
    """Format time in Korean style HHMM"""
    return dt.strftime("%H%M")
