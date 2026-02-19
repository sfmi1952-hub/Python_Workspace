"""
ModAppendix Module - Python Port
Contains appendix revision logic for Word document processing.
"""
import win32com.client
import os
from typing import Optional, List, Dict, Any
from .word_utils import WordHandler, wdCollapseEnd, wdCollapseStart, wdSectionBreakOddPage
from .public_functions import clean_text, get_cross_ref_items

# Word Constants
wdNumberRelativeContext = 2
wdContentText = 1

class ModAppendix:
    def __init__(self, config_loader):
        self.config = config_loader
        self.word = WordHandler()
        
        # Document arrays
        self.source_doc_arr = []
        self.target_doc_arr = []
        
        # Location markers
        self.loc_0세자녀 = 0
        
        # Logs
        self.성공_log = ""
        self.실패_log = ""

    def run_revise_main(self, log_callback=None, progress_callback=None):
        """
        Mirrors VBA Revise_Main subroutine.
        Main entry point for appendix revision.
        """
        if log_callback:
            log_callback("Starting Appendix Revision...")
        
        try:
            self.word.start_app(visible=True)
            
            # Reference ranges
            ref_경로 = self.config.get_range_object("Ref_경로")
            ref_상품 = self.config.get_range_object("Ref_상품")
            ref_base파일명 = self.config.get_range_object("Ref_Base파일명")
            ref_loop = self.config.get_range_object("Ref_Loop")
            
            loop_start = int(self.config.get_range_value("Loop_시작") or 0)
            loop_end = int(self.config.get_range_value("Loop_종료") or 0)
            
            # Load Base파일명 array
            max_row = ref_base파일명.End(-4121).Row - ref_base파일명.Row + 1  # xlDown
            max_col = ref_base파일명.End(-4161).Column - ref_base파일명.Column + 1  # xlToRight
            self.source_doc_arr = ref_base파일명.Resize(max_row, max_col).Value
            base_path = str(ref_경로.Offset(0, 1).Value or "").strip()
            
            # Load 상품약관 array
            max_row = ref_상품.End(-4121).Row - ref_상품.Row + 1
            max_col = ref_상품.End(-4161).Column - ref_상품.Column + 1
            self.target_doc_arr = ref_상품.Resize(max_row, max_col).Value
            product_path = str(ref_경로.Offset(1, 1).Value or "").strip()
            
            # Find 0세자녀 column location
            for i, val in enumerate(self.target_doc_arr[0] if self.target_doc_arr else []):
                if str(val).strip() == "0세자녀":
                    self.loc_0세자녀 = i
                    break
            
            # Clear previous results
            clear_range = self.config.main_sheet.Range(
                ref_loop.Offset(loop_start, 3),
                ref_loop.Offset(loop_end, 4)
            )
            clear_range.ClearContents()
            
            if log_callback:
                log_callback(f"Processing {len(self.target_doc_arr) - 1} target documents...")
            
            # Call the main revision logic
            self._revise_appendix_content(
                base_path, product_path, ref_loop, 
                loop_start, loop_end, log_callback, progress_callback
            )
            
            if log_callback:
                log_callback("Appendix Revision Completed!")
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error: {e}")
            import traceback
            traceback.print_exc()

    def _revise_appendix_content(self, base_path, product_path, ref_loop, 
                                  loop_start, loop_end, log_callback=None, progress_callback=None):
        """
        Mirrors VBA Revise별표내용 subroutine.
        Core logic for revising appendix content.
        """
        source_doc = None
        target_doc = None
        
        # Iterate through target documents
        for i in range(1, len(self.target_doc_arr)):
            target_filename = str(self.target_doc_arr[i][1]).strip() if len(self.target_doc_arr[i]) > 1 else ""
            full_target_path = os.path.join(product_path, target_filename)
            
            if log_callback:
                log_callback(f"Opening target: {target_filename}")
            
            # Open target document
            target_doc = self.word.open_doc(full_target_path)
            if not target_doc:
                if log_callback:
                    log_callback(f"Failed to open: {target_filename}")
                continue
            
            # Find 별표 region in target
            target_appendix_start = 0
            target_appendix_end = 0
            found_start = False
            
            for comment in target_doc.Comments:
                comment_text = str(comment.Range.Text).strip()
                
                if comment_text == "별표" and not found_start:
                    target_appendix_start = comment.Scope.Paragraphs(1).Range.Start
                    found_start = True
                elif comment_text == "법규정" and found_start:
                    target_appendix_end = comment.Scope.Paragraphs(1).Range.Start
                    break
            
            if not found_start:
                if log_callback:
                    log_callback(f"Warning: No '별표' comment found in {target_filename}")
                continue
            
            target_appendix_range = target_doc.Range(target_appendix_start, target_appendix_end)
            
            # Process each loop point
            for loop_point in range(loop_start, loop_end + 1):
                self.성공_log = str(ref_loop.Offset(loop_point, 3).Value or "")
                self.실패_log = str(ref_loop.Offset(loop_point, 4).Value or "")
                
                별표명 = str(ref_loop.Offset(loop_point, 1).Value or "").strip()
                base_category = str(ref_loop.Offset(loop_point, 2).Value or "").strip()
                
                if log_callback:
                    log_callback(f"Processing: {별표명}")
                
                # Find 별표 in target
                revise_range, para = self._find_appendix_in_doc(
                    target_doc, target_appendix_range, 별표명, 
                    self.target_doc_arr[i][self.loc_0세자녀] if self.loc_0세자녀 > 0 and len(self.target_doc_arr[i]) > self.loc_0세자녀 else 0
                )
                
                if not revise_range:
                    self.실패_log += f" {self.target_doc_arr[i][0]}:해당별표없음,"
                    ref_loop.Offset(loop_point, 4).Value = self.실패_log
                    continue
                
                # Find source base file
                source_filename = None
                for j in range(len(self.source_doc_arr)):
                    if str(self.source_doc_arr[j][0]).strip() == base_category:
                        source_filename = str(self.source_doc_arr[j][1]).strip()
                        break
                
                if not source_filename:
                    self.실패_log += f" Base파일 없음,"
                    ref_loop.Offset(loop_point, 4).Value = self.실패_log
                    continue
                
                # Open source document
                full_source_path = os.path.join(base_path, source_filename)
                source_doc = self.word.open_doc(full_source_path)
                
                if not source_doc:
                    self.실패_log += f" Source파일 열기 실패,"
                    ref_loop.Offset(loop_point, 4).Value = self.실패_log
                    continue
                
                # Find source 별표 region
                source_appendix_range = self._find_source_appendix_region(source_doc, 별표명)
                
                if source_appendix_range:
                    # Copy formatted text
                    revise_range.FormattedText = source_appendix_range.FormattedText
                    
                    self.성공_log += f" {self.target_doc_arr[i][0]}수정,"
                    ref_loop.Offset(loop_point, 3).Value = self.성공_log
                    
                    # Update cross references
                    self._update_cross_ref(target_doc, revise_range)
                
                if progress_callback:
                    total = loop_end - loop_start + 1
                    progress_callback(int((loop_point - loop_start + 1) / total * 100))
            
            # Handle 0세자녀 tags
            self._revise_0세자녀_tags(target_doc, target_appendix_range, 
                                       self.target_doc_arr[i][self.loc_0세자녀] if self.loc_0세자녀 > 0 else 0)

    def _find_appendix_in_doc(self, doc, search_range, 별표명, zero_age_child):
        """
        Finds a specific appendix (별표) in the document.
        Returns (revise_range, para) or (None, None) if not found.
        """
        try:
            find_range = doc.Range(search_range.Start, search_range.End)
            find_range.Find.Text = 별표명
            find_range.Find.Font.Bold = True
            
            while find_range.Find.Execute():
                para = find_range.Paragraphs(1)
                para_text = clean_text(para.Range.Text)
                
                # Check if it's a list item and matches exactly
                if para.Range.ListFormat.ListType != 0:
                    if para_text == 별표명:
                        return (find_range, para)
                    elif zero_age_child > 0 and para_text == 별표명 + "[자녀]":
                        return (find_range, para)
                
                # Move to next occurrence
                find_range = doc.Range(find_range.End, search_range.End)
                find_range.Find.Text = 별표명
                find_range.Find.Font.Bold = True
            
            # Try with [자녀] suffix
            if zero_age_child > 0:
                find_range = doc.Range(search_range.Start, search_range.End)
                find_range.Find.Text = 별표명 + "[자녀]"
                find_range.Find.Font.Bold = True
                
                if find_range.Find.Execute():
                    para = find_range.Paragraphs(1)
                    return (find_range, para)
            
            return (None, None)
            
        except Exception as e:
            print(f"Error finding appendix: {e}")
            return (None, None)

    def _find_source_appendix_region(self, source_doc, 별표명):
        """
        Finds the source appendix region to copy.
        """
        try:
            # Find 별표 comment in source
            source_start = 0
            
            for comment in source_doc.Comments:
                if str(comment.Range.Text).strip() == "별표":
                    source_start = comment.Scope.Paragraphs(1).Range.Start
                    break
            
            if source_start == 0:
                return None
            
            source_range = source_doc.Range(source_start, source_doc.Content.End)
            
            # Find specific 별표명 in source
            source_range.Find.Text = 별표명
            source_range.Find.Font.Bold = True
            
            if source_range.Find.Execute():
                para = source_range.Paragraphs(1)
                para_text = clean_text(para.Range.Text)
                
                if para.Range.ListFormat.ListType != 0 and para_text == 별표명:
                    # Find the end of this appendix section
                    # This would typically be the next list paragraph or 법규정 comment
                    return source_doc.Range(para.Next.Next.Range.Start, para.Range.End)
            
            return None
            
        except Exception as e:
            print(f"Error finding source appendix: {e}")
            return None

    def _update_cross_ref(self, doc, revise_range):
        """
        Mirrors VBA CrossRef subroutine.
        Updates cross-references within the revised range.
        """
        try:
            revise_range2 = doc.Range(revise_range.Start, revise_range.End)
            
            while True:
                found = False
                
                for field in revise_range2.Fields:
                    if field.Type == 3:  # wdFieldRef
                        field_code = field.Code.Text
                        
                        # Delete paragraph number references
                        if "\\r" in field_code or "\\w" in field_code or "\\n" in field_code:
                            field.Delete()
                            found = True
                            break
                        
                        # Handle paragraph text references
                        if "\\r" not in field_code and "\\p" not in field_code and "\\w" not in field_code:
                            font_size = field.Result.Font.Size
                            font_color = field.Result.Font.Color
                            
                            src_text = field.Result.Text
                            cleaned = clean_text(src_text)
                            cleaned = cleaned.replace(" ", "")
                            
                            ref_range = field.Code
                            field.Delete()
                            
                            # Replace with placeholder
                            new_range = doc.Range(ref_range.Start - 1, ref_range.End)
                            new_range.Text = "{별표" + cleaned + "}"
                            
                            found = True
                            break
                
                if not found:
                    break
                
        except Exception as e:
            print(f"Error updating cross refs: {e}")

    def _revise_0세자녀_tags(self, doc, appendix_range, has_zero_age_child):
        """
        Handles 0세자녀 tag removal or modification.
        """
        try:
            if has_zero_age_child == 0:
                # Remove entire 0세자녀 sections
                while True:
                    revise_range = doc.Range(appendix_range.Start, appendix_range.End)
                    revise_range.Find.Text = "{0세자녀-1}"
                    
                    if not revise_range.Find.Execute():
                        break
                    
                    start_point = revise_range.Start
                    
                    revise_range = doc.Range(start_point, doc.Range.End)
                    revise_range.Find.Text = "{0세자녀-2}"
                    
                    if revise_range.Find.Execute():
                        end_point = revise_range.End
                        delete_range = doc.Range(start_point, end_point)
                        delete_range.Delete()
            else:
                # Just remove the tags, keep the content
                while True:
                    revise_range = doc.Range(appendix_range.Start, appendix_range.End)
                    revise_range.Find.Text = "{0세자녀-1}"
                    
                    if revise_range.Find.Execute():
                        revise_range.Text = ""
                        if revise_range.Start > 1:
                            revise_range.Start = revise_range.Start - 1
                            revise_range.Delete(1, 1)
                    else:
                        break
                    
                    revise_range = doc.Range(appendix_range.Start, appendix_range.End)
                    revise_range.Find.Text = "{0세자녀-2}"
                    
                    if revise_range.Find.Execute():
                        revise_range.Text = ""
                        
        except Exception as e:
            print(f"Error revising 0세자녀 tags: {e}")
