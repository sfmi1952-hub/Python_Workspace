"""
진단코드(Inferred_Diagnosis_Code) 전용 비교 매퍼.

PoC_Step3의 2-Phase 추론 로직(별표 우선 → Few-Shot → 강건한 JSON 파싱)을
그대로 유지한 채, LLM 호출 함수만 외부에서 주입(provider) 받아
사외 SOTA LLM (Claude Opus 4.7) vs 사내 sLM (GPT-OSS) 을 같은 조건에서 비교합니다.
"""
import os
import re
import json
import time
import traceback
import pandas as pd

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

import pypdf


# ─────────────────────────────────────────────────────────────────────────────
# 진단코드 전용 ATTRIBUTE 설정 (PoC_Step3 의 첫 번째 항목과 동일)
# ─────────────────────────────────────────────────────────────────────────────
DIAGNOSIS_CONFIG = {
    "key": "Inferred_Diagnosis_Code",
    "name": "진단코드 (Diagnosis Code)",
    "mapping_files": ["1_진단분류코드", "진단분류", "FCDF131"],
    "phase1_instruction": """
- 약관 본문에서 '별표 X를 참조한다'는 문구를 찾고, 해당 별표에서 **KCD 코드 범위**(예: C00~C97)를 추출하세요.
- 매핑 테이블의 '분류번호'(예: 0A1)와 약관의 KCD 범위가 어떻게 연결되는지 패턴을 분석하세요.
- 제외 코드(예: C44 기타피부암, C73 갑상선암) 규칙을 반드시 포함하세요.
- 출력 JSON의 'rules' 배열 내 각 항목에 template_pattern, code, kcd_range, exclusions를 모두 기입하세요.
""",
    "phase2_instruction": """
- **별표(Appendix) 최우선**: 약관 본문에서 '별표'를 참조하라고 되어 있으면, 해당 별표 페이지를 찾아 KCD 코드 범위를 확인하세요.
- **외부 KCD 지식 활용**: 별표에서 찾을 수 없으면 표준 KCD(한국표준질병사인분류) 지식으로 대응 분류번호를 도출하세요.
- inferred_code는 매핑 테이블의 **분류번호**(예: 0A1) 형식으로 기입하세요. KCD 코드(C00 등) 직접 기입 금지.
""",
    "few_shot_example": """
**예시 입력**: 담보명: 암진단비 / 세부담보템플릿명: ZD_암진단_일반형
**예시 출력**:
{
  "benefit_name": "암진단비",
  "template_name": "ZD_암진단_일반형",
  "inferred_code": "0A1",
  "confidence": "high",
  "source": "appendix",
  "ref_page": "45",
  "ref_sentence": "이 특약에서 '암'이라 함은 별표[질병관련1]에서 정한 질병(C00~C97, C44·C73 제외)을 말합니다. [선정 이유] 별표 기준 진단분류코드 0A1 적용"
}
""",
}


