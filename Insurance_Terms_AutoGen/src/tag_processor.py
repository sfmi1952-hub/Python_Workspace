"""
Tag Processor Module - 약관 태그 처리
Handles substitution tags (치환태그) and output control tags (출력조정태그).

Based on VBA program guide:
- 치환태그: {진단확정N}, {감액기간N-M}, {지급률N-M-K}, {단체1}, {예약가입}, {감액1}, {감액2-N}, 
            {연장형}, {부모}, {세부보장N}
- 출력조정태그: {면책0-K}, {감액있음N-K}, {비갱신N-K}, {갱신N-K}, {감액한번N-K}, {감액두번N-K}, 
                {진단확정N-K}, {자동갱신형N-K}, {독립특약0-K}
"""
import re
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class TagContext:
    """Context for tag processing - holds all variables needed for tag replacement."""
    # 담보 속성  
    담보코드: str = ""
    대표담보코드: str = ""
    대표담보코드_list: List[str] = field(default_factory=list)  # 메모에 여러 담보코드가 있는 경우
    
    # 모델링 속성
    면책: int = 0
    감액: int = 0
    진단확정: int = 0
    부모: int = 0
    예약가입연령: int = 0
    연장형: int = 0
    단체: int = 0
    자동갱신형: int = 0
    독립특약: int = 0
    비갱신: int = 0
    
    # 감액 관련
    감액한번: bool = True
    감액두번: bool = False
    감액기간_list: List[List[int]] = field(default_factory=list)  # [[180, 365], [365]] - 코드별 감액기간
    감액비율_list: List[List[float]] = field(default_factory=list)  # [[50, 100], [100]] - 코드별 감액비율
    
    # 지급률 관련 (N-M-K 구조)
    지급률_data: Dict[str, List[List[float]]] = field(default_factory=dict)  # {담보코드: [[지급률1, 지급률2], [지급률3]]}
    
    # 세부보장 관련
    세부보장명_list: List[str] = field(default_factory=list)  # 대표담보코드별 세부보장명


