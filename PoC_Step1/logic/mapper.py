import pandas as pd
import json
import tempfile
import os
import shutil
import google.generativeai as genai
import pypdf
from .gemini_core import GeminiCore

class BenefitMapper:
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

    def _group_files_by_pair(self, file_paths):
        """
        Groups files by their base name (excluding extension).
        Returns a dictionary: { "base_name": [file_path1, file_path2] }
        """
        groups = {}
        for f in file_paths:
            base = os.path.splitext(os.path.basename(f))[0]
            if base not in groups:
                groups[base] = []
            groups[base].append(f)
        return groups

    def process(self, target_pdf, target_excel, ref_files=[], logger=print):
        try:
            # 1. Read Excel
            logger(f"Using Gemini Model: {self.client.get_model_name()}")
            logger("Reading Excel...")
            df = pd.read_excel(target_excel)
            if '담보명_출력물명칭' not in df.columns or '세부담보템플릿명' not in df.columns:
                return {"error": "Excel missing columns '담보명_출력물명칭' or '세부담보템플릿명'"}
            
            # Create a list of dictionaries for the prompt
            benefits_data = df[['담보명_출력물명칭', '세부담보템플릿명']].dropna().to_dict(orient='records')
            benefit_str = "\n".join([f"- Benefit: {b['담보명_출력물명칭']}, Template: {b['세부담보템플릿명']}" for b in benefits_data])
            
            files_to_clean = []
            
            # --- PHASE 1: Rule Extraction (Per Pair) ---
            mapping_logic_text = ""
            grouped_refs = self._group_files_by_pair(ref_files)
            
            if grouped_refs:
                logger(f"Phase 1: Extracting logic from {len(grouped_refs)} reference groups...")
                
                rule_prompt = """
                **Role**: 보험 약관 분석 전문가 및 검색 전략 수립가.
                
                **Goal**: 
                제공된 참조 문서(약관 및 담보 테이블)를 분석하여, 향후 Phase 2에서 **'담보명'과 '세부담보템플릿명'에 해당하는 약관 내용을 정확히 찾아낼 수 있도록 돕는 검색 단서(Search Clues)와 전략**을 추출하세요.
                
                **Instructions**:
                - 단순히 내용을 요약하지 말고, **"이 담보를 찾으려면 약관에서 어떤 키워드를 봐야 하는가?"**에 집중하세요.
                - '세부담보템플릿명'이 실제 약관 텍스트로는 어떻게 표현되는지 패턴을 분석하세요.
                
                **Output Requirements (다음 항목을 포함하여 최대한 자세히 기술하세요)**:
                1. **핵심 검색 키워드 (Critical Keywords)**: 
                   - 해당 세부담보템플릿을 식별하기 위해 약관에서 반드시 찾아야 할 단어, 문구, 혹은 조항 명칭.
                   - 예: "암진단비(유사암제외)" 템플릿 -> 약관 내 "소액암", "제자리암", "경계성종양" 등의 키워드 확인 필요.
                
                2. **동의어 및 표현 변형 (Synonyms & Aliases)**:
                   - 템플릿명이 약관에서는 다르게 표현되는 경우 (예: "뇌졸중" -> "뇌출혈 및 뇌경색증").
                
                3. **포함/제외 조건 (Inclusion/Exclusion Candidates)**:
                   - 특정 템플릿으로 매핑하기 위한 결정적 조건 (예: "갱신형" 텍스트가 있으면 '갱신형 템플릿' 선택).
                
                4. **위치 단서 (Location Clues)**:
                   - 해당 담보가 주로 등장하는 약관의 섹션이나 맥락 (예: "보통약관 제3조", "특별약관 파트").
                
                이 분석 결과는 Phase 2에서 AI가 타겟 약관을 뒤질 때 **네비게이션 지도** 역할을 할 것입니다.
                """

                for group_name, paths in grouped_refs.items():
                    logger(f"  > Processing Group: {group_name} ({len(paths)} files)...")
                    
                    # Upload files for this group
                    current_group_files = []
                    try:
                        # Attempt 1: Upload Native Files
                        for p in paths:
                            f = self.client.upload_file(p)
                            current_group_files.append(f)
                            files_to_clean.append(f)
                        
                        logger(f"    - Analyzing {group_name}...")
                        rule_resp = self.client.model.generate_content(
                            [rule_prompt] + current_group_files,
                            request_options={'timeout': 600}
                        )
                        mapping_logic_text += f"\n\n--- Rules from {group_name} ---\n{rule_resp.text}"
                        
                    except Exception as e:
                        # Fallback logic for Token Limit / Error
                        err_msg = str(e)
                        if "token" in err_msg.lower() or "size" in err_msg.lower() or "limit" in err_msg.lower() or "499" in str(e):
                            logger(f"    ⚠️ Token/Size Limit (or Timeout) hit for {group_name}. Retrying with Text-Only conversion...")
                            
                            light_refs = []
                            for p in paths:
                                ext = os.path.splitext(p)[1].lower()
                                if ext == '.pdf':
                                    txt_content = self.extract_text_from_pdf(p)
                                    # TRUNCATION: Limit to ~200k chars to avoidTimeout
                                    if len(txt_content) > 200000:
                                        logger(f"    ⚠️ Truncating text for {os.path.basename(p)} (Size: {len(txt_content)} -> 200000)")
                                        txt_content = txt_content[:200000] + "...(TRUNCATED)"
                                    
                                    # Only use text if it has substantial content
                                    if len(txt_content) > 500:
                                        fd, txt_path = tempfile.mkstemp(suffix=".txt")
                                        os.close(fd)
                                        with open(txt_path, "w", encoding="utf-8") as f:
                                            f.write(f"--- TEXT CONTENT OF: {os.path.basename(p)} ---\n\n")
                                            f.write(txt_content)
                                        f_up = self.client.upload_file(txt_path, mime_type='text/plain')
                                        light_refs.append(f_up)
                                        files_to_clean.append(f_up)
                                else:
                                    # Excel/Text - re-upload or reuse? Reuse is hard if prev upload failed or we want fresh context
                                    f_up = self.client.upload_file(p)
                                    light_refs.append(f_up)
                                    files_to_clean.append(f_up)
                                    
                            if light_refs:
                                try:
                                    rule_resp = self.client.model.generate_content(
                                        [rule_prompt] + light_refs,
                                        request_options={'timeout': 600}
                                    )
                                    mapping_logic_text += f"\n\n--- Rules from {group_name} (Text Mode) ---\n{rule_resp.text}"
                                    logger(f"    - Retry Successful for {group_name}.")
                                except Exception as e2:
                                    logger(f"    ❌ Retry Failed for {group_name}: {e2}")
                            else:
                                logger(f"    ❌ No files to retry for {group_name}.")
                        else:
                            logger(f"    ❌ Error processing {group_name}: {e}")
            
                logger("Phase 1 Complete. Aggregated Rules extracted.")
            else:
                logger("Phase 1 Skipped (No reference files provided).")

            # --- PHASE 2: Application (Target + Rules) ---
            t_pdf = self.client.upload_file(target_pdf, mime_type='application/pdf')
            files_to_clean.append(t_pdf)
            
            logger(f"Phase 2: Applying rules to Target PDF for {len(benefits_data)} benefits...")

            # BATCH PROCESSING
            BATCH_SIZE = 20
            data = []
            
            total_batches = (len(benefits_data) + BATCH_SIZE - 1) // BATCH_SIZE
            
            for i in range(0, len(benefits_data), BATCH_SIZE):
                batch_number = (i // BATCH_SIZE) + 1
                batch_items = benefits_data[i : i + BATCH_SIZE]
                
                logger(f"  > Processing Batch {batch_number}/{total_batches} ({len(batch_items)} items)...")
                
                batch_str = "\n".join([f"- Benefit: {b['담보명_출력물명칭']}, Template: {b['세부담보템플릿명']}" for b in batch_items])
                
                prompt = f"""
                **Task**: 제공된 '담보명'과 '세부담보템플릿명'을 검토하고, 타겟 약관에서 이를 뒷받침하는 근거를 찾아 매핑을 검증/보완하세요.

                **Input Benefit List (Batch {batch_number}/{total_batches})**:
                {batch_str}
                
                **Mapping Rules (참조 문서에서 추출한 추론 가이드라인 - 참고용)**:
                {mapping_logic_text}
                
                **Instructions**:
                1. 입력된 '담보명'과 '세부담보템플릿명' 쌍을 순서대로 분석하세요.
                2. **input_template_name**: 입력 목록에 있는 '세부담보템플릿명'을 그대로 반환하세요 (매핑 기준 키로 사용됨).
                3. **inferred_template_name (추론된 템플릿명)**:
                   - 타겟 약관에서 '담보명'과 '세부담보템플릿명'의 연관성을 찾으세요.
                   - ** Mapping Rules (참조 문서 가이드라인)**을 적극 활용하여, **가장 적합한(Most Probable)** 템플릿명을 선택하세요.
                   - 매핑이 유효하다고 판단되면, **입력된 '세부담보템플릿명'을 그대로(Exact Copy)** 기입하세요. 절대 변형하거나 요약하지 마십시오.
                   - 100% 일치하지 않더라도, 문맥상 의미가 통하거나 참조 규칙에 부합하면 매핑하세요.
                   - 단, 전혀 관련 없는 경우에는 빈칸("")으로 두세요.
                4. **ref_sentence (근거 문장)**:
                   - 타겟 약관에서 찾은 **문장 원문**을 그대로 기입하세요.
                   - 문장 뒤에 **[선정 이유]**를 간략히 덧붙여주세요. (예: "...함. [이유: 약관 제3조에 해당 담보 명칭이 명시됨]")
                5. 해당 내용이 위치한 **페이지 번호**를 찾으세요.
                
                **Output JSON**:
                [
                  {{
                    "benefit_name": "입력된 담보명",
                    "input_template_name": "입력된 세부담보템플릿명",
                    "inferred_template_name": "추론된 템플릿명", 
                    "ref_page": "페이지번호",
                    "ref_sentence": "문장 원문 [선정 이유]"
                  }}
                ]
                """
                
                try:
                    # Send ONLY Target PDF + Rule Text
                    response = self.client.model.generate_content(
                        [prompt, t_pdf],
                        request_options={'timeout': 600}
                    )
                    
                    # Parse
                    raw = response.text.replace("```json", "").replace("```", "").strip()
                    batch_data = json.loads(raw)
                    if isinstance(batch_data, list):
                        data.extend(batch_data)
                    else:
                        logger(f"    ⚠️ Warning: Batch {batch_number} returned non-list JSON.")
                except Exception as e:
                    logger(f"    ❌ Error in Batch {batch_number}: {e}")

            # 6. Map back to DataFrame
            # Keying by (Benefit, Input Template) to handle multiple templates per benefit
            map_dict = {(item.get('benefit_name'), item.get('input_template_name')): item for item in data}
            
            def get_mapped_value(row, key_field):
                # Lookup using the composite key
                lookup_key = (row['담보명_출력물명칭'], row['세부담보템플릿명'])
                return map_dict.get(lookup_key, {}).get(key_field, '')

            df['Inferred_Template_Name'] = df.apply(lambda row: get_mapped_value(row, 'inferred_template_name'), axis=1)
            df['Reference_Page'] = df.apply(lambda row: get_mapped_value(row, 'ref_page'), axis=1)
            df['Reference_Sentence'] = df.apply(lambda row: get_mapped_value(row, 'ref_sentence'), axis=1)
            
            # 7. Save Excel
            fd, out_path = tempfile.mkstemp(suffix=".xlsx")
            os.close(fd)
            df.to_excel(out_path, index=False)
            
            # 8. Save Rules Text (if exists)
            rules_path = ""
            if mapping_logic_text:
                fd2, rules_path = tempfile.mkstemp(suffix=".txt")
                os.close(fd2)
                with open(rules_path, "w", encoding="utf-8") as f:
                    f.write(mapping_logic_text)

            # Cleanup
            for f in files_to_clean:
                try: genai.delete_file(f.name)
                except: pass
                
            return {
                "file_path": out_path,
                "rules_text": mapping_logic_text,
                "rules_file_path": rules_path,
                "preview": df.head(50).fillna("").to_dict(orient='records')
            }

        except Exception as e:
            logger(f"Error: {e}")
            return {"error": str(e)}