class DiagnosisComparator:
    """
    같은 입력·같은 프롬프트로 두 모델을 호출해 결과를 비교 가능한 형태로 반환.
    provider 는 .generate(prompt_text, files=[paths], logger=...) 인터페이스를 구현해야 합니다.
    """

    def __init__(self, provider, provider_label):
        self.provider = provider
        self.label = provider_label
        self.token_usage = {"input": 0, "output": 0, "calls": 0}

    # ─────────────────────────────────────────────────────────────────────
    # PDF → 텍스트 추출 (PoC_Step3 와 동일: pdfplumber 우선, pypdf fallback, 캐시)
    # ─────────────────────────────────────────────────────────────────────
    def extract_text_from_pdf(self, pdf_path, cache_dir, logger=print):
        os.makedirs(cache_dir, exist_ok=True)
        filename = os.path.basename(pdf_path)
        cache_path = os.path.join(cache_dir, filename + ".md")

        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    logger(f"  > [Cache] Loaded: {filename}")
                    return f.read()
            except Exception:
                pass

        text_content = ""
        if pdfplumber:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                cleaned = [
                                    [str(cell) if cell else "" for cell in row]
                                    for row in table
                                ]
                                if len(cleaned) > 1:
                                    try:
                                        df_table = pd.DataFrame(cleaned[1:], columns=cleaned[0])
                                        text_content += "\n" + df_table.to_markdown(index=False) + "\n"
                                    except Exception:
                                        pass
                        else:
                            text_content += (page.extract_text() or "") + "\n"
                logger(f"  > [Extract] pdfplumber: {filename}")
            except Exception as e:
                logger(f"  > [Extract] pdfplumber 실패({e}), pypdf 폴백")
                text_content = ""

        if not text_content:
            try:
                with open(pdf_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    text_content = "\n".join([p.extract_text() or "" for p in reader.pages])
                logger(f"  > [Extract] pypdf: {filename}")
            except Exception as e:
                logger(f"  > [Extract] 실패 {pdf_path}: {e}")
                return ""

        if text_content:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(text_content)
            except Exception:
                pass
        return text_content

    # ─────────────────────────────────────────────────────────────────────
    # 강건한 JSON 파싱 (PoC_Step3 와 동일)
    # ─────────────────────────────────────────────────────────────────────
    def _parse_json_response(self, raw_text, logger=print):
        if not raw_text:
            return []
        cleaned = re.sub(r"```(?:json)?", "", raw_text).strip()
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1:
            return self._extract_objects(cleaned)
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            logger(f"  > [JSON] 1차 파싱 실패: {e} — 객체 추출 폴백")
            return self._extract_objects(cleaned)

    def _extract_objects(self, text):
        """중괄호 균형 기반 객체 추출 (정규식보다 안정적)."""
        results, depth, start = [], 0, -1
        for i, ch in enumerate(text):
            if ch == "{":
                if depth == 0:
                    start = i
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0 and start != -1:
                    chunk = text[start : i + 1]
                    try:
                        results.append(json.loads(chunk))
                    except Exception:
                        pass
                    start = -1
        return results

    # ─────────────────────────────────────────────────────────────────────
    # 매핑 컨텍스트 선택 (PoC_Step3 와 동일)
    # ─────────────────────────────────────────────────────────────────────
    def _select_mapping_context(self, maps_by_name):
        patterns = DIAGNOSIS_CONFIG["mapping_files"]
        selected = []
        for fname, content in maps_by_name.items():
            if any(p.lower() in fname.lower() for p in patterns):
                selected.append(content)
        if selected:
            return "\n".join(selected)
        return "[주의] 진단분류코드 매핑 테이블을 찾지 못했습니다."

    def _build_phase1_prompt(self, group_name, relevant_context):
        cfg = DIAGNOSIS_CONFIG
        return f"""
**Role**: 보험 약관 분석 전문가.

**Goal**: 참조 문서({group_name})를 분석하여 **'{cfg['name']}'** 추론에 필요한 규칙을 추출하고,
아래 JSON 형식으로만 출력하세요.

**Target Attribute**: {cfg['name']}

**Mapping Tables**:
{relevant_context}

**속성별 분석 지침**:
{cfg['phase1_instruction']}

**공통 지침**:
1. 오직 **'{cfg['name']}'** 추출 로직만 작성하세요. 다른 속성 내용은 절대 포함하지 마세요.
2. 약관에 '별표(Appendix)'가 있으면 **최우선**으로 확인하고 반영하세요.
3. 담보명과 세부담보템플릿명을 종합적으로 고려해야 하는 판단 기준을 포함하세요.

**출력 형식 (JSON만, 다른 텍스트 없음)**:
{{
  "attribute": "{cfg['name']}",
  "appendix_refs": ["별표[질병관련1]", ...],
  "context_clues": ["제N조에서 별표를 참조한다고 명시", ...],
  "rules": [
    {{
      "template_pattern": "담보명/템플릿명 패턴 (예: 암진단*)",
      "code": "매핑 코드 (예: 0A1)",
      "kcd_range": "KCD 범위 (해당 시, 예: C00-C97)",
      "exclusions": ["C44", "C73"],
      "note": "추가 조건 설명"
    }}
  ]
}}

유의미한 규칙이 없으면 rules 배열을 비워두세요.
"""

    def _build_phase2_prompt(self, logic_content, all_items_str, relevant_context):
        cfg = DIAGNOSIS_CONFIG
        return f"""
**Task**: '담보명', '세부담보템플릿명', 약관(PDF/텍스트), 매핑 테이블, 추출된 규칙을 종합하여
**'{cfg['name']}'** 값을 추론하세요.

**Attribute**: {cfg['name']}

**Mapping Tables**:
{relevant_context}

**Extracted Rules (Phase 1)**:
{logic_content}

**속성별 추론 지침**:
{cfg['phase2_instruction']}

**공통 지침**:
1. 입력된 담보명과 세부담보템플릿명 쌍을 **번호 순서대로** 분석하세요.
2. **약관 내 별표(Appendix) 최우선**: 약관 본문에서 별표 참조 문구를 찾으면 해당 별표를 최우선 근거로 삼으세요.
3. 약관에서 찾을 수 없으면 표준 보험/의료 지식을 활용하세요.
4. **inferred_code**가 빈칸("")인 경우 ref_sentence 에 반드시 "[미추론 사유: ...]"를 기입하세요.
5. **confidence**: high(약관 직접 근거) / medium(외부 지식) / low(추정)
6. **source**: appendix(별표) / policy_text(약관 본문) / mapping_table / external_knowledge

**[Chain-of-Thought 추론 순서]**:
각 담보를 분석하기 전에 다음 단계를 내부적으로 수행하세요 (출력에는 JSON만 포함):
① 담보명·템플릿명이 시사하는 의료/보험 영역 특정
② 약관 별표에서 관련 정의 검색 (페이지 확인)
③ 매핑 테이블에서 대응 코드 검색
④ 근거가 불충분하면 외부 지식으로 보완
⑤ 최종 코드 확정 및 신뢰도·출처 판단

**Few-Shot 예시**:
{cfg['few_shot_example']}

**Input Items**:
{all_items_str}

**Output JSON** (JSON 배열만 출력, 다른 텍스트 없음):
[
  {{
    "benefit_name": "...",
    "template_name": "...",
    "inferred_code": "...",
    "confidence": "high|medium|low",
    "source": "appendix|policy_text|mapping_table|external_knowledge",
    "ref_page": "...",
    "ref_sentence": "..."
  }}
]
"""

    # ─────────────────────────────────────────────────────────────────────
    # 참조 파일 그룹핑 (PoC_Step3 와 동일)
    # ─────────────────────────────────────────────────────────────────────
    def _group_files_by_pair(self, file_paths):
        groups = {}
        for f in file_paths:
            folder = os.path.dirname(os.path.abspath(f))
            group_key = os.path.basename(folder) or "default_group"
            groups.setdefault(group_key, []).append(f)
        if len(groups) == 1 and len(next(iter(groups.values()))) > 1:
            only_group = next(iter(groups.values()))
            groups = {}
            for f in only_group:
                base = os.path.splitext(os.path.basename(f))[0]
                groups.setdefault(base, []).append(f)
        return groups

    # ─────────────────────────────────────────────────────────────────────
    # LLM 호출 헬퍼 — 두 모델 모두 텍스트 입력으로 통일하여 공정 비교
    # ─────────────────────────────────────────────────────────────────────
    def _call_llm(self, prompt_text, file_paths, logger):
        """
        provider 종류에 관계없이 동일한 텍스트 입력을 전달.
        (Claude 도 PDF 첨부가 가능하지만, 두 모델의 공정한 비교를 위해 동일한
         텍스트 추출본을 입력으로 사용)
        """
        text_files = []
        for p in file_paths or []:
            ext = os.path.splitext(p)[1].lower()
            if ext == ".pdf":
                txt = self.extract_text_from_pdf(p, cache_dir=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "rag_cache"), logger=logger)
                tmp_txt = p + ".extracted.txt"
                if not os.path.exists(tmp_txt):
                    with open(tmp_txt, "w", encoding="utf-8") as wf:
                        wf.write(txt)
                text_files.append(tmp_txt)
            elif ext in [".xlsx", ".xls"]:
                try:
                    df = pd.read_excel(p)
                    tmp_csv = p + ".extracted.csv"
                    df.to_csv(tmp_csv, index=False)
                    text_files.append(tmp_csv)
                except Exception as e:
                    logger(f"  > Excel 변환 실패 {p}: {e}")
            else:
                text_files.append(p)

        result = self.provider.generate(prompt_text, files=text_files, logger=logger)
        self.token_usage["input"] += result.get("input_tokens", 0)
        self.token_usage["output"] += result.get("output_tokens", 0)
        self.token_usage["calls"] += 1
        return result["text"]

    # ─────────────────────────────────────────────────────────────────────
    # 메인 처리 파이프라인 (진단코드 1개 속성만)
    # ─────────────────────────────────────────────────────────────────────
    def process(self, target_pdf, target_excel, mapping_files, ref_files=None, result_dir=None, logger=print):
        cfg = DIAGNOSIS_CONFIG
        ref_files = ref_files or []
        try:
            df_initial = pd.read_excel(target_excel)
            if "세부담보템플릿명" not in df_initial.columns:
                return {"error": "Target Excel 에 '세부담보템플릿명' 컬럼이 없습니다."}

            benefits = (
                df_initial[["담보명_출력물명칭", "세부담보템플릿명"]]
                .dropna()
                .to_dict(orient="records")
            )

            # 매핑 파일 로드
            maps_by_name = {}
            for mf in mapping_files:
                try:
                    df_map = pd.read_excel(mf).dropna(how="all", axis=0).dropna(how="all", axis=1)
                    fname = os.path.basename(mf)
                    maps_by_name[fname] = f"\n\n=== 매핑 테이블: {fname} ===\n{df_map.to_csv(index=False)}\n"
                except Exception as e:
                    logger(f"매핑 파일 로드 실패 {mf}: {e}")

            relevant_context = self._select_mapping_context(maps_by_name)

            os.makedirs(result_dir, exist_ok=True)
            safe_name = cfg["key"].replace("Inferred_", "")
            label_slug = re.sub(r"[^A-Za-z0-9가-힣_-]", "_", self.label)

            # ── Phase 1 : 참조 약관에서 로직 추출 ───────────────────────────
            grouped_refs = self._group_files_by_pair(ref_files)
            extracted_logics = []

            if grouped_refs:
                logger(f"\n[{self.label}] Phase 1 - 로직 추출 시작 ({len(grouped_refs)} 그룹)")
                for group_name, paths in grouped_refs.items():
                    rule_prompt = self._build_phase1_prompt(group_name, relevant_context)
                    try:
                        raw = self._call_llm(rule_prompt, paths, logger)
                        if raw and "관련 내용 없음" not in raw:
                            parsed = self._parse_json_response(raw, logger)
                            if parsed:
                                extracted_logics.append(
                                    f"=== [Logic from {group_name}] ===\n"
                                    + json.dumps(parsed, ensure_ascii=False, indent=2)
                                )
                            else:
                                extracted_logics.append(
                                    f"=== [Logic from {group_name}] ===\n{raw}"
                                )
                            logger(f"  > 로직 추출 완료: {group_name}")
                    except Exception as ge:
                        logger(f"  > Phase 1 오류 ({group_name}): {ge}")
                    time.sleep(2)

            logic_content = (
                "\n\n".join(extracted_logics)
                if extracted_logics
                else "추출된 로직 없음. 표준 보험/의료 지식 활용."
            )

            logic_path = os.path.join(result_dir, f"Logic_{safe_name}__{label_slug}.txt")
            with open(logic_path, "w", encoding="utf-8") as f:
                f.write(f"=== {self.label} - {cfg['name']} ===\n\n{logic_content}")

            # ── Phase 2 : 타겟 약관에서 진단코드 추론 ───────────────────────
            logger(f"\n[{self.label}] Phase 2 - 진단코드 추론 시작 ({len(benefits)} 건)")
            all_items_str = "\n".join(
                [
                    f"[{i+1}] 담보명: {b['담보명_출력물명칭']} / 세부담보템플릿명: {b['세부담보템플릿명']}"
                    for i, b in enumerate(benefits)
                ]
            )

            prompt = self._build_phase2_prompt(logic_content, all_items_str, relevant_context)

            batch_results = []
            try:
                raw = self._call_llm(prompt, [target_pdf], logger)
                logger(f"  > 응답 첫 300자: {raw[:300] if raw else '(empty)'}")
                batch_results = self._parse_json_response(raw, logger)
            except Exception as ie:
                logger(f"  > 추론 실패: {ie}")
                logger(traceback.format_exc())

            logger(f"  > API 응답: {len(batch_results)}건")

            # 결과 DataFrame 구성
            df_result = df_initial.copy()
            df_result[cfg["key"]] = ""
            df_result["Confidence"] = ""
            df_result["Source"] = ""
            df_result["Ref_Page"] = ""
            df_result["Code_Mapping_Reason"] = ""
            df_result["LLM_Provider"] = self.label
            df_result["Model_Name"] = self.provider.get_model_name()

            res_dict = {}
            for r in batch_results:
                key = (
                    str(r.get("benefit_name", "")).strip(),
                    str(r.get("template_name", "")).strip(),
                )
                res_dict[key] = r

            def find_match(row):
                bn = str(row["담보명_출력물명칭"]).strip()
                tn = str(row["세부담보템플릿명"]).strip()
                if (bn, tn) in res_dict:
                    return res_dict[(bn, tn)]
                for (rb, rt), val in res_dict.items():
                    if (rb in bn or bn in rb) and (rt in tn or tn in rt):
                        return val
                return {}

            matched = 0
            for i, row in df_result.iterrows():
                m = find_match(row)
                if m:
                    matched += 1
                df_result.at[i, cfg["key"]] = m.get("inferred_code", "")
                df_result.at[i, "Confidence"] = m.get("confidence", "")
                df_result.at[i, "Source"] = m.get("source", "")
                df_result.at[i, "Ref_Page"] = m.get("ref_page", "")
                sent = m.get("ref_sentence", "")
                if sent:
                    df_result.at[i, "Code_Mapping_Reason"] = f"[{cfg['name']}] {sent}"
                elif not m:
                    df_result.at[i, "Code_Mapping_Reason"] = (
                        f"[{cfg['name']}] [미매칭: API 응답에서 해당 담보를 찾지 못함]"
                    )

            logger(f"  > 매칭: {matched}/{len(df_result)} 건")

            result_path = os.path.join(result_dir, f"Result_{safe_name}__{label_slug}.xlsx")
            df_result.to_excel(result_path, index=False)
            logger(f"  > 저장: {os.path.basename(result_path)}")

            return {
                "label": self.label,
                "model": self.provider.get_model_name(),
                "logic_path": logic_path,
                "result_path": result_path,
                "matched": matched,
                "total": len(df_result),
                "token_usage": dict(self.token_usage),
                "dataframe": df_result,
            }

        except Exception as e:
            logger(f"Error: {e}")
            logger(traceback.format_exc())
            return {"error": str(e), "label": self.label}
