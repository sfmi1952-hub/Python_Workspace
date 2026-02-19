
import pandas as pd
import json
import tempfile
import os
import shutil
import google.generativeai as genai
import pypdf
from .gemini_core import GeminiCore

class DiagnosisMapper:
    def __init__(self, api_key):
        self.client = GeminiCore(api_key)

    def extract_text_from_pdf(self, pdf_path):
        try:
            reader = pypdf.PdfReader(pdf_path)
            text = []
            for page in reader.pages:
                text.append(page.extract_text() or "")
            return "\n".join(text)
        except Exception as e:
            print(f"PDF Text Extraction Failed: {e}")
            return ""

    def process(self, target_pdf, target_excel, code_mapping_excel, ref_files=[], logger=print):
        try:
            # 1. Read Inputs
            logger(f"Using Gemini Model: {self.client.get_model_name()}")
            logger("Reading Excel inputs...")
            
            # Target Benefit List (Output of Step 1)
            df_target = pd.read_excel(target_excel)
            if '세부담보템플릿명' not in df_target.columns:
                return {"error": "Target Excel missing '세부담보템플릿명' column."}
            
            # Code Mapping Table
            df_code = pd.read_excel(code_mapping_excel)
            code_mapping_csv = df_code.to_csv(index=False) 
            
            # Prepare Benefit List for Prompt
            benefits_data = df_target[['담보명_출력물명칭', '세부담보템플릿명']].dropna().to_dict(orient='records')
            
            files_to_clean = []
            
            # --- PHASE 1: Rule Extraction (RAG from Reference Pairs) ---
            mapping_logic_text = ""
            grouped_refs = self._group_files_by_pair(ref_files)
            
            if grouped_refs:
                logger(f"Phase 1: Extracting 'Inference Logic' from {len(grouped_refs)} reference groups...")
                
                rule_prompt = f"""
                **Role**: 보험 약관 분석 전문가 및 진단 코딩 전략 수립가.
                
                **Goal**: 
                제공된 참조 문서(약관 및 담보 테이블)와 진단코드 매핑테이블(Code Mapping Table)을 분석하여, 향후 Phase 2에서 **'담보명'과 '세부담보템플릿명'으로부터 정확한 '진단코드(분류번호)'를 도출할 수 있도록 돕는 추론 로직(Inference Logic)**을 추출하세요.
                
                **Reference Context**:
                - **Code Mapping Table (Reference)**:
                {code_mapping_csv}
                
                **Instructions**:
                - 단순히 내용을 요약하지 말고, **"이 담보의 진단 범위를 약관에서 어떻게 식별하고, 매핑 테이블의 어떤 코드와 연결해야 하는가?"**에 집중하세요.
                - 특히 약관 본문에 **'별표(Appendix)'** 혹은 **'부속서'**를 참조하라는 안내가 있는지 확인하고, 문서 뒷부분에 위치할 수 있는 해당 별표의 진단 정의(KCD 기호 등)를 찾아 로직에 포함하세요.
                - 약관에 명시된 질병 기호(KCD 등)나 정의 문구가 매핑 테이블의 '분류번호'와 어떻게 매칭되는지 패턴을 분석하세요.
                
                **Output Requirements (최대한 자세히 기술하세요)**:
                1. **담보별 진단 정의 분석 (Diagnosis Definition Patterns)**:
                   - 해당 세부담보템플릿이 보장하는 질병의 약관상 정의 및 핵심 키워드.
                   - (중요) 관련 '별표' 번호 및 해당 별표에 명시된 주요 KCD 코드 범위.
                2. **코드 매핑 로직 (Code Mapping Strategy)**:
                   - 약관상 정의된 질병 범위가 매핑 테이블의 어느 '분류번호' 범위에 해당하는지 기술.
                   - 예: "약관에서 정의한 '암'의 범위(C00~C97) -> 매핑 테이블상 '일반암' 분류번호(0A1)로 매핑"
                3. **포함/제외 세부 조건 (Inclusion/Exclusion Rules)**:
                   - 특정 코드 제외 혹은 특정 상태(갱신형 등)에 따른 코드 변형 규칙.
                4. **위치 및 문맥 단서 (Context Clues)**:
                   - 진단 정의가 주로 등장하는 조항 위치나 문서 내 표현 방식.
                """

                for group_name, paths in grouped_refs.items():
                    logger(f"  > Processing Group: {group_name}...")
                    current_group_files = []
                    try:
                        for p in paths:
                            logger(f"    - Preparing file: {os.path.basename(p)}")
                            f = self.client.upload_file(p, logger=logger)
                            current_group_files.append(f)
                            files_to_clean.append(f)
                        
                        logger(f"    - Extracting rules for {group_name} via Gemini...")
                        rule_resp = self.client.model.generate_content(
                            [rule_prompt] + current_group_files,
                            request_options={'timeout': 600}
                        )
                        mapping_logic_text += f"\n\n=== [Mapping Logic: {group_name}] ===\n{rule_resp.text}\n"
                        logger(f"    - Rules extracted for {group_name}.")
                        
                    except Exception as e:
                        logger(f"    ❌ Error RAG Group {group_name}: {e}")
            else:
                logger("Phase 1 Skipped (No reference files provided or grouped).")

            # Upload Target PDF
            t_pdf = self.client.upload_file(target_pdf, mime_type='application/pdf', logger=logger)
            files_to_clean.append(t_pdf)

            # --- PHASE 2: Infer Diagnosis Codes ---
            logger(f"Phase 2: Inferring Diagnosis Codes for {len(benefits_data)} items...")
            
            results = []
            
            # Prepare all items string
            all_items_str = "\n".join([f"- 담보명: {b['담보명_출력물명칭']}, 세부담보템플릿명: {b['세부담보템플릿명']}" for b in benefits_data])
            
            prompt = f"""
            **Task**: 제공된 '담보명'과 '세부담보템플릿명'을 검토하고, 타겟 약관과 매핑 테이블을 바탕으로 정확한 **'진단코드(분류번호)'**를 추론하세요.

            **Input Benefit List**:
            {all_items_str}
            
            **Code Mapping Table (Current Reference)**:
            {code_mapping_csv}
            
            **Mapping Rules (참조 문서에서 추출한 추론 가이드라인 - 필독)**:
            {mapping_logic_text}
            
            **Instructions**:
            1. 입력된 '담보명'과 '세부담보템플릿명' 쌍을 순서대로 분석하세요.
            2. **약관 내 '별표(Appendix)' 우선 참조**: 약관 본문에서 특정 진단에 대해 '별표'를 참조하라고 되어 있다면, 해당 별표 페이지를 찾아 그 안의 질병 기호(KCD)를 최우선 근거로 삼으세요.
            3. **외부 지식 활용(Search Fallback)**: 만약 타겟 약관 내에서 직접적인 KCD 코드나 별표 정보를 찾을 수 없는 경우, 해당 담보명에 대한 **표준 KCD(한국표준질병사인분류) 지식**을 활용(검색 결과로 간주)하여 가장 타당한 범위를 도출하고, 이를 매핑 테이블의 '분류번호'와 매칭하세요.
            4. **input_template_name**: 입력 목록에 있는 '세부담보템플릿명'을 그대로 반환하세요.
            5. **inferred_code (추론된 진단코드)**:
               - 타겟 약관(특히 별표) 및 외부 KCD 정보를 활용하여 가장 적절한 **'분류번호'**를 선택하세요.
               - 매칭되는 코드가 명확하지 않은 경우, 가장 근접한 분류를 선택하거나 빈칸("")으로 두세요.
            6. **ref_sentence (근거 문장)**:
               - 약관 또는 별표에서 찾은 **진단 정의 문장 원문**을 그대로 기입하세요.
               - 외부 지식을 활용한 경우 "[외부 지식: KCD 분류 기준 상 ...에 해당함]" 형식으로 기입하세요.
               - 문장 뒤에 **[선정 이유]**를 덧붙여주세요.
            7. **ref_page**: 해당 내용이 위치한 타겟 약관의 페이지 번호를 숫자로 기입하세요. (외부 지식인 경우 '0' 기입)
            
            **Output JSON**:
            [
              {{
                "benefit_name": "입력된 담보명",
                "template_name": "입력된 세부담보템플릿명",
                "inferred_code": "분류번호 (예: 0A1)", 
                "ref_page": "페이지번호",
                "ref_sentence": "문장 원문 [선정 이유]"
              }}
            ]
            """
            
            try:
                response = self.client.model.generate_content(
                    [prompt, t_pdf],
                    request_options={'timeout': 600}
                )
                raw = response.text.replace("```json", "").replace("```", "").strip()
                batch_res = json.loads(raw)
                if isinstance(batch_res, list):
                    results.extend(batch_res)
            except Exception as e:
                logger(f"    ❌ Error during inference: {e}")

            # Map results back to DataFrame
            res_dict = {(r.get('benefit_name'), r.get('template_name')): r for r in results}
            
            def get_val(row, key):
                k = (row['담보명_출력물명칭'], row['세부담보템플릿명'])
                return res_dict.get(k, {}).get(key, '')

            df_target['Inferred_Diagnosis_Code'] = df_target.apply(lambda r: get_val(r, 'inferred_code'), axis=1)
            
            # 진단분류설명 추가 (코드매핑 테이블에서 맵핑) - 추론된 진단코드 항목 뒤에 추가
            if '코드값' in df_code.columns and '진단분류설명' in df_code.columns:
                code_to_desc = dict(zip(df_code['코드값'].astype(str).str.strip(), df_code['진단분류설명'].astype(str).str.strip()))
                df_target['진단분류설명'] = df_target['Inferred_Diagnosis_Code'].astype(str).str.strip().map(code_to_desc).fillna('')
            else:
                logger("Warning: '코드값' or '진단분류설명' columns not found in mapping table.")
                df_target['진단분류설명'] = ''

            df_target['Code_Mapping_Reason'] = df_target.apply(lambda r: get_val(r, 'ref_sentence'), axis=1)
            df_target['Ref_Page'] = df_target.apply(lambda r: get_val(r, 'ref_page'), axis=1)
            
            # Save Output Excel
            fd_exc, out_path = tempfile.mkstemp(suffix=".xlsx")
            os.close(fd_exc)
            df_target.to_excel(out_path, index=False)

            # Save Mapping Logic Text
            mapping_logic_path = ""
            if mapping_logic_text:
                fd_txt, mapping_logic_path = tempfile.mkstemp(suffix=".txt")
                with os.fdopen(fd_txt, 'w', encoding='utf-8') as f:
                    f.write(mapping_logic_text)

            # Cleanup
            for f in files_to_clean:
                try: genai.delete_file(f.name)
                except: pass
                
            return {
                "file_path": out_path,
                "logic_path": mapping_logic_path,
                "preview": df_target.head(50).fillna("").to_dict(orient='records')
            }

        except Exception as e:
            logger(f"Error: {e}")
            import traceback
            logger(traceback.format_exc())
            return {"error": str(e)}

    def _group_files_by_pair(self, file_paths):
        groups = {}
        for f in file_paths:
            base = os.path.splitext(os.path.basename(f))[0]
            if base not in groups:
                groups[base] = []
            groups[base].append(f)
        return groups
