# PoC_Step6 — 사외 SOTA LLM vs 사내 sLM 진단코드 추출 성능 비교

> **목적**: 보험IT 부서의 사내 sLM(GPT-OSS) 활용 가능성 문의에 대한 정량 근거 자료 확보.
> 같은 입력·같은 프롬프트·같은 파이프라인에서 LLM 호출만 swap 하여 두 모델의
> 진단코드 추출 정확도·신뢰도·근거 품질을 비교한다.

---

## 1. 실험 설계 (Methodology)

| 구분 | 사외 SOTA LLM | 사내 sLM |
|---|---|---|
| 모델 | **Claude Opus 4.7** (Anthropic) | **GPT-OSS 120B** (사내 호스팅) |
| 접근 경로 | AWS Bedrock 또는 Anthropic Direct API | 사내 OpenAI 호환 엔드포인트 |
| 컨텍스트 | 200K~1M 토큰 | 일반적으로 ~128K |
| 학습 도메인 | 일반 + 다국어 + 멀티모달 | 일반 (보험·의료 도메인 추가 학습 없음) |

### 통제 변인 (Same for Both)
PoC_Step3 의 검증된 파이프라인을 **그대로 복사**해 통제한다.

1. **입력 데이터** — `data/new/` (타겟 약관 PDF + 입력 템플릿 Excel)
2. **참조 데이터** — `data/rag/` (Phase 1 로직 학습용 약관 4종)
3. **매핑 테이블** — `data/code/1_진단분류코드_FCDF131.xlsx`
4. **PDF 텍스트 추출 로직** — pdfplumber 우선 + pypdf 폴백 + 캐시
5. **2-Phase 프롬프트** — 별표(Appendix) 최우선, Chain-of-Thought, Few-Shot 1개
6. **JSON 파싱 로직** — 코드블록 제거 → 배열 추출 → 중괄호 균형 객체 폴백
7. **추출 대상 속성** — `Inferred_Diagnosis_Code` (진단코드) 1종으로 한정

### 독립 변인 (Only Difference)
- LLM provider (`logic/claude_core.py` vs `logic/gpt_oss_core.py`)

---

## 2. 디렉토리 구조

```
PoC_Step6/
├── data/
│   ├── code/        # 매핑 테이블 (1_진단분류코드_FCDF131.xlsx 외 5개)
│   ├── new/         # 타겟 약관 (마이헬스 파트너 / 알파Plus)
│   ├── rag/         # 참조 약관 4종 (Phase 1 로직 학습)
│   ├── rag_cache/   # PDF→텍스트 캐시 (자동 생성)
│   └── result/      # 추출 결과 + 비교 리포트 (자동 생성)
├── logic/
│   ├── claude_core.py    # Claude Opus 4.7 클라이언트
│   ├── gpt_oss_core.py   # GPT-OSS 클라이언트 (OpenAI 호환)
│   └── code_mapper.py    # 2-Phase 진단코드 추출 (PoC_Step3 로직 동일)
├── run_comparison.py     # 메인 실행 (Claude + GPT-OSS 순차 호출 → 리포트)
├── run_poc.ps1           # PowerShell 실행 래퍼
├── requirements.txt
└── README.md             # (본 문서)
```

---

## 3. 실행 방법

### 3.1 환경 준비

```powershell
# PoC_Step3 와 동일한 venv 공유 사용
..\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3.2 API 키 / 엔드포인트 설정

```powershell
# Claude (Anthropic Direct)
$env:ANTHROPIC_API_KEY = "sk-ant-..."
$env:ANTHROPIC_MODEL   = "claude-opus-4-7"

# Claude (AWS Bedrock — 망분리 환경)
$env:ANTHROPIC_USE_BEDROCK = "true"
$env:AWS_REGION            = "us-east-1"
$env:BEDROCK_MODEL_ID      = "anthropic.claude-opus-4-7-20260101-v1:0"

# 사내 GPT-OSS (OpenAI 호환 엔드포인트)
$env:GPT_OSS_API_BASE = "http://gpt-oss.internal:8000/v1"
$env:GPT_OSS_API_KEY  = "EMPTY"     # 없으면 EMPTY
$env:GPT_OSS_MODEL    = "gpt-oss-120b"
```

### 3.3 실행

```powershell
# 마이헬스 파트너 약관(기본)으로 두 모델 모두 실행
.\run_poc.ps1

# 알파Plus 약관으로 실행
.\run_poc.ps1 --target alpha

# 한쪽만 실행 (예: GPT-OSS 엔드포인트 미준비)
.\run_poc.ps1 --skip-gpt-oss
.\run_poc.ps1 --skip-claude
```

### 3.4 산출물 (`data/result/`)

| 파일 | 내용 |
|---|---|
| `Logic_Diagnosis_Code__Claude_Opus_4.7.txt` | Claude 의 Phase 1 추출 로직 |
| `Logic_Diagnosis_Code__GPT_OSS.txt` | GPT-OSS 의 Phase 1 추출 로직 |
| `Result_Diagnosis_Code__Claude_Opus_4.7.xlsx` | Claude 추출 결과 (담보별 코드/신뢰도/근거) |
| `Result_Diagnosis_Code__GPT_OSS.xlsx` | GPT-OSS 추출 결과 |
| `Comparison_Report_{target}_{ts}.xlsx` | **CIO 보고용 비교 리포트** |
| `run_{target}_{ts}.log` | 전체 실행 로그 |

---

## 4. 비교 리포트 (Comparison_Report.xlsx) 시트 구성

1. **요약** — 모델별 추출 성공률, Confidence high 비율, 토큰 사용량, API 호출수
2. **모델간_일치율** — 두 모델이 같은 코드를 도출한 비율 (일치/불일치/양쪽 미추론)
3. **담보별_비교** — 담보별 좌우 비교 (코드 / Confidence / Source / Ref_Page / 근거 문장)
4. **Claude_원본** — Claude 단독 결과
5. **GPTOSS_원본** — GPT-OSS 단독 결과

---

## 5. CIO 보고 시 핵심 비교 포인트

1. **추론 성공률** — 빈칸("") 비율 차이 → 약관에서 근거를 찾지 못한 비율
2. **Confidence high 비율** — 약관 직접 근거 기반 추론 비율 (의료/보험 도메인 이해도)
3. **모델 간 일치율** — 두 모델이 같은 코드를 낼수록 단순한 case, 불일치 case 는 별표/외부지식 활용 여부에 따라 갈림
4. **근거 문장 품질** — `Code_Mapping_Reason` 컬럼에서 별표 인용 여부, 페이지 번호 정확도
5. **별표(Appendix) 인용율** — `Source == appendix` 비율 (PDF 멀티모달 + 장문 컨텍스트 이해도)
6. **JSON 출력 안정성** — 파싱 실패 / 재시도 발생 빈도 (로그 확인)

---

## 6. 한계 및 보완 (Disclaimers)

- 두 모델 모두 **같은 텍스트 추출본**을 입력으로 사용한다 (PDF → pdfplumber/pypdf 텍스트). Claude 의 native PDF 멀티모달은 사용하지 않으므로, **Claude 의 실제 성능 상한선은 본 비교보다 높을 수 있다**.
- GPT-OSS 의 결과는 사내 호스팅 환경(GPU·양자화·max_tokens 설정)에 따라 변동될 수 있다.
- 동일 약관에 대해 여러 회 실행 시 LLM 의 비결정성(temperature=0 으로 통제하나 완전 동일은 아님)으로 작은 차이가 발생할 수 있다.
- 본 PoC 는 진단코드 1개 속성만 비교한다. 9개 전체 속성 비교는 추후 확장 가능.
