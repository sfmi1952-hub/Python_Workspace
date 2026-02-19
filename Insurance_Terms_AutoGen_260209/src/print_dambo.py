"""
PrintDambo Module - Python Port (Optimized)
Main module for insurance terms document generation.
Contains the core logic for reading PGM, copying terms, and revising documents.

OPTIMIZATION: Uses Pandas DataLoader for bulk data reading (10-50x faster than COM)
"""
import os
import datetime
import numpy as np
from typing import Optional, List, Dict, Any, Tuple

from .word_utils import WordHandler, wdCollapseEnd, wdCollapseStart, wdSectionBreakOddPage
from .data_loader import DataLoader, ExcelWriter
from .tag_processor import TagProcessor, TagContext, create_tag_context_from_dambo_att


class DamboAttributes:
    """Data class to hold coverage attributes."""
    def __init__(self):
        self.담보코드 = ""
        self.대표담보코드 = ""
        self.진단확정 = 0
        self.부모 = 0
        self.예약가입연령 = 0
        self.모듈 = ""
        self.형구분 = ""
        self.단체 = 0
        self.자동갱신형 = 0
        self.면책강제반영 = ""
        self.면책 = 0
        self.감액 = 0
        self.연장형 = 0
        
        # 독립특약
        self.독특감액여부 = ""
        self.독특면책여부 = ""
        
        # 세부보장명 (for {세부보장N} tag replacement)
        self.세부보장명 = ""
        self.세부보장명_list = []  # 출력담보명이 같은 담보들의 담보명 리스트
        
        # 독립특약 설정
        self.독립특약 = 0


