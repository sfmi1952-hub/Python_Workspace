
import pandas as pd
import json
import re
import tempfile
import os
import shutil
import zipfile
import pypdf
import time
import traceback

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from .openai_core import OpenAICore


# ─────────────────────────────────────────────────────────────────────────────
# [개선 #1] 속성별 전용 프롬프트 + 명시적 매핑 파일 + Few-Shot 예시 통합 설정
#           (기존: 하나의 프롬프트 안에 모든 속성 조건 혼재 → 속성별 완전 분리)
# ─────────────────────────────────────────────────────────────────────────────
ATTRIBUTE_CONFIGS = [
    {
        "key": "Inferred_Diagnosis_Code",
        "name": "진단코드 (Diagnosis Code)",
        # 매핑 파일 파일명 패턴 (기존 키워드 휴리스틱 대체)
        "mapping_files": ["1_진단분류코드", "진단분류", "FCDF131"],
        # Phase 1 전용 지시문
        "phase1_instruction": """
- 약관 본문에서 '별표 X를 참조한다'는 문구를 찾고, 해당 별표에서 **KCD 코드 범위**(예: C00~C97)를 추출하세요.
- 매핑 테이블의 '분류번호'(예: 0A1)와 약관의 KCD 범위가 어떻게 연결되는지 패턴을 분석하세요.
- 제외 코드(예: C44 기타피부암, C73 갑상선암) 규칙을 반드시 포함하세요.
- 출력 JSON의 'rules' 배열 내 각 항목에 template_pattern, code, kcd_range, exclusions를 모두 기입하세요.
""",
        # Phase 2 전용 지시문
        "phase2_instruction": """
- **별표(Appendix) 최우선**: 약관 본문에서 '별표'를 참조하라고 되어 있으면, 해당 별표 페이지를 찾아 KCD 코드 범위를 확인하세요.
- **외부 KCD 지식 활용**: 별표에서 찾을 수 없으면 표준 KCD(한국표준질병사인분류) 지식으로 대응 분류번호를 도출하세요.
- inferred_code는 매핑 테이블의 **분류번호**(예: 0A1) 형식으로 기입하세요. KCD 코드(C00 등) 직접 기입 금지.
""",
        # [개선 #3] Few-Shot 예시
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
    },
    {
        "key": "Inferred_Exemption_Code",
        "name": "면책코드 (Exemption Code)",
        "mapping_files": ["면책", "Exemption"],
        "phase1_instruction": """
- **'보장하지 않는 사항(면책 사유)'**만 분석하세요. 진단 코드·질병 정의·수술 정의는 절대 포함하지 마세요.
- 면책 사유 코드가 명시된 조항 위치(예: 제3조 보험금을 지급하지 않는 경우)를 기록하세요.
- 코드가 존재하지 않는 담보는 rules 배열을 비워두세요.
""",
        "phase2_instruction": """
- **(중요)** 이 항목은 질병 코드가 아니라 **'보장하지 않는 사항(면책 사유)'** 코드입니다. KCD 코드(C00, I20 등) 절대 금지.
- 약관에 면책 사유 코드가 명시되지 않았으면 inferred_code를 **빈칸("")**으로 두세요. 억지로 채우지 마세요.
- ref_sentence에는 '보장하지 않는 사항' 조항 원문을 그대로 기입하세요.
""",
        "few_shot_example": """
**예시 입력**: 담보명: 암진단비 / 세부담보템플릿명: ZD_암진단_일반형
**예시 출력**:
{
  "benefit_name": "암진단비",
  "template_name": "ZD_암진단_일반형",
  "inferred_code": "",
  "confidence": "high",
  "source": "policy_text",
  "ref_page": "0",
  "ref_sentence": "[미추론 사유: 약관 제3조 보장하지 않는 사항에 별도 면책코드가 명시되어 있지 않음]"
}
""",
    },
    {
        "key": "Inferred_EDI_Code",
        "name": "EDI코드 (EDI Code)",
        "mapping_files": ["2_EDI코드", "EDI", "ZFSW072"],
        "phase1_instruction": """
- 약관에서 수술·처치 정의 조항을 찾아 EDI(건강보험 수술분류) 코드와의 연결 패턴을 분석하세요.
- 약관 설명이 부족한 경우, 의료/EDI 표준 지식을 동원해 추론 로직을 보강하세요.
- 수술 종류별(예: 개두술, 관상동맥 수술 등) 대응 EDI 코드 범위를 rules에 기술하세요.
""",
        "phase2_instruction": """
- 약관에서 해당 담보의 수술·처치 정의를 찾아 EDI 코드 매핑 테이블과 대응시키세요.
- 약관에 직접 EDI 코드가 없으면, 담보명이 시사하는 의료 행위의 표준 EDI 코드를 의료 지식으로 도출하세요.
- inferred_code는 EDI 코드(예: R4421) 형식으로 기입하세요.
""",
        "few_shot_example": """
**예시 입력**: 담보명: 뇌수술비 / 세부담보템플릿명: ZD_뇌수술_일반
**예시 출력**:
{
  "benefit_name": "뇌수술비",
  "template_name": "ZD_뇌수술_일반",
  "inferred_code": "R4421",
  "confidence": "medium",
  "source": "external_knowledge",
  "ref_page": "0",
  "ref_sentence": "[외부 지식: 뇌수술은 EDI 수술분류 R4421(개두술)에 해당함] [선정 이유] 약관에 직접 EDI 코드 미명시, 의료 표준 분류 적용"
}
""",
    },
    {
        "key": "Inferred_Hospital_Grade",
        "name": "병원등급 (Hospital Grade)",
        "mapping_files": ["4_병원등급", "병원등급"],
        "phase1_instruction": """
- 약관에서 '병원 등급(상급종합병원, 종합병원, 병원, 의원 등)' 기준 조항을 찾으세요.
- 등급별 코드(예: G1, G2 등)와 약관 정의의 연결 패턴을 분석하세요.
- 담보별로 적용되는 병원 등급 제한(예: 상급종합병원 이상)을 rules에 기술하세요.
""",
        "phase2_instruction": """
- 담보명에서 병원 등급 제한 여부를 파악하세요(예: '종합병원', '상급종합병원' 포함 여부).
- 매핑 테이블의 병원등급 코드(예: G1~G4)와 대응시키세요.
- 병원 등급 제한이 명시되지 않은 담보는 inferred_code를 빈칸("")으로 두세요.
""",
        "few_shot_example": """
**예시 입력**: 담보명: 상급종합병원입원일당 / 세부담보템플릿명: ZD_입원일당_상급
**예시 출력**:
{
  "benefit_name": "상급종합병원입원일당",
  "template_name": "ZD_입원일당_상급",
  "inferred_code": "G1",
  "confidence": "high",
  "source": "policy_text",
  "ref_page": "12",
  "ref_sentence": "이 특약에서 '상급종합병원'이라 함은 의료법 제3조의4에 따라 지정된 의료기관을 말합니다. [선정 이유] 담보명 및 약관 정의 기준 G1(상급종합병원) 적용"
}
""",
    },
    {
        "key": "Inferred_Hospital_Class",
        "name": "병원분류 (Hospital Classification)",
        "mapping_files": ["3_병원분류", "병원분류", "ZFCW095"],
        "phase1_instruction": """
- 약관에서 '병원 분류(종합병원형, 병원형 등)' 조항을 찾으세요.
- 분류별 코드와 약관 정의의 연결 패턴을 분석하세요.
- 특정 담보 유형(입원/통원/수술)과 병원 분류 조건의 연관성을 rules에 기술하세요.
""",
        "phase2_instruction": """
- 담보 유형(입원/통원/수술)과 약관에서 규정하는 병원 분류 조건을 매핑 테이블과 연결하세요.
- 분류 조건이 명시되지 않은 담보는 inferred_code를 빈칸("")으로 두세요.
""",
        "few_shot_example": """
**예시 입력**: 담보명: 종합병원통원일당 / 세부담보템플릿명: ZD_통원_종합병원
**예시 출력**:
{
  "benefit_name": "종합병원통원일당",
  "template_name": "ZD_통원_종합병원",
  "inferred_code": "H02",
  "confidence": "high",
  "source": "mapping_table",
  "ref_page": "15",
  "ref_sentence": "국내 종합병원(의료법 제3조의3) 통원 치료 시 지급. [선정 이유] 매핑 테이블 H02(종합병원) 적용"
}
""",
    },
    {
        "key": "Inferred_Accident_Type",
        "name": "사고유형 (Accident Type)",
        "mapping_files": ["5_사고유형", "사고유형"],
        "phase1_instruction": """
- 약관에서 '사고 유형(질병/상해/재해 등)' 정의 조항을 찾으세요.
- 담보별로 적용되는 사고 유형 코드(예: A01, D01 등)와 약관 정의의 연결 패턴을 분석하세요.
""",
        "phase2_instruction": """
- 담보명에서 사고 유형(질병형/상해형/재해형)을 판단하세요.
- 매핑 테이블의 사고유형 코드와 대응시키세요.
- 복합형(질병+상해) 담보는 해당 코드를 모두 기입하세요(쉼표 구분).
""",
        "few_shot_example": """
**예시 입력**: 담보명: 질병사망 / 세부담보템플릿명: ZD_질병사망_일반
**예시 출력**:
{
  "benefit_name": "질병사망",
  "template_name": "ZD_질병사망_일반",
  "inferred_code": "D01",
  "confidence": "high",
  "source": "policy_text",
  "ref_page": "8",
  "ref_sentence": "이 특약은 피보험자가 질병으로 사망한 경우 보험금을 지급합니다. [선정 이유] 질병 사망 → 사고유형 D01 적용"
}
""",
    },
    {
        "key": "Inferred_Admission_Limit",
        "name": "입원한도일수 (Admission Limit Days)",
        "mapping_files": ["6_입원한도", "입원한도"],
        "phase1_instruction": """
- 약관에서 '입원 한도 일수(예: 120일, 180일)' 조항을 찾으세요.
- 한도 일수를 코드(예: L01=120일, L02=180일)로 변환하는 규칙을 분석하세요.
- 담보 유형별 한도 일수 차이(예: 상해 vs 질병)를 rules에 기술하세요.
""",
        "phase2_instruction": """
- 약관에서 해당 담보의 입원 한도 일수 조항을 찾으세요.
- 매핑 테이블의 코드(예: L01)로 변환하여 기입하세요. 직접 일수 숫자 기입 금지.
- 한도 조항이 없으면 inferred_code를 빈칸("")으로 두세요.
""",
        "few_shot_example": """
**예시 입력**: 담보명: 질병입원일당 / 세부담보템플릿명: ZD_질병입원_120일
**예시 출력**:
{
  "benefit_name": "질병입원일당",
  "template_name": "ZD_질병입원_120일",
  "inferred_code": "L01",
  "confidence": "high",
  "source": "policy_text",
  "ref_page": "20",
  "ref_sentence": "입원 1회당 120일을 한도로 지급합니다. [선정 이유] 120일 → 매핑 코드 L01 적용"
}
""",
    },
    {
        "key": "Inferred_Min_Admission",
        "name": "최소입원일수 (Minimum Admission Days)",
        "mapping_files": [],   # 매핑 테이블 없음 — 숫자 직접 추출
        "phase1_instruction": """
- 약관에서 '최소 입원 일수(예: 4일 이상 입원 시 지급)' 조항을 찾으세요.
- 매핑 테이블이 없으므로 **실제 일수 숫자**를 추출하는 규칙을 분석하세요.
- 담보별 최소 입원일수 차이를 rules에 기술하세요.
""",
        "phase2_instruction": """
- 약관에서 최소 입원 일수 조항을 찾아 **실제 숫자(예: '4')**를 기입하세요.
- 코드 변환 없이 숫자 그대로 기입합니다.
- 조항이 없으면 inferred_code를 빈칸("")으로 두세요.
""",
        "few_shot_example": """
**예시 입력**: 담보명: 질병입원일당 / 세부담보템플릿명: ZD_질병입원_4일이상
**예시 출력**:
{
  "benefit_name": "질병입원일당",
  "template_name": "ZD_질병입원_4일이상",
  "inferred_code": "4",
  "confidence": "high",
  "source": "policy_text",
  "ref_page": "21",
  "ref_sentence": "계속하여 4일 이상 입원한 경우에 한하여 지급합니다. [선정 이유] 최소 입원일수 4일 직접 추출"
}
""",
    },
    {
        "key": "Inferred_Coverage_Period",
        "name": "보장기간 (Coverage Period)",
        "mapping_files": ["보장기간", "Period"],
        "phase1_instruction": """
- 약관에서 '보장기간(예: 3년, 10년, 100세 등)' 정의 조항을 찾으세요.
- 보장기간 값과 코드(또는 표현 방식)의 연결 패턴을 분석하세요.
- 갱신형/비갱신형 여부에 따른 보장기간 차이를 rules에 기술하세요.
""",
        "phase2_instruction": """
- 약관에서 해당 담보의 보장기간 조항을 찾아 기입하세요.
- 매핑 테이블이 있으면 코드로, 없으면 '10년', '100세' 등 약관 표현 그대로 기입하세요.
- 보장기간 조항이 없으면 inferred_code를 빈칸("")으로 두세요.
""",
        "few_shot_example": """
**예시 입력**: 담보명: 암진단비(갱신형) / 세부담보템플릿명: ZD_암진단_갱신
**예시 출력**:
{
  "benefit_name": "암진단비(갱신형)",
  "template_name": "ZD_암진단_갱신",
  "inferred_code": "3년",
  "confidence": "high",
  "source": "policy_text",
  "ref_page": "3",
  "ref_sentence": "이 특약의 보험기간은 3년으로 합니다. [선정 이유] 갱신형 기본 보장기간 3년 적용"
}
""",
    },
]