class TagProcessor:
    """
    Tag processor for insurance terms documents.
    Handles both substitution tags and output control tags.
    """
    
    def __init__(self, csv_loader=None):
        """
        Initialize tag processor.

        Args:
            csv_loader: CSVLoader instance for 참조 data lookup
        """
        self.csv_loader = csv_loader

        # 치환태그 패턴 (참조시트에서 치환) - PRE-COMPILED for speed
        self.substitution_patterns = {
            re.compile(r'\{단체(\d*)\}'): self._replace_단체,
            re.compile(r'\{감액(\d*)\}'): self._replace_감액,
            re.compile(r'\{감액2-(\d+)\}'): self._replace_감액2,
            re.compile(r'\{연장형(\d*)\}'): self._replace_연장형,
            re.compile(r'\{부모(\d*)\}'): self._replace_부모,
            re.compile(r'\{예약가입(\d*)\}'): self._replace_예약가입,
            re.compile(r'\{진단확정(\d+)\}'): self._replace_진단확정,
            re.compile(r'\{세부보장(\d+)\}'): self._replace_세부보장,
            re.compile(r'\{보통약관 해약환급금\}'): self._replace_보통약관_해약환급금,
        }

        # Quick-check keywords to skip irrelevant patterns (avoid regex on non-matching text)
        self._substitution_keywords = {
            '단체': [], '감액': [], '감액2-': [], '연장형': [], '부모': [],
            '예약가입': [], '진단확정': [], '세부보장': [], '보통약관': [],
        }
        for compiled_re, handler in self.substitution_patterns.items():
            # Extract the base keyword from the pattern for fast pre-check
            pattern_str = compiled_re.pattern
            for keyword in self._substitution_keywords:
                if keyword in pattern_str:
                    self._substitution_keywords[keyword].append((compiled_re, handler))
                    break

        # PGM에서 읽어 치환하는 태그 - PRE-COMPILED
        self.pgm_patterns = {
            re.compile(r'\{감액기간(\d+)-(\d+)\}'): self._replace_감액기간,
            re.compile(r'\{지급률(\d+)-(\d+)-(\d+)\}(\*|\/)?(\d+\.?\d*)?(%)?'): self._replace_지급률,
        }

        # 출력조정태그 패턴 - PRE-COMPILED
        self.output_control_patterns = [
            (re.compile(r'\{면책0-(\d)\}'), '면책'),
            (re.compile(r'\{감액있음(\d+)-(\d)\}'), '감액'),
            (re.compile(r'\{비갱신(\d+)-(\d)\}'), '비갱신'),
            (re.compile(r'\{갱신(\d+)-(\d)\}'), '갱신'),
            (re.compile(r'\{감액한번(\d+)-(\d)\}'), '감액한번'),
            (re.compile(r'\{감액두번(\d+)-(\d)\}'), '감액두번'),
            (re.compile(r'\{진단확정(\d+)-(\d)\}'), '진단확정'),
            (re.compile(r'\{자동갱신형(\d+)-(\d)\}'), '자동갱신형'),
            (re.compile(r'\{독립특약0-(\d)\}'), '독립특약'),
        ]

        # Pre-compiled cleanup pattern
        self._cleanup_pattern = re.compile(
            r'\{(?:연장형|부모|예약가입|단체|감액|감액2-|진단확정|세부보장|감액기간|지급률'
            r'|면책|감액있음|비갱신|갱신|감액한번|감액두번|자동갱신형|독립특약)\d*(?:-\d+)?(?:-\d+)?\}'
        )
    
    def process_all_tags(self, text: str, context: TagContext) -> str:
        """
        Process all tags in the text.
        
        Args:
            text: Text containing tags
            context: TagContext with all necessary variables
            
        Returns:
            Processed text with tags replaced/removed
        """
        # 1. 출력조정태그 처리 (먼저 처리 - 섹션 삭제가 먼저)
        text = self._process_output_control_tags(text, context)
        
        # 2. 치환태그 처리 (참조시트)
        text = self._process_substitution_tags(text, context)
        
        # 3. PGM 기반 치환태그 처리
        text = self._process_pgm_tags(text, context)
        
        return text
    
    def _process_output_control_tags(self, text: str, context: TagContext) -> str:
        """
        Process output control tags (출력조정태그).
        Rules:
        - K=1,2: 속성 해당하면 태그만 삭제, 아니면 태그+사이내용 삭제
        - K=3,4: 속성 해당하면 태그+사이내용 삭제, 아니면 태그만 삭제
        """
        for pattern, attr_name in self.output_control_patterns:
            text = self._process_single_output_tag(text, pattern, attr_name, context)
        return text
    
    def _process_single_output_tag(self, text: str, pattern, attr_name: str,
                                   context: TagContext) -> str:
        """Process a single type of output control tag. Accepts pre-compiled pattern."""
        # Use pre-compiled pattern directly (no re.compile overhead)
        regex = pattern if hasattr(pattern, 'finditer') else re.compile(pattern)
        matches = list(regex.finditer(text))
        
        if not matches:
            return text
        
        # Process pairs (tag-1/tag-2 or tag-3/tag-4)
        i = 0
        while i < len(matches) - 1:
            match1 = matches[i]
            match2 = matches[i + 1]
            
            # Extract K values
            groups1 = match1.groups()
            groups2 = match2.groups()
            
            # K is the last group
            k1 = int(groups1[-1])
            k2 = int(groups2[-1])
            
            # Get N value if present (for 담보코드 순번)
            n_value = 1
            if len(groups1) > 1:
                try:
                    n_value = int(groups1[0]) if groups1[0] else 1
                except ValueError:
                    n_value = 1
            
            # Check if we have a valid pair
            if (k1 in [1, 3] and k2 in [2, 4]) or (k1 in [2, 4] and k2 in [1, 3]):
                # Get attribute value from context
                attr_value = self._get_attribute_value(attr_name, n_value, context)
                
                # Determine action based on K values and attribute
                if k1 in [1, 2]:
                    # -1~-2 rule: 속성 해당하면 태그만 삭제, 아니면 전체삭제
                    if attr_value:
                        # Delete only tags
                        text = text[:match1.start()] + text[match1.end():match2.start()] + text[match2.end():]
                    else:
                        # Delete tags and content between
                        text = text[:match1.start()] + text[match2.end():]
                else:  # k1 in [3, 4]
                    # -3~-4 rule: 속성 해당하면 전체삭제, 아니면 태그만 삭제
                    if attr_value:
                        # Delete tags and content between
                        text = text[:match1.start()] + text[match2.end():]
                    else:
                        # Delete only tags
                        text = text[:match1.start()] + text[match1.end():match2.start()] + text[match2.end():]
                
                # Re-find matches after modification
                matches = list(regex.finditer(text))
                i = 0  # Reset index
            else:
                i += 1
        
        return text
    
    def _get_attribute_value(self, attr_name: str, n_value: int, context: TagContext) -> bool:
        """Get attribute value from context based on name and N index."""
        # N=0 means all (특정 담보코드 상관없이)
        if n_value == 0:
            n_value = 1  # Use first code's attributes
        
        # Adjust for 0-based index
        idx = n_value - 1 if n_value > 0 else 0
        
        if attr_name == '면책':
            return context.면책 > 0
        elif attr_name == '감액':
            return context.감액 > 0
        elif attr_name == '진단확정':
            return context.진단확정 > 0
        elif attr_name == '부모':
            return context.부모 > 0
        elif attr_name == '연장형':
            return context.연장형 > 0
        elif attr_name == '단체':
            return context.단체 > 0
        elif attr_name == '자동갱신형':
            return context.자동갱신형 > 0
        elif attr_name == '독립특약':
            return context.독립특약 > 0
        elif attr_name == '비갱신':
            return context.비갱신 > 0 or context.자동갱신형 == 0
        elif attr_name == '갱신':
            return context.자동갱신형 > 0
        elif attr_name == '감액한번':
            return context.감액한번 and not context.감액두번
        elif attr_name == '감액두번':
            return context.감액두번
        
        return False
    
    def _process_substitution_tags(self, text: str, context: TagContext) -> str:
        """Process substitution tags using 참조 data. Uses pre-compiled patterns."""
        for compiled_re, handler in self.substitution_patterns.items():
            text = compiled_re.sub(lambda m: handler(m, context), text)
        return text

    def _process_pgm_tags(self, text: str, context: TagContext) -> str:
        """Process PGM-based tags (감액기간, 지급률). Uses pre-compiled patterns."""
        for compiled_re, handler in self.pgm_patterns.items():
            text = compiled_re.sub(lambda m: handler(m, context), text)
        return text
    
    # ==================== 치환태그 핸들러 ====================
    
    def _replace_단체(self, match, context: TagContext) -> str:
        """Replace {단체N} tag."""
        n = match.group(1) or "1"
        코드명 = f"{{단체{n}}}"
        
        # 적용구분: 1=단체보험인 경우, 0=아닌 경우
        적용구분 = 1 if context.단체 > 0 else 0
        
        return self._lookup_참조(코드명, "단체", 적용구분)
    
    def _replace_감액(self, match, context: TagContext) -> str:
        """Replace {감액N} tag."""
        n = match.group(1) or "1"
        코드명 = f"{{감액{n}}}"
        
        적용구분 = 1 if context.감액 > 0 else 0
        
        return self._lookup_참조(코드명, "감액", 적용구분)
    
    def _replace_감액2(self, match, context: TagContext) -> str:
        """Replace {감액2-N} tag - N번째 대표담보코드의 감액여부에 따라 치환."""
        n = int(match.group(1))
        코드명 = "{감액2}"
        
        # N번째 담보코드의 감액 여부 확인
        적용구분 = 1 if context.감액 > 0 else 0
        
        return self._lookup_참조(코드명, "감액", 적용구분)
    
    def _replace_연장형(self, match, context: TagContext) -> str:
        """Replace {연장형N} tag."""
        n = match.group(1) or ""
        코드명 = f"{{연장형{n}}}" if n else "{연장형}"
        적용구분 = 1 if context.연장형 > 0 else 0
        return self._lookup_참조(코드명, "연장형", 적용구분)
    
    def _replace_부모(self, match, context: TagContext) -> str:
        """Replace {부모N} tag."""
        n = match.group(1) or ""
        코드명 = f"{{부모{n}}}" if n else "{부모}"
        적용구분 = 1 if context.부모 > 0 else 0
        return self._lookup_참조(코드명, "부모", 적용구분)
    
    def _replace_예약가입(self, match, context: TagContext) -> str:
        """Replace {예약가입N} tag."""
        n = match.group(1) or ""
        코드명 = f"{{예약가입{n}}}" if n else "{예약가입}"
        적용구분 = 1 if context.예약가입연령 > 0 else 0
        return self._lookup_참조(코드명, "예약가입연령", 적용구분)

    def _replace_보통약관_해약환급금(self, match, context: TagContext) -> str:
        """Replace {보통약관 해약환급금} tag."""
        # This is likely a direct lookup without specific attribute dependency, 
        # or it might depend on product attributes. For now, try direct lookup.
        # Assuming it's in 참조 table.
        return self._lookup_참조("{보통약관 해약환급금}", None, None)
    
    def _replace_진단확정(self, match, context: TagContext) -> str:
        """Replace {진단확정N} tag."""
        n = match.group(1)
        코드명 = f"{{진단확정{n}}}"
        
        적용구분 = 1 if context.진단확정 > 0 else 0
        
        return self._lookup_참조(코드명, "진단확정", 적용구분)
    
    def _replace_세부보장(self, match, context: TagContext) -> str:
        """
        Replace {세부보장N} tag.
        N: 약관메모에 있는 대표담보코드 순서
        치환값: 해당 담보코드의 세부보장명 (「약관명」 형태로)
        """
        n = int(match.group(1))
        idx = n - 1
        
        if idx < len(context.세부보장명_list):
            세부보장명 = context.세부보장명_list[idx]
            if 세부보장명:
                return f"「{세부보장명}」"
        
        return ""
    
    def _replace_감액기간(self, match, context: TagContext) -> str:
        """
        Replace {감액기간N-K} tag.
        N: 대표담보코드 순서 (1, 2, ...)
        K: 감액기간 오름차순 순번
        """
        n = int(match.group(1))
        k = int(match.group(2))
        
        idx_n = n - 1
        idx_k = k - 1
        
        if idx_n < len(context.감액기간_list):
            기간_list = sorted(context.감액기간_list[idx_n])  # 오름차순 정렬
            if idx_k < len(기간_list):
                기간 = 기간_list[idx_k]
                return self._format_기간(기간)
        
        return "NA"
    
    def _replace_지급률(self, match, context: TagContext) -> str:
        """
        Replace {지급률N-M-K} tag, optionally with arithmetic.
        N: 대표담보코드 순서
        M: 세부담보코드 순번 (오름차순)
        K: 지급률 순번 (오름차순)
        Optional: *x or /x for arithmetic operations
        """
        n = int(match.group(1))
        m = int(match.group(2))
        k = int(match.group(3))
        operator = match.group(4) if len(match.groups()) > 3 else None
        operand = match.group(5) if len(match.groups()) > 4 else None
        percent_sign = match.group(6) if len(match.groups()) > 5 else ""
        
        idx_n = n - 1
        idx_m = m - 1
        idx_k = k - 1
        
        # Get 대표담보코드
        if idx_n >= len(context.대표담보코드_list):
            return ""
        
        담보코드 = context.대표담보코드_list[idx_n]
        
        # Get 지급률 data
        if 담보코드 in context.지급률_data:
            세부담보_지급률 = context.지급률_data[담보코드]
            if idx_m < len(세부담보_지급률):
                지급률_list = sorted(세부담보_지급률[idx_m])  # 오름차순
                if idx_k < len(지급률_list):
                    지급률 = 지급률_list[idx_k]
                    
                    # Apply arithmetic if specified
                    if operator and operand:
                        try:
                            operand_val = float(operand)
                            if operator == '*':
                                지급률 = 지급률 * operand_val
                            elif operator == '/':
                                지급률 = 지급률 / operand_val
                        except ValueError:
                            pass
                    
                    # Format result
                    if 지급률 == int(지급률):
                        return f"{int(지급률)}{percent_sign}"
                    else:
                        return f"{지급률:.1f}{percent_sign}"
        
        return ""
    
    def _lookup_참조(self, 코드명: str, 담보속성: str, 적용구분: int) -> str:
        """
        Lookup replacement text from 참조 CSV.
        
        Args:
            코드명: Tag name (e.g., '{단체1}')
            담보속성: Coverage attribute (e.g., '단체')
            적용구분: Application type (0 or 1)
        """
        if self.csv_loader is None:
            return ""
        
        result = self.csv_loader.find_참조문구(코드명, 담보속성, 적용구분)
        return result if result else ""
    
    def _format_기간(self, days: int) -> str:
        """Format period in days to readable format."""
        if days == 0:
            return ""
        elif days < 30:
            return f"{days}일"
        elif days < 365:
            months = days // 30
            return f"{months}개월" if days % 30 == 0 else f"{days}일"
        else:
            years = days // 365
            return f"{years}년" if days % 365 == 0 else f"{days}일"
    
    # ==================== Range (Word) 처리 ====================
    
    def process_range(self, range_obj, context: TagContext, log_callback=None) -> None:
        """
        Process all tags in a specific Word Range.
        Refactored to support range-based processing (e.g., per-section).
        
        Args:
            range_obj: Word Range object
            context: TagContext with processing data
            log_callback: Optional logging callback
        """
        try:
            # Get text of the range ONCE for tag detection
            full_text = range_obj.Text
            
            # Only proceed if there are tags in the range
            if '{' not in full_text:
                return

            # Check if output control tags exist (fast string check)
            has_output_tags = any(tag in full_text for tag in [
                '{면책0-', '{독립특약0-', '{비갱신', '{갱신', '{자동갱신형',
                '{감액있음', '{감액한번', '{감액두번', '{진단확정'
            ])
            
            # 1. 출력조정태그 처리 (섹션 삭제 로직) - only if tags exist
            if has_output_tags:
                self._range_process_output_control_tags(range_obj, context, full_text, log_callback)
                # Re-get text only after actual deletions
                full_text = range_obj.Text
            
            # 2. 치환태그 처리 (단순 치환) - use cached text
            self._range_find_replace_tags(range_obj, context, full_text, log_callback)
            
            # 3. 최종 정리 - 남은 태그 삭제 (use cached text)
            self._range_cleanup_remaining_tags(range_obj, full_text, log_callback)
            
        except Exception as e:
            if log_callback:
                log_callback(f"   ❌ TagProcessor 오류: {e}")
    
    def _range_cleanup_remaining_tags(self, range_obj, cached_text=None, log_callback=None):
        """
        Final cleanup: Remove any remaining unused tags in the range.
        Uses manual Find/Execute loop (wdReplaceAll doesn't work on Range).
        """
        try:
            full_text = cached_text if cached_text else range_obj.Text

            if '{' not in full_text:
                return

            tags_to_delete = set(self._cleanup_pattern.findall(full_text))

            if not tags_to_delete:
                return

            doc = range_obj.Document

            for tag in tags_to_delete:
                try:
                    search_range = doc.Range(range_obj.Start, range_obj.End)
                    find = search_range.Find
                    find.ClearFormatting()
                    find.Replacement.ClearFormatting()
                    find.Text = tag
                    find.Forward = True
                    find.Wrap = 0
                    find.MatchCase = True
                    find.MatchWholeWord = False
                    find.MatchWildcards = False

                    for _ in range(50):
                        if not find.Execute():
                            break
                        search_range.Text = ""
                        search_range.Collapse(0)
                except:
                    pass

        except Exception as e:
            if log_callback:
                log_callback(f"   ⚠️ 태그 정리 오류: {e}")
    
    def _range_process_output_control_tags(self, range_obj, context: TagContext, cached_text=None, log_callback=None):
        """
        Process output control tags in the specified range.
        Uses regex to detect only actually-present tags instead of generating all possible configs.
        """
        try:
            # Use cached text if provided
            range_text = cached_text if cached_text else range_obj.Text
            
            # ===== OPTIMIZED: Extract only tags that ACTUALLY EXIST in text =====
            # Base tags (no N suffix) - always check these
            tag_configs = []
            
            base_tags = {
                '면책0': context.면책 > 0,
                '독립특약0': context.독립특약 > 0,
                '비갱신0': context.비갱신 > 0 or context.자동갱신형 == 0,
                '갱신0': context.자동갱신형 > 0,
                '자동갱신형0': context.자동갱신형 > 0,
            }
            for tag_name, attr_value in base_tags.items():
                if f'{{{tag_name}-' in range_text:
                    tag_configs.append((tag_name, attr_value))
            
            # N-based tags: extract actual N values from text using regex
            n_tag_patterns = {
                '감액있음': lambda: context.감액 > 0,
                '비갱신': lambda: context.비갱신 > 0 or context.자동갱신형 == 0,
                '갱신': lambda: context.자동갱신형 > 0,
                '감액한번': lambda: context.감액한번,
                '감액두번': lambda: context.감액두번,
                '진단확정': lambda: context.진단확정 > 0,
                '자동갱신형': lambda: context.자동갱신형 > 0,
            }
            
            # Single regex to find all N-based output control tags in text
            found_n_tags = set()
            for tag_base in n_tag_patterns:
                # Match {tagN-K} where N is a digit
                pattern = r'\{' + re.escape(tag_base) + r'(\d+)-'
                for m in re.finditer(pattern, range_text):
                    n = m.group(1)
                    tag_key = f'{tag_base}{n}'
                    if tag_key not in found_n_tags:
                        found_n_tags.add(tag_key)
                        tag_configs.append((tag_key, n_tag_patterns[tag_base]()))
            
            # Process ONLY existing tags
            for tag_name, attr_value in tag_configs:
                self._process_single_range_output_tag(range_obj, tag_name, attr_value)
                
        except Exception as e:
            if log_callback:
                log_callback(f"   ⚠️ 출력조정태그 처리 오류: {e}")
    
    def _process_single_range_output_tag(self, range_obj, tag_name: str, attr_value: bool):
        """
        Process a single output control tag pair in range.
        """
        # Process -1/-2 pairs
        self._delete_range_tag_pair(range_obj, f"{{{tag_name}-1}}", f"{{{tag_name}-2}}", attr_value, rule_type=12)
        # Process -3/-4 pairs  
        self._delete_range_tag_pair(range_obj, f"{{{tag_name}-3}}", f"{{{tag_name}-4}}", attr_value, rule_type=34)
    
    def _delete_range_tag_pair(self, range_obj, tag1: str, tag2: str, attr_value: bool, rule_type: int):
        """
        Find and delete tag pairs in range.
        """
        max_iterations = 50  # Prevent infinite loops
        iteration = 0
        
        doc = range_obj.Document  # Get parent document
        
        while iteration < max_iterations:
            iteration += 1
            
            try:
                # Find tag1 within the range
                find_range = doc.Range(range_obj.Start, range_obj.End)
                find_range.Find.ClearFormatting()
                found = find_range.Find.Execute(FindText=tag1, Forward=True, Wrap=0) # wdFindStop
                
                if not found:
                    break
                
                # Check if found range is still within our target range (double check)
                if find_range.Start < range_obj.Start or find_range.End > range_obj.End:
                    break
                
                tag1_start = find_range.Start
                tag1_end = find_range.End
                
                # Find second tag (search from after first tag, UP TO range_obj.End)
                search_range = doc.Range(tag1_end, range_obj.End)
                search_range.Find.ClearFormatting()
                found2 = search_range.Find.Execute(FindText=tag2, Forward=True, Wrap=0)
                
                if not found2:
                    break
                
                tag2_start = search_range.Start
                tag2_end = search_range.End
                
                # Determine what to delete based on rule_type and attr_value
                if rule_type == 12:
                    # -1/-2: attr_value=True -> tags only, False -> all
                    if attr_value:
                        # Delete only tags (tag2 first, then tag1 - backwards safely)
                        doc.Range(tag2_start, tag2_end).Delete()
                        doc.Range(tag1_start, tag1_end).Delete()
                    else:
                        # Delete everything from tag1 start to tag2 end
                        doc.Range(tag1_start, tag2_end).Delete()
                else:  # rule_type == 34
                    # -3/-4: attr_value=True -> all, False -> tags only
                    if attr_value:
                        # Delete everything from tag1 start to tag2 end
                        doc.Range(tag1_start, tag2_end).Delete()
                    else:
                        # Delete only tags (tag2 first, then tag1)
                        doc.Range(tag2_start, tag2_end).Delete()
                        doc.Range(tag1_start, tag1_end).Delete()
                
            except:
                break
    
    def _range_find_replace_tags(self, range_obj, context: TagContext, doc_text: str, log_callback=None):
        """
        Perform find & replace on range.
        Uses proven manual loop: Range created ONCE per tag, then Find/Replace in loop.
        """
        try:
            replacements = self._build_replacement_dict(context, doc_text)

            if not replacements:
                return

            doc = range_obj.Document

            if doc.TrackRevisions:
                doc.TrackRevisions = False

            for find_text, replace_text in replacements.items():
                try:
                    # Create range ONCE per tag
                    search_range = doc.Range(range_obj.Start, range_obj.End)
                    find = search_range.Find
                    find.ClearFormatting()
                    find.Replacement.ClearFormatting()
                    find.Text = find_text
                    find.Forward = True
                    find.Wrap = 0  # wdFindStop
                    find.MatchCase = True
                    find.MatchWholeWord = False
                    find.MatchWildcards = False

                    for _ in range(50):
                        if not find.Execute():
                            break
                        search_range.Text = replace_text
                        search_range.Collapse(0)  # wdCollapseEnd
                except Exception:
                    pass

        except Exception as e:
            if log_callback:
                log_callback(f"   ❌ 태그 치환 오류: {e}")
    
    # Pre-compiled patterns for _build_replacement_dict (class-level, compiled once)
    _RE_SUBSTITUTION_TAG = re.compile(
        r'\{(단체|감액|연장형|부모|예약가입|진단확정|세부보장|감액2-|감액기간|보통약관 해약환급금)(\d*)\}'
    )
    _RE_감액기간 = re.compile(r'\{감액기간(\d+)-(\d+)\}')
    _RE_세부보장 = re.compile(r'\{세부보장(\d+)\}')

    def _build_replacement_dict(self, context: TagContext, doc_text: str = "") -> Dict[str, str]:
        """
        Build dictionary of tag -> replacement text.
        Uses a single regex pass to extract only substitution tags (not output control tags).
        """
        replacements = {}

        if not doc_text or '{' not in doc_text:
            return replacements

        # ===== SINGLE REGEX PASS: Extract only substitution tags =====
        # This avoids matching output control tags like {감액있음1-2}, {면책0-1} etc.
        found_tags = set(self._RE_SUBSTITUTION_TAG.findall(doc_text))
        # Also find multi-part tags separately
        found_감액기간 = self._RE_감액기간.findall(doc_text)
        found_세부보장 = self._RE_세부보장.findall(doc_text)

        # Process simple substitution tags: {base} or {baseN}
        tag_handlers = {
            '단체': ('단체', context.단체),
            '감액': ('감액', context.감액),
            '연장형': ('연장형', context.연장형),
            '부모': ('부모', context.부모),
            '예약가입': ('예약가입연령', context.예약가입연령),
            '진단확정': ('진단확정', context.진단확정),
        }

        for base, n_str in found_tags:
            if base in tag_handlers:
                attr_name, attr_val = tag_handlers[base]
                적용구분 = 1 if attr_val > 0 else 0
                tag_full = f"{{{base}{n_str}}}"

                # Try exact lookup first, then fallback to base
                val = self._lookup_참조(tag_full, attr_name, 적용구분)
                if val is not None:
                    replacements[tag_full] = val
                elif n_str:
                    tag_plain = f"{{{base}}}"
                    val = self._lookup_참조(tag_plain, attr_name, 적용구분)
                    if val is not None:
                        replacements[tag_full] = val

            elif base == '감액2-' and n_str:
                적용구분 = 1 if context.감액 > 0 else 0
                tag_full = f"{{감액2-{n_str}}}"
                val = self._lookup_참조("{감액2}", "감액", 적용구분)
                if val is not None:
                    replacements[tag_full] = val

            elif base == '보통약관 해약환급금':
                tag_full = "{보통약관 해약환급금}"
                val = self._lookup_참조(tag_full, None, None)
                if val is not None:
                    replacements[tag_full] = val

        # 세부보장N 태그
        for (n_str,) in found_세부보장:
            idx = int(n_str) - 1
            tag_full = f"{{세부보장{n_str}}}"
            if idx < len(context.세부보장명_list):
                세부보장명 = context.세부보장명_list[idx]
                replacements[tag_full] = f"「{세부보장명}」" if 세부보장명 else ""
            else:
                replacements[tag_full] = ""

        # 감액기간N-K 태그
        if found_감액기간 and context.감액기간_list:
            for n_str, k_str in found_감액기간:
                n_idx = int(n_str) - 1
                k_idx = int(k_str) - 1
                tag_full = f"{{감액기간{n_str}-{k_str}}}"
                if n_idx < len(context.감액기간_list):
                    sorted_list = sorted(context.감액기간_list[n_idx])
                    if k_idx < len(sorted_list):
                        replacements[tag_full] = self._format_기간(sorted_list[k_idx])

        return replacements