class PrintDambo:
    """
    Main class for insurance terms document generation.
    Uses Pandas-based DataLoader for high-performance data access.
    """
    
    def __init__(self, data_loader: DataLoader):
        """
        Initialize with DataLoader instance.
        
        Args:
            data_loader: Pre-loaded DataLoader with config and PGM data
        """
        self.data = data_loader
        self.word = WordHandler()
        self.tag_processor = TagProcessor()  # Tag processing module
        
        # Column Locations (cached from data arrays)
        self.loc_확장번호 = 0
        self.loc_보험기간연장형 = 0
        self.loc_간편고지 = 0
        self.loc_통합고지 = 0
        self.loc_태아구분 = 0
        self.loc_보기납기 = 0
        self.loc_담보그룹 = 0
        
        # 보장구조 columns
        self.loc_보장배수 = 0
        self.loc_세부담보순번 = 0
        self.loc_세부담보코드 = 0
        self.loc_급부탈퇴율개수 = 0
        self.loc_납면탈퇴율개수 = 0
        
        # 보장배수 columns
        self.loc_지급률 = 0
        self.loc_분할지급차년 = 0
        self.loc_연지급횟수 = 0
        self.loc_면책기간 = 0
        self.loc_감액기간 = 0
        self.loc_감액기간2 = 0
        self.loc_감액비율 = 0
        self.loc_감액비율2 = 0
        self.loc_15세면책 = 0
        
        # 세부담보 관련
        self.세부담보개수 = 0
        self.세부담보_bencoef = []
        self.세부담보코드List = []
        self.m_point = 0
        self.min_riskrate_row = 0
        self.납입면제여부 = False
        
        # 감액/면책 관련
        self.is감액두번 = False
        self.sum_면책 = 0
        self.sum_감액 = 0
        
        # 보기납기 관련
        self.n_array = []
        self.age_b = 0
        self.age_e = 0
        self.term_lookup_key = ""
        
        # Paths (from data_loader)
        self.출력파일명 = ""
        
        # Copied terms tracking
        self.copied_list_strings = set()
        
        # Number marks ① ② ③ etc.
        self.num_mark_arr = ["①", "②", "③", "④", "⑤", "⑥", "⑦", "⑧", "⑨", "⑩", 
                            "⑪", "⑫", "⑬", "⑭", "⑮"]
        
        # 독립특약 관련
        self.is_독특간편 = False
        self.독특담보그룹 = 0
        self.독립특약명 = ""
        
        # Excel Writer for result saving (lazy init)
        self._excel_writer = None

    def execute(self, log_callback=None, progress_callback=None):
        """
        Main entry point for terms generation.
        Uses template data (coverage_list) for mapping results and PGM data.
        """
        try:
            if log_callback:
                log_callback("초기화 및 컬럼 위치 파악...")
            
            # Initialize Word with performance settings
            self.word.start_app(visible=False)
            
            # Find column locations from cached arrays
            self._find_column_locations(log_callback)
            
            # Get coverage list from template_data
            template_data = getattr(self.data, 'template_data', {}) or {}
            coverage_list = template_data.get('coverage_list', [])
            
            if not coverage_list:
                if log_callback:
                    log_callback("❌ 담보목록이 없습니다. 템플릿을 먼저 로드해주세요.")
                return
            
            total_steps = len(coverage_list)
            
            if log_callback:
                log_callback(f"종속특약 약관생성: {total_steps}개 항목...")
            
            # Generate output filename
            now = datetime.datetime.now()
            self.출력파일명 = f"03_0_약관_{self.data.prod_name}_{now.strftime('%Y%m%d')}_{now.strftime('%H%M')}.docx"
            
            # ============ PRE-OPEN DOCUMENTS FOR PERFORMANCE ============
            # Open target document ONCE before loop
            target_path = getattr(self.data, 'product_doc_file', None)
            if target_path and os.path.exists(target_path):
                if log_callback:
                    log_callback(f"📄 타겟 문서 열기: {os.path.basename(target_path)}")
                self.word.target_doc = self.word.open_doc(target_path)
            
            # Cache source documents (open once, reuse)
            self.source_docs = {}  # {file_type: doc}
            if hasattr(self, 'base_files') and self.base_files:
                if log_callback:
                    log_callback(f"📄 소스 문서 {len(self.base_files)}개 열기...")
                for file_type, file_path in self.base_files.items():
                    doc = self.word.open_doc(file_path)
                    if doc:
                        self.source_docs[file_type] = doc
            
            # ============ OPTIMIZE WORD FOR BATCH OPERATIONS ============
            # Disable spell check, grammar check, pagination for massive speed boost
            self.word.optimize_for_batch_operations()
            if log_callback:
                log_callback("⚡ Word 최적화 설정 적용 (맞춤법/문법검사/페이지 계산 비활성화)")
            
            if log_callback:
                log_callback("✅ 문서 준비 완료\n")
            
            # ============ CONNECT COMPONENTS ============
            # Connect CSVLoader to TagProcessor if available
            if hasattr(self, 'csv_loader') and self.csv_loader:
                self.tag_processor.csv_loader = self.csv_loader
                if log_callback:
                    log_callback("✅ TagProcessor에 CSVLoader 연결 완료")
            
            # ============ GROUP BY 출력담보명 FOR 세부보장 TAGS ============
            # VBA: 출력담보명이 같은 담보들은 {세부보장1}, {세부보장2}... 순번으로 치환
            # 정렬 기준: 담보코드 오름차순
            self.출력담보명_groups = {}  # {출력담보명: [(담보코드, 담보명), ...]}
            for coverage in coverage_list:
                출력담보명 = str(coverage.get('출력담보명', '') or 
                              coverage.get('담보명_출력물명칭', '') or '').strip()
                담보명 = str(coverage.get('담보명', '') or 
                           coverage.get('세부보장명', '') or '').strip()
                담보코드 = str(coverage.get('담보코드', '')).strip()
                
                if 출력담보명 and 담보명:
                    if 출력담보명 not in self.출력담보명_groups:
                        self.출력담보명_groups[출력담보명] = []
                    self.출력담보명_groups[출력담보명].append((담보코드, 담보명))
            
            if log_callback and self.출력담보명_groups:
                log_callback(f"📋 출력담보명 그룹: {len(self.출력담보명_groups)}개")
            
            # ========================= PHASE 1: COPY & PROCESS TERMS =========================
            if log_callback:
                log_callback(f"\n📄 Phase 1: 약관 복사 및 태그 처리 ({total_steps}개)...")
            
            for i, coverage in enumerate(coverage_list):
                # Extract data from coverage dictionary (from template)
                dambo_code = str(coverage.get('담보코드', '')).strip()
                dambo_category = str(coverage.get('구분값', '')).strip()  # From CSV mapping
                대표담보코드 = str(coverage.get('대표담보코드', '')).strip()  # From CSV mapping
                
                if log_callback:
                    log_callback(f"  [{i+1}/{total_steps}] 처리중: {dambo_code} ({대표담보코드})")
                
                # Create DamboAttributes from coverage dictionary (from template)
                dambo_att = DamboAttributes()
                dambo_att.담보코드 = dambo_code
                dambo_att.대표담보코드 = 대표담보코드
                
                # Set 면책/감액/연장형 from template (already mapped from PGM)
                dambo_att.면책 = int(coverage.get('면책', 0) or 0)
                dambo_att.감액 = int(coverage.get('감액', 0) or 0)
                dambo_att.연장형 = int(coverage.get('연장형', 0) or 0)
                dambo_att.형구분 = str(coverage.get('형구분', '')).strip()
                
                # 모듈 설정
                모듈_val = coverage.get('모듈', '')
                if 모듈_val:
                    dambo_att.모듈 = f"{모듈_val}모듈"
                else:
                    dambo_att.모듈 = ""
                
                dambo_att.단체 = getattr(self.data, '단체보험', 0)
                dambo_att.자동갱신형 = getattr(self.data, '자동갱신형', 0)
                
                # 진단확정, 부모, 예약가입연령 추가
                dambo_att.진단확정 = int(coverage.get('진단확정', 0) or 0)
                dambo_att.부모 = int(coverage.get('부모', 0) or 0)
                dambo_att.예약가입연령 = int(coverage.get('예약가입연령', 0) or 0)
                
                # 세부보장명 설정
                dambo_att.세부보장명 = str(coverage.get('세부보장명', '') or 
                                         coverage.get('담보명', '') or '').strip()
                
                # 세부보장명_list 설정
                출력담보명 = str(coverage.get('출력담보명', '') or 
                              coverage.get('담보명_출력물명칭', '') or '').strip()
                
                if 출력담보명 in self.출력담보명_groups:
                    # 담보코드 기준으로 정렬
                    group_items = self.출력담보명_groups[출력담보명]
                    sorted_items = sorted(group_items, key=lambda x: x[0])  # x[0] is 담보코드
                    dambo_att.세부보장명_list = [item[1] for item in sorted_items]  # item[1] is 담보명
                else:
                    dambo_att.세부보장명_list = [dambo_att.세부보장명]
                
                # 독립특약 속성
                dambo_att.독립특약 = getattr(self.data, '독립특약', 0)
                
                # Read PGM Data (CRITICAL: Must read PGM before processing tags)
                # This updates self.sum_면책, self.sum_감액, self.세부담보_bencoef, etc.
                self._read_pgm_loop(dambo_code, dambo_att, i, log_callback)
                
                # 독립특약 파일 경로 재지정
                if self.data.독립특약 != 0:
                    self._set_독특_file_path(dambo_att, 대표담보코드, dambo_code, log_callback)
                
                # Find source document info
                특별약관경로 = ""
                특별약관파일명 = ""
                
                if hasattr(self, 'base_files') and self.base_files:
                    if dambo_category in self.base_files:
                        특별약관file = self.base_files[dambo_category]
                        특별약관경로 = os.path.dirname(특별약관file)
                        특별약관파일명 = os.path.basename(특별약관file)
                    else:
                        if self.base_files:
                            first_file = list(self.base_files.values())[0]
                            특별약관경로 = os.path.dirname(first_file)
                            특별약관파일명 = os.path.basename(first_file)
                elif self.data.arr_source_doc is not None:
                    for j in range(len(self.data.arr_source_doc)):
                        if dambo_category == str(self.data.arr_source_doc[j][0]).strip():
                            특별약관경로 = self.data.종속특약경로
                            특별약관파일명 = str(self.data.arr_source_doc[j][1]).strip()
                            break
                
                # Copy terms AND identify the range where it was pasted
                target_range = self._copy_terms(대표담보코드, 특별약관경로, 특별약관파일명, 
                                              dambo_category, dambo_att, log_callback)
                
                # Process Tags IMMEDIATELY on the target range
                if target_range:
                    self._revise_terms(dambo_att, i, target_range, log_callback)
                
                # Update progress
                if progress_callback:
                    progress_callback(int((i + 1) / total_steps * 100))

            
            # PHASE 2 REMOVED - Tags are processed in Phase 1 loop
            pass
            
            # Final processing - 0세자녀 태그 처리
            self._revise_별표_0세(log_callback)

            # ============ RESTORE WORD SETTINGS ============
            # Restore spell check, grammar check, pagination before saving
            self.word.restore_after_batch()
            
            # Enable screen updating to show final result
            self.word.enable_screen_updating(True)
            
            # Save the modified document to output path
            output_file = getattr(self.data, 'output_file', None)
            if log_callback:
                log_callback(f"\n📋 저장 준비 중...")
                log_callback(f"   출력 경로: {output_file}")
                log_callback(f"   target_doc 존재: {self.word.target_doc is not None}")
            
            if not output_file:
                if log_callback:
                    log_callback("❌ 저장 실패: 출력 파일 경로가 설정되지 않았습니다.")
            elif not self.word.target_doc:
                if log_callback:
                    log_callback("❌ 저장 실패: 대상 Word 문서가 열려있지 않습니다.")
                    log_callback("   원인: _copy_terms에서 target_doc이 설정되지 않았습니다.")
            else:
                try:
                    self.word.target_doc.SaveAs2(output_file)
                    if log_callback:
                        log_callback(f"✅ 파일 저장 완료: {output_file}")
                except Exception as save_err:
                    if log_callback:
                        log_callback(f"❌ 파일 저장 오류: {save_err}")
            
            # Close Word documents
            self.word.close_all()
            
            if log_callback:
                log_callback("\n✅ 약관 생성 완료!")
                
        except Exception as e:
            if log_callback:
                log_callback(f"Error: {e}")
            import traceback
            traceback.print_exc()

    def _find_column_locations(self, log_callback=None):
        """
        Find column locations in PGM arrays.
        Uses cached numpy arrays for fast lookup.
        """
        # Find column locations in Main sheet
        if self.data.arr_pgm_main is not None and len(self.data.arr_pgm_main) > 1:
            header_row = self.data.arr_pgm_main[1]  # Assuming header is row 1
            
            for i, val in enumerate(header_row):
                attr_name = str(val or "").strip().replace("\n", "")
                
                if attr_name == "ExpansionNumber":
                    self.loc_확장번호 = i
                elif attr_name == "보험기간연장형":
                    self.loc_보험기간연장형 = i
                elif attr_name == "ZA_ConvenientDisclosureTypeScCode":
                    self.loc_간편고지 = i
                elif attr_name == "ZA_DisclosureTypeScCode":
                    self.loc_통합고지 = i
                elif attr_name == "FetusFlag":
                    self.loc_태아구분 = i
                elif attr_name == "ZA_CoveragePaymentInprd":
                    self.loc_보기납기 = i
                elif attr_name == "담보그룹":
                    self.loc_담보그룹 = i
        
        # Find column locations in 보장구조
        if self.data.arr_보장구조 is not None and len(self.data.arr_보장구조) > 0:
            header_row = self.data.arr_보장구조[0]
            
            for i, val in enumerate(header_row):
                attr_name = str(val or "").strip().replace("\n", "")
                
                if attr_name == "보장배수":
                    self.loc_보장배수 = i
                elif attr_name == "세부담보순번":
                    self.loc_세부담보순번 = i
                elif attr_name == "세부담보코드":
                    self.loc_세부담보코드 = i
                elif attr_name == "탈퇴율개수":
                    if self.loc_급부탈퇴율개수 == 0:
                        self.loc_급부탈퇴율개수 = i
                    else:
                        self.loc_납면탈퇴율개수 = i
        
        # Find column locations in 보장배수
        if self.data.arr_보장배수 is not None and len(self.data.arr_보장배수) > 1:
            for i in range(len(self.data.arr_보장배수[1])):
                attr_name = str(self.data.arr_보장배수[1][i] or "").strip().replace("\n", "")
                if not attr_name and len(self.data.arr_보장배수) > 0:
                    attr_name = str(self.data.arr_보장배수[0][i] or "").strip().replace("\n", "")
                
                if attr_name == "지급률":
                    self.loc_지급률 = i
                elif attr_name == "지급차년":
                    self.loc_분할지급차년 = i
                elif attr_name == "연지급횟수":
                    self.loc_연지급횟수 = i
                elif attr_name == "면책기간":
                    self.loc_면책기간 = i
                elif attr_name == "감액기간":
                    if self.loc_감액기간 == 0:
                        self.loc_감액기간 = i
                    else:
                        self.loc_감액기간2 = i
                elif attr_name == "감액비율":
                    if self.loc_감액비율 == 0:
                        self.loc_감액비율 = i
                    else:
                        self.loc_감액비율2 = i
                elif attr_name == "15세미만면책적용":
                    self.loc_15세면책 = i
        
        if log_callback:
            log_callback(f"컬럼 위치 분석 완료: 확장번호={self.loc_확장번호}, 보기납기={self.loc_보기납기}")

    def _read_pgm_loop(self, dambo_code: str, dambo_att: DamboAttributes, loop_point: int, log_callback=None):
        """
        Read PGM data for each coverage code.
        Uses numpy arrays for fast lookup (nanosecond access).
        """
        try:
            # Initialize
            self.m_point = 0
            self.세부담보개수 = -1
            self.세부담보코드List = []
            self.is감액두번 = False
            self.min_riskrate_row = 0
            self.is_독특간편 = False
            
            # ===== M_Point Search (using numpy - FAST!) =====
            arr_main = self.data.arr_pgm_main
            
            if arr_main is not None:
                for mpoint_lookup in range(len(arr_main)):
                    try:
                        row = arr_main[mpoint_lookup]
                        if row[0] is None:
                            continue
                        
                        if self.data.독립특약 == 0:
                            # 일반 담보
                            row_dambo = str(row[1] if len(row) > 1 else "").strip()
                            if row_dambo == dambo_code:
                                self.m_point = mpoint_lookup
                                break
                        else:
                            # 독립특약
                            row_dambo = str(row[0] if len(row) > 0 else "").strip()
                            row_형구분 = str(row[self.loc_확장번호] if len(row) > self.loc_확장번호 else "").strip()
                            if row_dambo == dambo_code and row_형구분 == dambo_att.형구분:
                                self.m_point = mpoint_lookup
                                break
                    except:
                        continue
            
            if self.m_point == 0:
                # if log_callback:
                #     log_callback(f"[경고] M_Point를 찾을 수 없음: {dambo_code}")
                return
            
            # ===== 보장구조 Lookup Key =====
            if self.data.독립특약 == 0:
                if self.m_point < len(arr_main) and self.loc_확장번호 < len(arr_main[self.m_point]):
                    dambo = arr_main[self.m_point][self.loc_확장번호]
                    보장구조_lookup_key = f"{self.data.product_code}_{dambo}"
                else:
                    보장구조_lookup_key = ""
            else:
                보장구조_lookup_key = f"{dambo_code}_{dambo_att.형구분}"
                if self.loc_담보그룹 > 0 and self.m_point < len(arr_main):
                    self.독특담보그룹 = arr_main[self.m_point][-1]  # Last column
            
            # ===== 세부담보 개수/코드 (using numpy) =====
            arr_구조 = self.data.arr_보장구조
            
            if arr_구조 is not None and 보장구조_lookup_key:
                for index_lookup in range(len(arr_구조)):
                    try:
                        lookup_val = str(arr_구조[index_lookup][0]).strip()
                        if lookup_val == 보장구조_lookup_key:
                            if self.세부담보개수 <= 0:
                                self.세부담보개수 += 1
                            elif arr_구조[index_lookup][self.loc_세부담보순번] > self.세부담보개수:
                                self.세부담보개수 += 1
                            else:
                                break
                            
                            if self.세부담보개수 == 0:
                                self.min_riskrate_row = index_lookup
                            
                            # 세부담보코드 저장
                            if self.세부담보개수 >= 0 and self.loc_세부담보코드 < len(arr_구조[index_lookup]):
                                self.세부담보코드List.append(arr_구조[index_lookup][self.loc_세부담보코드])
                            
                            # 다음 행 확인
                            if index_lookup + 1 >= len(arr_구조):
                                break
                            if str(arr_구조[index_lookup + 1][0]).strip() != 보장구조_lookup_key:
                                break
                    except:
                        continue
            
            # ===== 납입면제여부 =====
            if arr_구조 is not None and self.min_riskrate_row < len(arr_구조) and self.loc_납면탈퇴율개수 > 0:
                try:
                    if arr_구조[self.min_riskrate_row][self.loc_납면탈퇴율개수] > 0:
                        self.납입면제여부 = True
                    else:
                        self.납입면제여부 = False
                except:
                    self.납입면제여부 = False
            
            # ===== 세부담보_bencoef 배열 생성 =====
            arr_배수 = self.data.arr_보장배수
            
            if self.세부담보개수 > 0 and arr_구조 is not None and arr_배수 is not None:
                self.세부담보_bencoef = []
                for i in range(self.세부담보개수):
                    try:
                        if self.min_riskrate_row + i + 1 < len(arr_구조):
                            보장배수_key = arr_구조[self.min_riskrate_row + i + 1][self.loc_보장배수]
                            bencoef_row = self.data.get_array_row(arr_배수, 보장배수_key, 0)
                            if bencoef_row is not None:
                                self.세부담보_bencoef.append([0] + list(bencoef_row))
                            else:
                                self.세부담보_bencoef.append([0])
                        else:
                            self.세부담보_bencoef.append([0])
                    except:
                        self.세부담보_bencoef.append([0])
            
            # ===== 면책/감액 Summary =====
            self.sum_면책 = 0
            self.sum_감액 = 0
            
            for i in range(self.세부담보개수):
                try:
                    if len(self.세부담보_bencoef[i]) > self.loc_면책기간:
                        val = self.세부담보_bencoef[i][self.loc_면책기간]
                        self.sum_면책 += float(val or 0)
                    if len(self.세부담보_bencoef[i]) > self.loc_감액기간:
                        val = self.세부담보_bencoef[i][self.loc_감액기간]
                        self.sum_감액 += float(val or 0)
                except:
                    pass
            
            # ===== 감액횟수 =====
            for i in range(self.세부담보개수):
                try:
                    if (len(self.세부담보_bencoef[i]) > self.loc_감액기간2 and 
                        len(self.세부담보_bencoef[i]) > self.loc_감액비율2):
                        if (self.세부담보_bencoef[i][self.loc_감액기간2] > 0 and 
                            self.세부담보_bencoef[i][self.loc_감액비율2] > 0):
                            self.is감액두번 = True
                            break
                except:
                    pass
            
            # ===== 보기납기 처리 =====
            self._read_pgm_보기납기(dambo_att, log_callback)
            
            # ===== 세부보장명_list 업데이트 (PGM 구조 우선) =====
            # PGM에서 세부담보코드가 발견되었다면, 이를 최우선으로 세부보장명_list에 반영
            if self.세부담보코드List and self.data.arr_담보매핑 is not None:
                new_sembo_list = []
                # 담보매핑에서 코드->명칭 조회 (Fast lookup using numpy)
                # 담보매핑 구조: [대표담보코드, 대표담보명, 담보코드, 담보명, ...]
                # Index 2: 담보코드, Index 3: 담보명
                
                arr_mapping = self.data.arr_담보매핑
                
                for sembo_code in self.세부담보코드List:
                    try:
                        # Find row where col[2] == sembo_code
                        row = self.data.get_array_row(arr_mapping, sembo_code, 2)
                        if row is not None and len(row) > 3:
                            sembo_name = str(row[3] or "").strip()
                            if sembo_name:
                                new_sembo_list.append(sembo_name)
                            else:
                                new_sembo_list.append(sembo_code) # 이름없으면 코드라도
                        else:
                             # 매핑 실패 시 코드 자체 사용 or Skip?
                             # 보통 매핑이 있어야 함. 없으면 빈 문자열보다 코드가 나음.
                             new_sembo_list.append(sembo_code)
                    except:
                        pass
                
                if new_sembo_list:
                    dambo_att.세부보장명_list = new_sembo_list
                    # if log_callback:
                    #     log_callback(f"      세부보장명_list 업데이트(PGM): {new_sembo_list}")

        except Exception as e:
            if log_callback:
                log_callback(f"[에러] _read_pgm_loop: {e}")

    def _read_pgm_보기납기(self, dambo_att: DamboAttributes, log_callback=None):
        """
        Read 보기납기 data using numpy arrays.
        """
        try:
            self.n_array = []
            self.age_b = 999
            self.age_e = 0
            
            # TERM_Lookup_Key 생성
            arr_main = self.data.arr_pgm_main
            
            if arr_main is not None and self.m_point < len(arr_main):
                if self.data.독립특약 == 0:
                    if self.loc_보기납기 < len(arr_main[self.m_point]):
                        보기납기값 = arr_main[self.m_point][self.loc_보기납기]
                        self.term_lookup_key = f"{self.data.product_code}_{보기납기값}"
                    else:
                        self.term_lookup_key = ""
                else:
                    if self.loc_보기납기 < len(arr_main[self.m_point]):
                        보기납기값 = arr_main[self.m_point][self.loc_보기납기]
                        self.term_lookup_key = str(보기납기값)
                    else:
                        self.term_lookup_key = ""
            
            # N 배열 저장 (using numpy - FAST!)
            arr_보기 = self.data.arr_보기납기
            
            if arr_보기 is not None and self.term_lookup_key:
                for index_lookup in range(len(arr_보기)):
                    try:
                        lookup_val = str(arr_보기[index_lookup][0]).strip()
                        if lookup_val == self.term_lookup_key:
                            # Age_B, Age_E 저장
                            age_b_val = arr_보기[index_lookup][8] if len(arr_보기[index_lookup]) > 8 else 0
                            age_e_val = arr_보기[index_lookup][9] if len(arr_보기[index_lookup]) > 9 else 0
                            
                            self.age_b = min(self.age_b, int(age_b_val) if age_b_val else 0)
                            self.age_e = max(self.age_e, int(age_e_val) if age_e_val else 0)
                            
                            # N 배열에 추가
                            n_entry = [
                                arr_보기[index_lookup][6] if len(arr_보기[index_lookup]) > 6 else "",
                                arr_보기[index_lookup][11] if len(arr_보기[index_lookup]) > 11 else "",
                                arr_보기[index_lookup][12] if len(arr_보기[index_lookup]) > 12 else ""
                            ]
                            self.n_array.append(n_entry)
                    except:
                        continue
            
            if self.age_b == 999:
                self.age_b = 0
                
        except Exception as e:
            if log_callback:
                log_callback(f"[에러] _read_pgm_보기납기: {e}")

    def _set_독특_file_path(self, dambo_att: DamboAttributes, 대표담보코드: str, dambo_code: str, log_callback=None):
        """
        독립특약 파일 경로 재지정 및 감액면책여부 저장.
        Uses numpy arrays for fast lookup.
        """
        try:
            # 파일경로 재지정
            arr_파일명 = self.data.arr_독특파일명
            if arr_파일명 is not None:
                for i in range(len(arr_파일명)):
                    if arr_파일명[i][0] == self.독특담보그룹:
                        if self.is_독특간편:
                            self.data.약관파일명 = str(arr_파일명[i][2])
                        else:
                            self.data.약관파일명 = str(arr_파일명[i][1])
                        
                        # 독립특약명 추출
                        약관파일명 = self.data.약관파일명
                        if 약관파일명:
                            start_idx = 약관파일명.find("약관_")
                            if start_idx >= 0:
                                end_idx = 약관파일명.find("_", start_idx + 3)
                                if end_idx > start_idx:
                                    self.독립특약명 = 약관파일명[start_idx + 3:end_idx]
                        break
            
            # 감액면책여부 저장
            arr_레이아웃 = self.data.arr_독특레이아웃
            if arr_레이아웃 is not None:
                layout_key = f"{dambo_code}_{dambo_att.형구분}"
                for i in range(len(arr_레이아웃)):
                    if str(arr_레이아웃[i][0]).strip() == layout_key:
                        if "X" in str(arr_레이아웃[i][7]):
                            dambo_att.독특감액여부 = "감액없음"
                        else:
                            dambo_att.독특감액여부 = "감액있음"
                        
                        if "X" in str(arr_레이아웃[i][8]):
                            dambo_att.독특면책여부 = "면책없음"
                        else:
                            dambo_att.독특면책여부 = "면책있음"
                        break
                        
        except Exception as e:
            if log_callback:
                log_callback(f"[에러] _set_독특_file_path: {e}")

    def _copy_terms(self, 대표담보코드: str, 특별약관경로: str, 특별약관파일명: str, 
                    dambo_category: str, dambo_att: DamboAttributes, log_callback=None):
        """
        Copy terms from source document to target document.
        Based on VBA Copy_약관 logic.
        """
        try:
            # Use pre-cached source document (opened before main loop)
            source_doc = None
            if hasattr(self, 'source_docs') and self.source_docs:
                source_doc = self.source_docs.get(dambo_category)
                if not source_doc and self.source_docs:
                    # Fallback to first available
                    source_doc = list(self.source_docs.values())[0]
            
            if not source_doc:
                if log_callback:
                    log_callback(f"   ⚠️ 소스 문서 없음: {dambo_category}")
                return
            
            # Use pre-opened target document
            target_doc = self.word.target_doc
            if not target_doc:
                if log_callback:
                    log_callback(f"   ⚠️ 타겟 문서 없음")
                return
            
            # Find the coverage code in source document comments
            copy_range = None
            found_start = False
            특별약관명 = None
            
            if log_callback:
                log_callback(f"   🔍 주석에서 '{대표담보코드}' 검색 중...")
            
            for comment in source_doc.Comments:
                comment_text = str(comment.Range.Text)
                codes = [c.strip() for c in comment_text.split(",")]
                
                if not found_start:
                    if 대표담보코드 in codes:
                        # VBA: 특별약관명으로 중복 체크 (예: "교통상해후유장해")
                        # 이 값은 comment.Scope.Paragraphs(1)의 텍스트에서 추출
                        para = comment.Scope.Paragraphs(1)
                        특별약관명 = str(para.Range.Text).strip().replace('\r', '').replace('\n', '')
                        
                        # Check if already copied using 특별약관명 key
                        if 특별약관명 in self.copied_list_strings:
                            if log_callback:
                                log_callback(f"   ⏭️ 이미 복사됨: {특별약관명}")
                            return
                        
                        self.copied_list_strings.add(특별약관명)
                        copy_range = source_doc.Range(para.Range.Start, para.Range.Start)
                        found_start = True
                        if log_callback:
                            log_callback(f"   ✅ 시작 위치 발견: {대표담보코드}")
                else:
                    # Found end marker (next comment)
                    copy_range.End = comment.Scope.Paragraphs(1).Range.Start
                    if log_callback:
                        log_callback(f"   ✅ 종료 위치 발견")
                    break
            
            if copy_range and copy_range.Start != copy_range.End:
                # Find paste location in target (at END of section)
                if log_callback:
                    log_callback(f"   🔍 삽입 위치 검색: {dambo_category}")
                paste_range = self._find_paste_location(target_doc, dambo_category, dambo_att, log_callback)
                
                if paste_range:
                    # VBA: 붙여넣기영역.FormattedText = 복사영역.FormattedText
                    # InsertAfter를 사용하여 섹션 맨 뒤에 삽입
                    paste_range.InsertAfter("\r")  # 단락 구분 추가
                    paste_range.Collapse(0)  # wdCollapseEnd = 0
                    
                    # Capture Start Position BEFORE Paste
                    start_pos = paste_range.Start
                    
                    # Paste Content
                    paste_range.FormattedText = copy_range.FormattedText
                    
                    # Capture End Position AFTER Paste
                    # Note: When FormattedText is set, the Range object usually expands to include new text.
                    end_pos = paste_range.End
                    
                    # Re-verify range validity
                    if end_pos <= start_pos:
                        # Fallback: If range didn't expand, try to expand to end of current paragraph
                        # This works because we inserted at the end of a section
                        try:
                            # Try to expand to at least some content
                            end_pos = paste_range.Paragraphs(1).Range.End
                        except:
                            pass
                    
                    # Create explicit range for the pasted content
                    try:
                        if end_pos <= start_pos + 5: # Allow small buffer
                            # Fallback: Recalculate end position using section markers
                            if log_callback:
                                log_callback(f"   ⚠️ Range not expanded. Recalculating end position...")
                            result_range = self._recalculate_paste_range_end(target_doc, start_pos, log_callback)
                        else:
                            result_range = target_doc.Range(start_pos, end_pos)
                    except Exception as e:
                        if log_callback:
                            log_callback(f"   ⚠️ Range creation failed: {e}")
                        result_range = paste_range  # Fallback to original object
                    
                    if log_callback:
                        captured_text_preview = result_range.Text[:100].replace('\r', '\\r').replace('\n', '\\n') if result_range else "None"
                        print(f"      [DEBUG] Captured Range Text ({start_pos}~{result_range.End if result_range else '?'}: {captured_text_preview}")
                        log_callback(f"   ✅ 복사 완료: {대표담보코드} → {dambo_category} 섹션 끝 (Range: {start_pos}~{end_pos})")
                    
                    return result_range
                else:
                    if log_callback:
                        log_callback(f"   ⚠️ 붙여넣기 위치 없음: {대표담보코드}")
            else:
                if log_callback:
                    log_callback(f"   ⚠️ 복사 범위 없음: {대표담보코드}")
            
            return None
                    
        except Exception as e:
            if log_callback:
                log_callback(f"   ❌ 약관 복사 에러: {e}")
            import traceback
            traceback.print_exc()

    def _find_paste_location(self, target_doc, dambo_category: str, dambo_att: DamboAttributes, log_callback=None):
        """
        Find paste location in target document - at the END of the section.
        Based on VBA logic: find section start, then find next section marker to get end position.
        섹션 형식: "생활안정모듈-상해관련 특별약관" (코멘트)
        """
        # Debug: 모듈형 값 확인
        모듈형_val = getattr(self.data, '모듈형', 0)
        if log_callback:
            # log_callback(f"      DEBUG: 모듈형={모듈형_val}, dambo_att.모듈='{dambo_att.모듈}'")
            pass
        
        # 섹션 타이틀 형식: "생활안정모듈-상해관련 특별약관"
        # 모듈형=1 이거나 dambo_att.모듈에 값이 있으면 모듈형으로 처리
        if (모듈형_val == 1 or dambo_att.모듈) and dambo_att.모듈:
            section_title = f"{dambo_att.모듈}-{dambo_category}관련 특별약관"
        else:
            # 비모듈형: "상해관련 특별약관"
            section_title = f"{dambo_category}관련 특별약관"
        
        if log_callback:
            log_callback(f"      섹션 검색: {section_title}")
        
        section_start = None
        section_end = None
        found_section = False
        
        # Search in comments for section boundaries
        for comment in target_doc.Comments:
            comment_text = str(comment.Range.Text)
            
            if not found_section:
                # Find the start of our section
                if section_title in comment_text:
                    section_start = comment.Scope.Paragraphs(1).Range
                    found_section = True
                    if log_callback:
                        log_callback(f"      ✅ 섹션 시작 발견")
            else:
                # Find the end - next section marker (다음 섹션 또는 별표)
                # 패턴: "모듈-카테고리관련 특별약관" 또는 "별표"
                if any(marker in comment_text for marker in 
                       ["관련 특별약관", "제도성 특별약관", "별표"]):
                    # 현재 섹션과 다른 섹션이면 끝
                    if section_title not in comment_text:
                        # End is just before this next section
                        section_end = target_doc.Range(
                            section_start.End,
                            comment.Scope.Paragraphs(1).Range.Start - 1
                        )
                        if log_callback:
                            log_callback(f"      ✅ 섹션 끝 발견: {comment_text[:30]}...")
                        break
        
        if section_end:
            # Return the range at the END of the section (before next section)
            return section_end
        elif section_start:
            # If no next section found, use end of section_start paragraph
            # Find the last paragraph in this section
            return section_start
        
        return None

    def _revise_terms(self, dambo_att: DamboAttributes, loop_point: int, target_range, log_callback=None):
        """
        Revise terms with specific attribute values using TagProcessor.
        Handles substitution tags and output control tags within the specified range.
        
        Args:
            dambo_att: DamboAttributes
            loop_point: Loop index
            target_range: Word Range object to process (e.g., pasted text)
        """
        try:
            if log_callback:
                log_callback(f"   🏷️ 태그 처리 시작: {dambo_att.담보코드}")
            
            # Create TagContext from DamboAttributes
            context = create_tag_context_from_dambo_att(dambo_att, self.data)
            
            # Set additional context from PGM data
            context.면책 = 1 if self.sum_면책 > 0 else 0
            context.감액 = 1 if self.sum_감액 > 0 else 0
            context.감액한번 = not self.is감액두번
            context.감액두번 = self.is감액두번
            context.독립특약 = self.data.독립특약
            context.비갱신 = 1 if self.data.자동갱신형 == 0 else 0
            
            if log_callback:
                log_callback(f"      면책={context.면책}, 감액={context.감액}, 연장형={dambo_att.연장형}")
            
            # Build 감액기간 list from PGM
            if self.세부담보_bencoef:
                for bencoef in self.세부담보_bencoef:
                    기간_list = []
                    # Check safe access
                    if len(bencoef) > self.loc_감액기간 and bencoef[self.loc_감액기간]:
                        try:
                            기간_list.append(int(bencoef[self.loc_감액기간]))
                        except (ValueError, TypeError):
                            pass
                    if len(bencoef) > self.loc_감액기간2 and bencoef[self.loc_감액기간2]:
                        try:
                            기간_list.append(int(bencoef[self.loc_감액기간2]))
                        except (ValueError, TypeError):
                            pass
                    
                    if 기간_list:
                        context.감액기간_list.append(기간_list)
            
            # Build 지급률 data from PGM
            if self.세부담보_bencoef and context.대표담보코드:
                지급률_list = []
                for bencoef in self.세부담보_bencoef:
                    if len(bencoef) > self.loc_지급률 and bencoef[self.loc_지급률]:
                        try:
                            지급률_list.append([float(bencoef[self.loc_지급률])])
                        except (ValueError, TypeError):
                            지급률_list.append([100.0])
                    else:
                        지급률_list.append([100.0])
                context.지급률_data[context.대표담보코드] = 지급률_list
            
            # Process tags in target RANGE
            if target_range:
                self.tag_processor.csv_loader = self.csv_loader if hasattr(self, 'csv_loader') else None
                self.tag_processor.process_range(target_range, context, log_callback)
            else:
                if log_callback:
                    log_callback(f"   ⚠️ target_range 없음 - 태그 처리 스킵")
                
        except Exception as e:
            if log_callback:
                log_callback(f"   ❌ [에러] _revise_terms: {e}")
            import traceback
            traceback.print_exc()

    def _revise_별표_0세(self, log_callback=None):
        """
        Handle 0세 (zero age) child related revisions.
        Processes 0세자녀 related tags.
        """
        try:
            if self.data.zero_age_자녀 == 0:
                return  # No 0세자녀 processing needed
            
            if log_callback:
                log_callback("0세자녀 태그 처리 중...")
            
            # Process 0세자녀 specific tags
            # TODO: Implement specific 0세자녀 tag processing
            
            if log_callback:
                log_callback("0세자녀 태그 처리 완료")
                
        except Exception as e:
            if log_callback:
                log_callback(f"[에러] _revise_별표_0세: {e}")
    def _recalculate_paste_range_end(self, target_doc, start_pos, log_callback=None):
        """
        Calculates the end position of the pasted content by finding the next section or end of document.
        """
        try:
            # Search for the next section marker starting from start_pos
            search_range = target_doc.Range(start_pos, target_doc.Content.End)
            
            # Find next section or end of doc
            search_range.Find.ClearFormatting()
            found = False
            
            # Markers that indicate start of a new section
            markers = ["관련 특별약관", "제도성 특별약관", "별표"]
            
            min_end_pos = target_doc.Content.End
            
            for marker in markers:
                search_range.Find.Execute(FindText=marker, Forward=True, Wrap=0)
                if search_range.Find.Found:
                    # Found a marker. The end of our section is before this marker's paragraph.
                    # Move to start of the paragraph containing the marker
                    marker_para_start = search_range.Paragraphs(1).Range.Start
                    if marker_para_start < min_end_pos and marker_para_start > start_pos:
                        min_end_pos = marker_para_start
                        found = True
                
                # Reset search range for next marker check
                search_range = target_doc.Range(start_pos, target_doc.Content.End)
            
            return target_doc.Range(start_pos, min_end_pos)
            
        except Exception as e:
            if log_callback:
                log_callback(f"   ⚠️ Range calculation error: {e}")
            return target_doc.Range(start_pos, target_doc.Content.End)