class DiagnosisMapper:
    def __init__(self, api_key):
        self.client = OpenAICore(api_key)

    # ─────────────────────────────────────────────────────────────────────────
    # [개선 #5] PDF 텍스트 추출 — 테이블 내용 중복 제거
    #           (기존: extract_text + extract_tables 동시 사용 → 별표 내용 2배 주입)
    # ─────────────────────────────────────────────────────────────────────────
    def extract_text_from_pdf(self, pdf_path):
        """
        PDF 텍스트 추출. 캐시 우선, pdfplumber(테이블 우선), pypdf 순서.
        테이블이 있는 페이지는 마크다운 테이블만 사용하고 raw 텍스트는 제외하여
        내용 중복을 방지합니다.
        """
        PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "rag_cache")
        os.makedirs(CACHE_DIR, exist_ok=True)

        filename = os.path.basename(pdf_path)
        cache_path = os.path.join(CACHE_DIR, filename + ".md")

        # 1. 캐시 확인
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    print(f"  > [Cache] Loaded: {os.path.basename(cache_path)}")
                    return f.read()
            except Exception as e:
                print(f"  > [Cache] Read failed: {e}")

        text_content = ""

        # 2. pdfplumber — 테이블이 있는 페이지는 마크다운만, 없으면 텍스트만
        if pdfplumber:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page in pdf.pages:
                        tables = page.extract_tables()
                        if tables:
                            # 테이블이 있는 페이지: 마크다운 테이블만 사용 (중복 방지)
                            for table in tables:
                                cleaned = [
                                    [str(cell) if cell else "" for cell in row]
                                    for row in table
                                ]
                                if len(cleaned) > 1:
                                    try:
                                        df_table = pd.DataFrame(
                                            cleaned[1:], columns=cleaned[0]
                                        )
                                        text_content += "\n" + df_table.to_markdown(index=False) + "\n"
                                    except Exception:
                                        pass
                        else:
                            # 테이블 없는 페이지: 텍스트만 사용
                            text_content += (page.extract_text() or "") + "\n"
                print(f"  > [Extraction] pdfplumber: {filename}")
            except Exception as e:
                print(f"  > [Extraction] pdfplumber failed ({e}), falling back to pypdf...")
                text_content = ""

        # 3. pypdf fallback
        if not text_content:
            try:
                with open(pdf_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    text_parts = [page.extract_text() or "" for page in reader.pages]
                    text_content = "\n".join(text_parts)
                print(f"  > [Extraction] pypdf: {filename}")
            except Exception as e:
                print(f"  > [Extraction] pypdf failed for {pdf_path}: {e}")
                return ""

        # 4. 캐시 저장
        if text_content:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(text_content)
                print(f"  > [Cache] Saved: {os.path.basename(cache_path)}")
            except Exception as e:
                print(f"  > [Cache] Save failed: {e}")

        return text_content

    # ─────────────────────────────────────────────────────────────────────────
    # [개선 #7] 강건한 JSON 파싱 + 재시도
    # ─────────────────────────────────────────────────────────────────────────
    def _parse_json_response(self, raw_text, logger=print):
        """JSON 배열을 파싱합니다. 실패 시 정규식으로 재시도합니다."""
        if not raw_text:
            return []
        # 코드 블록 마커 제거
        cleaned = re.sub(r"```(?:json)?", "", raw_text).strip()
        # 배열 구간 추출 (중첩 구조 대응: 첫 '[' ~ 마지막 ']')
        start = cleaned.find("[")
        end = cleaned.rfind("]")
        if start == -1 or end == -1:
            logger("  > [JSON] 배열 마커를 찾을 수 없습니다.")
            return []
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as e:
            logger(f"  > [JSON] 파싱 실패: {e}")
            # 개별 객체를 정규식으로 추출 시도
            objects = re.findall(r"\{[^{}]*\}", cleaned, re.DOTALL)
            results = []
            for obj_str in objects:
                try:
                    results.append(json.loads(obj_str))
                except Exception:
                    pass
            if results:
                logger(f"  > [JSON] 정규식 복구: {len(results)}개 객체 추출")
            return results

    def _parse_json_with_llm_retry(self, raw_text, logger=print):
        """JSON 파싱 실패 시 LLM에 수정 요청하여 재시도합니다."""
        result = self._parse_json_response(raw_text, logger)
        if result:
            return result
        logger("  > [JSON] 1차 파싱 실패 — LLM 수정 요청 재시도...")
        fix_prompt = (
            "아래 텍스트는 유효하지 않은 JSON입니다. "
            "올바른 JSON 배열([ { ... }, ... ])만 출력하세요. 다른 설명 없이 JSON만:\n\n"
            + raw_text[:2000]
        )
        try:
            fix_resp = self.client.generate_content(fix_prompt)
            fix_text = OpenAICore.extract_text(fix_resp)
            result = self._parse_json_response(fix_text, logger)
            if result:
                logger(f"  > [JSON] LLM 수정 후 파싱 성공: {len(result)}개")
            return result
        except Exception as e:
            logger(f"  > [JSON] LLM 수정 재시도 실패: {e}")
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # 매핑 컨텍스트 선택 — [개선 #4] 명시적 파일 패턴 기반
    # ─────────────────────────────────────────────────────────────────────────
    def _select_mapping_context(self, config, maps_by_name):
        """속성별 매핑 파일 패턴으로 관련 테이블만 선택합니다."""
        patterns = config.get("mapping_files", [])
        if not patterns:
            return "해당 속성에 대한 매핑 테이블이 없습니다."
        selected = []
        for fname, content in maps_by_name.items():
            if any(p.lower() in fname.lower() for p in patterns):
                selected.append(content)
        if selected:
            return "\n".join(selected)
        # 패턴 매칭 실패 시: 전체 대신 경고 메시지 반환 (노이즈 방지)
        return f"[주의] '{config['name']}' 관련 매핑 파일을 찾지 못했습니다. 파일명을 확인하세요."

    # ─────────────────────────────────────────────────────────────────────────
    # [개선 #6] Phase 1 구조화 JSON 출력 요청
    # ─────────────────────────────────────────────────────────────────────────
    def _build_phase1_prompt(self, config, group_name, relevant_context):
        attr_name = config["name"]
        attr_specific = config.get("phase1_instruction", "")
        return f"""
**Role**: 보험 약관 분석 전문가.

**Goal**: 참조 문서({group_name})를 분석하여 **'{attr_name}'** 추론에 필요한 규칙을 추출하고,
아래 JSON 형식으로만 출력하세요.

**Target Attribute**: {attr_name}

**Mapping Tables**:
{relevant_context}

**속성별 분석 지침**:
{attr_specific}

**공통 지침**:
1. 오직 **'{attr_name}'** 추출 로직만 작성하세요. 다른 속성 내용은 절대 포함하지 마세요.
2. 약관에 '별표(Appendix)'가 있으면 **최우선**으로 확인하고 반영하세요.
3. 담보명과 세부담보템플릿명을 종합적으로 고려해야 하는 판단 기준을 포함하세요.

**출력 형식 (JSON만, 다른 텍스트 없음)**:
{{
  "attribute": "{attr_name}",
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

    # ─────────────────────────────────────────────────────────────────────────
    # [개선 #1 #2 #3] Phase 2 속성별 전용 프롬프트 + CoT + Few-Shot
    # ─────────────────────────────────────────────────────────────────────────
    def _build_phase2_prompt(self, config, logic_content, all_items_str, relevant_context):
        attr_name = config["name"]
        attr_specific = config.get("phase2_instruction", "")
        few_shot = config.get("few_shot_example", "")

        return f"""
**Task**: '담보명', '세부담보템플릿명', 약관(PDF), 매핑 테이블, 추출된 규칙을 종합하여
**'{attr_name}'** 값을 추론하세요.

**Attribute**: {attr_name}

**Mapping Tables**:
{relevant_context}

**Extracted Rules (Phase 1)**:
{logic_content}

**속성별 추론 지침**:
{attr_specific}

**공통 지침**:
1. 입력된 담보명과 세부담보템플릿명 쌍을 **번호 순서대로** 분석하세요.
2. **약관 내 별표(Appendix) 최우선**: 약관 본문에서 별표 참조 문구를 찾으면 해당 별표를 최우선 근거로 삼으세요.
3. 약관에서 찾을 수 없으면 표준 보험/의료 지식을 활용하세요.
4. **inferred_code**가 빈칸("")인 경우 ref_sentence에 반드시 "[미추론 사유: ...]"를 기입하세요.
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
{few_shot}

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

    # ─────────────────────────────────────────────────────────────────────────
    # 메인 처리 파이프라인 — OpenAI Responses API + file_search (Vector Store)
    # ─────────────────────────────────────────────────────────────────────────
    def process(self, target_pdf, target_excel, mapping_files, ref_files=[], logger=print):
        try:
            # 입력 템플릿 로드
            df_initial_template = pd.read_excel(target_excel)
            if "세부담보템플릿명" not in df_initial_template.columns:
                return {"error": "Target Excel에 '세부담보템플릿명' 컬럼이 없습니다."}

            benefits_data = (
                df_initial_template[["담보명_출력물명칭", "세부담보템플릿명"]]
                .dropna()
                .to_dict(orient="records")
            )

            vector_stores_to_clean = []

            # 매핑 파일 로드 (텍스트로 프롬프트에 주입 — Gemini 버전과 동일)
            if not isinstance(mapping_files, list):
                mapping_files = [mapping_files]

            maps_by_name = {}
            logger(f"Processing {len(mapping_files)} Mapping Files...")
            for mf in mapping_files:
                try:
                    df_map = pd.read_excel(mf)
                    df_map = df_map.dropna(how="all", axis=0).dropna(how="all", axis=1)
                    csv_clean = df_map.to_csv(index=False)
                    fname = os.path.basename(mf)
                    maps_by_name[fname] = f"\n\n=== 매핑 테이블: {fname} ===\n{csv_clean}\n"
                except Exception as e:
                    logger(f"Warning: {mf} 로드 실패: {e}")

            # ── 타겟 PDF → Vector Store 업로드 (1회) ──────────────────────
            logger("Creating Vector Store for target PDF...")
            target_vs = self.client.create_vector_store(
                name="target_policy", logger=logger
            )
            vector_stores_to_clean.append(target_vs.id)
            self.client.upload_to_vector_store(
                target_vs.id, target_pdf, logger=logger
            )
            target_vs_id = target_vs.id

            # [개선 #10] 참조 파일 그룹핑 — 디렉토리 단위
            grouped_refs = self._group_files_by_pair(ref_files)

            PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            RESULT_DIR = os.path.join(PROJECT_ROOT, "data", "result")
            os.makedirs(RESULT_DIR, exist_ok=True)

            generated_files = []

            # 담보 목록 번호 부여 (CoT 참조용)
            all_items_str = "\n".join(
                [
                    f"[{i+1}] 담보명: {b['담보명_출력물명칭']} / 세부담보템플릿명: {b['세부담보템플릿명']}"
                    for i, b in enumerate(benefits_data)
                ]
            )

            # ── 속성별 격리 루프 ─────────────────────────────────────────────
            for idx, config in enumerate(ATTRIBUTE_CONFIGS):
                attr_key = config["key"]
                attr_name = config["name"]
                safe_name = attr_key.replace("Inferred_", "")

                logger(f"\n{'='*55}")
                logger(f"[{idx+1}/{len(ATTRIBUTE_CONFIGS)}] {attr_name}")
                logger(f"{'='*55}")

                df_attr_result = df_initial_template.copy()
                if attr_key not in df_attr_result.columns:
                    df_attr_result[attr_key] = ""
                df_attr_result["Code_Mapping_Reason"] = ""
                df_attr_result["Confidence"] = ""
                df_attr_result["Source"] = ""
                if "Ref_Page" not in df_attr_result.columns:
                    df_attr_result["Ref_Page"] = ""

                # [개선 #4] 속성별 관련 매핑 컨텍스트만 선택
                relevant_context = self._select_mapping_context(
                    config, maps_by_name
                )

                # ── Phase 1: 로직 추출 ────────────────────────────────────────
                cached_logic_path = os.path.join(RESULT_DIR, f"Logic_{safe_name}.txt")
                extracted_logics = []

                if grouped_refs:
                    logger(f"Phase 1 (Logic): {attr_name} 규칙 추출 중...")
                    for group_name, paths in grouped_refs.items():
                        ref_vs_id = None
                        try:
                            # [개선 #6] 구조화 JSON 요청 프롬프트
                            rule_prompt = self._build_phase1_prompt(
                                config, group_name, relevant_context
                            )

                            try:
                                # 참조 파일 그룹별 Vector Store 생성
                                ref_vs = self.client.create_vector_store(
                                    name=f"ref_{group_name}", logger=logger
                                )
                                ref_vs_id = ref_vs.id

                                for p in paths:
                                    self.client.upload_to_vector_store(
                                        ref_vs_id, p, logger=logger
                                    )

                                # Responses API + file_search로 로직 추출
                                rule_resp = self.client.generate_content(
                                    rule_prompt,
                                    vector_store_ids=[ref_vs_id],
                                )
                                resp_text = OpenAICore.extract_text(rule_resp)

                                if resp_text and "관련 내용 없음" not in resp_text:
                                    # JSON 구조 파싱 시도
                                    parsed_logic = self._parse_json_response(
                                        resp_text, logger
                                    )
                                    if parsed_logic:
                                        extracted_logics.append(
                                            f"=== [Logic from {group_name}] ===\n"
                                            + json.dumps(parsed_logic, ensure_ascii=False, indent=2)
                                        )
                                    else:
                                        # 파싱 불가 시 원문 저장
                                        extracted_logics.append(
                                            f"=== [Logic from {group_name}] ===\n{resp_text}"
                                        )
                                    logger(f"  > Logic 추출 완료: {group_name}")

                            except Exception as api_err:
                                logger(f"  > Vector Store 업로드 실패 ({api_err}). 텍스트 폴백...")
                                self._phase1_text_fallback(
                                    paths, rule_prompt, extracted_logics, group_name, logger
                                )

                        except Exception as ge:
                            logger(f"  > Phase 1 오류 ({group_name}): {ge}")
                        finally:
                            # 참조 Vector Store 정리
                            if ref_vs_id:
                                self.client.delete_vector_store(ref_vs_id, logger=logger)
                            time.sleep(5)

                    logic_content = (
                        "\n\n".join(extracted_logics)
                        if extracted_logics
                        else "추출된 로직 없음. 표준 보험/의료 지식 활용."
                    )
                    txt_path = os.path.join(RESULT_DIR, f"Logic_{safe_name}.txt")
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(f"=== Logic for {attr_name} ===\n\n{logic_content}")
                    generated_files.append((f"Logic_{safe_name}.txt", txt_path))
                    logger(f"  > Logic_{safe_name}.txt 저장 완료")

                else:
                    # Phase 1 스킵 — 캐시 로드
                    if os.path.exists(cached_logic_path):
                        with open(cached_logic_path, "r", encoding="utf-8") as f:
                            logic_content = f.read()
                        logger(f"Phase 1 Skip: 캐시 로드 — Logic_{safe_name}.txt")
                    else:
                        logic_content = "추출된 로직 없음. 표준 보험/의료 지식 활용."
                        logger(f"Phase 1 Skip: 캐시 없음 — 일반 지식 사용")

                # ── Phase 2: 속성 추론 ────────────────────────────────────────
                logger(f"Phase 2 (Inference): {attr_name} 추론 중...")

                # [개선 #1 #2 #3] 속성별 전용 프롬프트 + CoT + Few-Shot
                prompt = self._build_phase2_prompt(
                    config, logic_content, all_items_str, relevant_context
                )

                batch_results = []
                try:
                    # Responses API + file_search (타겟 PDF Vector Store)
                    resp = self.client.generate_content(
                        prompt,
                        vector_store_ids=[target_vs_id],
                    )
                    resp_text = OpenAICore.extract_text(resp)

                    logger(
                        f"  > [DEBUG] 응답 첫 500자: {resp_text[:500] if resp_text else '(empty)'}"
                    )

                    # [개선 #7] 강건한 JSON 파싱 + LLM 재시도
                    batch_results = self._parse_json_with_llm_retry(resp_text, logger)

                    if batch_results:
                        sample = batch_results[0]
                        logger(
                            f"  > [DEBUG] 샘플: benefit={sample.get('benefit_name','?')}, "
                            f"code={sample.get('inferred_code','?')}, "
                            f"conf={sample.get('confidence','?')}, "
                            f"src={sample.get('source','?')}"
                        )

                except Exception as ie:
                    logger(f"  > 추론 실패 ({attr_name}): {ie}")
                    logger(f"  > [DEBUG] {traceback.format_exc()}")

                logger(f"  > API 응답: {len(batch_results)}건")

                # ── [개선 #8] find_match 결과 사전 계산 (중복 호출 제거) ──────
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
                    # 부분 매칭 fallback
                    for (rb, rt), val in res_dict.items():
                        if (rb in bn or bn in rb) and (rt in tn or tn in rt):
                            return val
                    return {}

                # 1회 계산 후 재사용
                match_cache = {
                    i: find_match(row)
                    for i, row in df_attr_result.iterrows()
                }

                df_attr_result[attr_key] = [
                    match_cache[i].get("inferred_code", "")
                    for i in df_attr_result.index
                ]

                # [개선 #9] 신뢰도(Confidence) + 출처(Source) 컬럼 추가
                df_attr_result["Confidence"] = [
                    match_cache[i].get("confidence", "")
                    for i in df_attr_result.index
                ]
                df_attr_result["Source"] = [
                    match_cache[i].get("source", "")
                    for i in df_attr_result.index
                ]
                df_attr_result["Ref_Page"] = [
                    match_cache[i].get("ref_page", "")
                    for i in df_attr_result.index
                ]

                def make_reason(i):
                    m = match_cache[i]
                    sent = m.get("ref_sentence", "")
                    if sent:
                        return f"[{attr_name}] {sent}"
                    if not m:
                        return f"[{attr_name}] [미매칭: API 응답에서 해당 담보를 찾지 못함]"
                    return ""

                df_attr_result["Code_Mapping_Reason"] = [
                    make_reason(i) for i in df_attr_result.index
                ]

                matched_count = sum(1 for m in match_cache.values() if m)
                logger(f"  > 매칭: {matched_count}/{len(df_attr_result)}건")

                # 결과 저장
                exc_path = os.path.join(RESULT_DIR, f"Result_{safe_name}.xlsx")
                df_attr_result.to_excel(exc_path, index=False)
                generated_files.append((f"Result_{safe_name}.xlsx", exc_path))
                logger(f"  > Result_{safe_name}.xlsx 저장 완료")

                time.sleep(5)

            # ── Vector Store 정리 ─────────────────────────────────────────
            logger("Cleaning up Vector Stores...")
            for vs_id in vector_stores_to_clean:
                self.client.delete_vector_store(vs_id, logger=logger)

            # ZIP 생성
            zip_path = os.path.join(RESULT_DIR, "All_Results.zip")
            with zipfile.ZipFile(zip_path, "w") as zf:
                for archive_name, fs_path in generated_files:
                    zf.write(fs_path, arcname=archive_name)

            return {"file_path": zip_path, "logic_path": "", "preview": []}

        except Exception as e:
            logger(f"Error: {e}")
            logger(traceback.format_exc())
            return {"error": str(e)}

    def _phase1_text_fallback(self, paths, rule_prompt, extracted_logics, group_name, logger):
        """Vector Store 업로드 실패 시 텍스트 추출 폴백"""
        MAX_CHARS = 100_000
        fallback_text = ""
        for p in paths:
            if len(fallback_text) >= MAX_CHARS:
                logger(f"    - {MAX_CHARS}자 초과, 잘림 적용")
                break
            ext = os.path.splitext(p)[1].lower()
            extracted = ""
            try:
                if ext == ".pdf":
                    extracted = self.extract_text_from_pdf(p)
                elif ext in [".xlsx", ".xls"]:
                    extracted = pd.read_excel(p).to_csv(index=False)
                else:
                    with open(p, "r", encoding="utf-8", errors="ignore") as tx:
                        extracted = tx.read()
            except Exception:
                pass
            if extracted:
                allowed = MAX_CHARS - len(fallback_text)
                fallback_text += (
                    f"\n=== {os.path.basename(p)} ===\n{extracted[:allowed]}\n"
                )

        if fallback_text:
            combined_prompt = rule_prompt + "\n\n--- 참조 문서 내용 ---\n" + fallback_text
            try:
                fb_resp = self.client.generate_content(combined_prompt)
                fb_text = OpenAICore.extract_text(fb_resp)
                if fb_text and "관련 내용 없음" not in fb_text:
                    extracted_logics.append(
                        f"=== [Logic from {group_name} (Fallback)] ===\n{fb_text}"
                    )
                    logger(f"  > Fallback Logic 추출: {group_name}")
            except Exception as fe:
                logger(f"  > Fallback 실패: {fe}")

    # ─────────────────────────────────────────────────────────────────────────
    # [개선 #10] 파일 그룹핑 — 디렉토리 단위 (기존: 파일명 완전 일치 → PDF+Excel 분리)
    # ─────────────────────────────────────────────────────────────────────────
    def _group_files_by_pair(self, file_paths):
        """
        참조 파일을 디렉토리 단위로 그룹핑합니다.
        동일 폴더 내 PDF + Excel 등 여러 파일이 자동으로 한 그룹이 됩니다.
        """
        groups = {}
        for f in file_paths:
            folder = os.path.dirname(os.path.abspath(f))
            group_key = os.path.basename(folder)  # 폴더명을 그룹명으로 사용
            if not group_key:
                group_key = "default_group"
            groups.setdefault(group_key, []).append(f)
        # 단일 폴더(모두 같은 위치)인 경우 파일별로 분리
        if len(groups) == 1 and len(next(iter(groups.values()))) > 1:
            only_group = next(iter(groups.values()))
            groups = {}
            for f in only_group:
                base = os.path.splitext(os.path.basename(f))[0]
                groups.setdefault(base, []).append(f)
        return groups
