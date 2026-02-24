"""
M5: 프롬프트 템플릿 — 9개 속성별 전용 프롬프트 구성
PoC_Step3 ATTRIBUTE_CONFIGS 완전 이식 + 프롬프트 빌더
"""

# ─────────────────────────────────────────────────────────────────────────────
# 속성별 전용 프롬프트 + 매핑 파일 패턴 + Few-Shot 예시 통합 설정
# ─────────────────────────────────────────────────────────────────────────────
ATTRIBUTE_CONFIGS = [
    {
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
        "mapping_files": [],
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


# ── 프롬프트 빌더 ─────────────────────────────────────────────────────────

def build_phase1_prompt(config: dict, group_name: str, relevant_context: str) -> str:
    """Phase 1: 참조 문서에서 속성별 추론 규칙 추출"""
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


def build_phase2_prompt(
    config: dict,
    logic_content: str,
    all_items_str: str,
    relevant_context: str,
) -> str:
    """Phase 2: 속성별 전용 프롬프트 + CoT + Few-Shot"""
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