def create_tag_context_from_dambo_att(dambo_att, data_loader=None) -> TagContext:
    """
    Helper function to create TagContext from DamboAttributes.
    
    Args:
        dambo_att: DamboAttributes instance
        data_loader: DataLoader instance for additional data
        
    Returns:
        Configured TagContext
    """
    context = TagContext()
    
    # Copy basic attributes
    context.담보코드 = dambo_att.담보코드
    context.대표담보코드 = dambo_att.대표담보코드
    
    # Parse multiple 대표담보코드 if present
    if dambo_att.대표담보코드:
        context.대표담보코드_list = [code.strip() for code in dambo_att.대표담보코드.split(',')]
    
    # Copy modeling attributes
    context.면책 = dambo_att.면책
    context.감액 = dambo_att.감액
    context.진단확정 = dambo_att.진단확정
    context.부모 = dambo_att.부모
    context.예약가입연령 = dambo_att.예약가입연령
    context.연장형 = dambo_att.연장형
    context.단체 = dambo_att.단체
    context.자동갱신형 = dambo_att.자동갱신형
    
    # 독립특약 (from dambo_att or data_loader)
    context.독립특약 = getattr(dambo_att, '독립특약', 0)
    if data_loader:
        context.독립특약 = getattr(data_loader, '독립특약', context.독립특약)
    
    # 세부보장명 리스트 (VBA에서 같은 출력담보명의 담보들을 묶어서 처리)
    세부보장명_list = getattr(dambo_att, '세부보장명_list', [])
    if not 세부보장명_list:
        # Fallback to single 세부보장명
        세부보장명 = getattr(dambo_att, '세부보장명', '')
        if 세부보장명:
            세부보장명_list = [세부보장명]
    context.세부보장명_list = 세부보장명_list
    
    return context
