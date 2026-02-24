# Insurance Extraction System

**보험 약관 정보 추출 시스템** &mdash; AI 기반 보험 약관 PDF에서 정형 데이터를 자동 추출하는 End-to-End 파이프라인

> 약관 PDF 수집부터 상품마스터DB 적재까지, 12개 모듈로 구성된 프로덕션 시스템

---

## Table of Contents

- [Overview](#overview)
- [System Architecture](#system-architecture)
- [Data Pipeline](#data-pipeline)
- [Module Reference](#module-reference)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Getting Started](#getting-started)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Web UI](#web-ui)
- [Extraction Attributes](#extraction-attributes)
- [How It Works](#how-it-works)

---

## Overview

보험 약관 PDF에서 진단코드, 면책코드, 수술분류코드 등 **9가지 핵심 속성**을 AI로 자동 추출하고, 룰 기반 매핑과 앙상블 교차검증을 거쳐 상품마스터DB에 적재하는 시스템입니다.

### 핵심 특징

| 특징 | 설명 |
|------|------|
| **Multi-LLM 앙상블** | Gemini, GPT, Claude 3개 프로바이더 지원. 2-모델 교차투표로 정확도 극대화 |
| **2-Phase 추출** | Phase 1 (광범위 분석) + Phase 2 (정밀 추론) 이중 파이프라인 |
| **HITL 리뷰** | Confidence 95% 미만 결과는 Human-in-the-Loop 리뷰 큐로 자동 분류 |
| **룰 기반 매핑** | FCDF131 매핑 테이블 기반 KCD 코드 변환 (정확도 100%) |
| **사외/사내 분리** | 보안 게이트웨이를 통한 CSV 전송으로 사외망-사내망 격리 |
| **RAG 지원** | 과거 정답셋, 가이드라인 문서를 벡터 스토어에 인덱싱하여 Few-shot 동적 주입 |

---

## System Architecture

시스템은 **사외망**, **보안 게이트웨이**, **사내망** 3개 존(Zone)으로 분리됩니다.

```
┌─────────────────────────────────────────────────────────────────────────┐
│  사외망 (External Network) — AI 추출 시스템 + 클라우드 인프라            │
│                                                                         │
│  ┌──────────┐    ┌──────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ M1       │    │ M2       │    │ M3           │    │ M4           │  │
│  │ 약관수집 │ ──→│ 약관저장소│ ──→│ 전처리 엔진  │ ──→│ RAG 인덱싱   │  │
│  │ Crawler  │    │ Storage  │    │ Preprocessor │    │ Indexer      │  │
│  └──────────┘    └──────────┘    └──────────────┘    └──────┬───────┘  │
│                                                              │          │
│                                                              ▼          │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │ M5  AI 추출 엔진 (Core)                                         │  │
│  │ ┌────────────────┐  ┌────────────────┐  ┌───────────────────┐   │  │
│  │ │ Gemini 3.x Pro │  │ Claude / GPT   │  │ Ensemble 검증     │   │  │
│  │ │ PDF 이해·별표   │  │ 구조화 출력    │  │ 교차투표·Conf.    │   │  │
│  │ └────────────────┘  └────────────────┘  └───────────────────┘   │  │
│  └──────────────────────────────────────────────────┬───────────────┘  │
│                                                      │                  │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────▼───────┐         │
│  │ M8           │    │ M7           │    │ M6               │         │
│  │ Output DB    │ ◀──│ 검증·리뷰    │ ◀──│ 매핑 엔진        │         │
│  │ CSV Export   │    │ HITL         │    │ FCDF131 Rule     │         │
│  └──────┬───────┘    └──────────────┘    └──────────────────┘         │
│         │                                                               │
└─────────┼───────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  GW1  보안 게이트웨이 — SFTP · SHA-256 체크섬 · IP Whitelist            │
└─────────┬───────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  사내망 (Internal Network) — 상품마스터DB + 보상 시스템                   │
│                                                                         │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │ I1           │    │ I2           │    │ I3                      │  │
│  │ CSV 수신     │ ──→│ DB 연동      │ ──→│ 상품마스터DB (Oracle)    │  │
│  │ Receiver     │    │ Sync         │    │ → 보상시스템 참조        │  │
│  └──────────────┘    └──────────────┘    └──────────────────────────┘  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Data Pipeline

약관 수집부터 DB 적재까지 **10단계** 데이터 파이프라인:

| Step | 모듈 | 처리 내용 | 데이터 흐름 |
|:----:|------|----------|------------|
| **1** | M1 → M2 | 약관 수집 | 공시페이지 → PDF 저장소 |
| **2** | M2 → M3 | 전처리 | PDF → 구조화 텍스트(Markdown) |
| **3** | M3 → M4 | 인덱싱 | 청크 → 벡터 스토어 |
| **4** | M4 → M5 | AI 추출 | LLM 추론 + RAG 검색 |
| **5** | M5 → M6 | 코드 매핑 | 질병분류번호 → 코드값 |
| **6** | M6 → M7 | 검증 | 자동확정 / HITL 리뷰 분류 |
| **7** | M7 → M8 | 저장 | 확정 결과 → Output DB |
| **8** | M8 → GW1 | 전송 | CSV 보안 전송 (SFTP) |
| **9** | GW1 → I1 | 수신 | CSV 수신 · 무결성 검증 |
| **10** | I1 → I2 | 적재 | 상품마스터DB INSERT/UPDATE |

---

## Module Reference

### 사외망 모듈 (External Network)

#### M1 — 약관 수집 모듈 (`m1_crawler`)
- 보험사 공시 웹페이지에서 약관 PDF 자동 다운로드
- 상품유형별 분류 (건강/자동차/화재/생명 등)
- 신규 출시 및 개정 약관 자동 감지 (diff 비교)
- **Tech**: Python, Playwright, BeautifulSoup

#### M2 — 약관 저장소 (`m2_storage`)
- 계층형 폴더 구조: `/{상품유형}/{상품명}/v{버전}/`
- 원본 PDF + 전처리 결과 보관 및 버전 관리
- 메타데이터 JSON 관리 (상품코드, 담보수, 처리상태)
- **Tech**: File System (S3 호환 인터페이스)

#### M3 — 전처리 엔진 (`m3_preprocessor`)
- PDF → 텍스트 추출 (pdfplumber 우선, pypdf 폴백)
- 약관 구조 파싱: 조/항/호 계층 인식 (정규식)
- 별표 섹션 분리 및 인덱싱
- 담보별 청킹 및 Markdown 캐싱
- **Tech**: pdfplumber, pypdf, pandas

#### M4 — RAG 인덱싱 모듈 (`m4_rag_indexer`)
- 약관 원문, 과거 정답셋, 가이드라인을 벡터 스토어에 인덱싱
- OpenAI File Search API 또는 Gemini Files API 지원
- 상품별/담보별 검색 스코프 태깅
- FCDF131 매핑테이블도 LLM 질의응답용으로 인덱싱
- **Tech**: OpenAI Embedding, Gemini Files

#### M5 — AI 추출 엔진 (`m5_extraction_engine`) `CORE`
- **모델 라우터**: config 기반 LLM 선택 (Gemini / OpenAI / Claude)
- **Phase 1**: 광범위 분석 (약관 원문 + 매핑 테이블 + 외부 지식)
- **Phase 2**: 정밀 추론 (합의 도출 + 별표 우선)
- **앙상블 검증**: 2개 모델 교차투표, Confidence Score 산출
- **프롬프트 관리**: 9가지 속성별 맞춤 프롬프트 템플릿
- **Tech**: google-generativeai, openai, anthropic

##### 지원 프로바이더

| Provider | 기본 모델 | 폴백 모델 | 파일 업로드 | 벡터 스토어 |
|----------|----------|----------|:-----------:|:-----------:|
| Gemini | gemini-3.1-pro | gemini-3.0-pro, 1.5-pro | O | O |
| OpenAI | gpt-5.2 | gpt-4.1-mini | O | O |
| Claude | claude-sonnet-4-6 | claude-haiku-4-5 | O (Base64) | X |

#### M6 — 매핑 엔진 (`m6_mapping_engine`)
- FCDF131.xlsx 매핑 테이블 로드 및 캐싱 (2,876행)
- KCD 코드 범위 비교 로직 (FROM <= code <= TO)
- 진단코드/면책코드 분리 매핑 처리
- **Tech**: pandas, LRU Cache

#### M7 — 검증/리뷰 모듈 (`m7_validation`)
- Confidence >= 95%: **자동 확정** → Output DB 직행
- Confidence < 95%: **HITL 리뷰 큐** 등록
- 웹 기반 리뷰 대시보드 (승인/반려/수정)
- 수정 데이터 피드백 DB 축적 (모델 개선용)
- **Tech**: FastAPI, SQLAlchemy

#### M8 — Output DB (`m8_output_db`)
- 확정된 정형데이터 저장 (19개 컬럼 CSV 스키마)
- 상품 단위 CSV 배치 생성 및 전송 대기 큐 관리
- **Tech**: PostgreSQL (prod) / SQLite (dev), CSV Export

### 보안 게이트웨이

#### GW1 — 파일 전송 게이트웨이 (`gw1_gateway`)
- SFTP 암호화 전송 (또는 개발환경 로컬 복사)
- SHA-256 체크섬 무결성 검증
- 실패 시 최대 3회 재전송 + 알림
- 전송 로그 기록 (TransferLog 테이블)
- **Tech**: paramiko (SFTP)

### 사내망 모듈 (Internal Network)

#### I1 — CSV 수신 에이전트 (`i1_receiver`)
- SFTP 수신 디렉토리 모니터링
- CSV 파일 포맷 검증 (컬럼 스키마 확인)
- 데이터 무결성 체크 (건수, 체크섬) 및 ACK 전송

#### I2 — DB 연동 모듈 (`i2_db_sync`)
- CSV → 상품마스터DB 테이블 매핑 변환
- KEY: 상품코드 + 담보코드 + 세부담보코드
- 신규 INSERT / 변경 UPDATE (diff 비교)
- 적재 전 기존 데이터 백업 (롤백 대비)

---

## Tech Stack

### Backend
| 범주 | 기술 |
|------|-----|
| Framework | FastAPI, Uvicorn |
| Database | SQLAlchemy 2.0, SQLite (dev) / PostgreSQL (prod) |
| PDF 처리 | pdfplumber, pypdf |
| AI/LLM | google-generativeai, openai, anthropic |
| 파일 전송 | paramiko (SFTP) |
| 크롤링 | Playwright, BeautifulSoup4 |
| 데이터 처리 | pandas, openpyxl |

### Frontend
| 범주 | 기술 |
|------|-----|
| Framework | React 19 |
| Build | Vite 7 |
| Styling | TailwindCSS 4 |
| HTTP | Axios |
| Icons | Lucide React |

---

## Project Structure

```
InsuranceExtractionSystem/
├── api/                          # FastAPI REST API 레이어
│   ├── main.py                   #   앱 진입점 (Lifespan, CORS, 라우트 등록)
│   ├── schemas.py                #   Pydantic 요청/응답 스키마
│   └── routes/
│       ├── extraction.py         #   추출 API (단건/배치)
│       ├── review.py             #   HITL 리뷰 API
│       ├── pipeline.py           #   파이프라인 오케스트레이션 API
│       └── admin.py              #   시스템 관리 API
│
├── config/
│   └── settings.py               # 전역 설정 (환경변수 기반)
│
├── db/
│   ├── models.py                 # ORM 모델 (Policy, ExtractionResult 등 5개 테이블)
│   └── session.py                # DB 엔진 & 세션 관리
│
├── modules/                      # 12개 모듈
│   ├── m1_crawler/               #   약관 수집
│   ├── m2_storage/               #   약관 저장소
│   ├── m3_preprocessor/          #   전처리 엔진
│   ├── m4_rag_indexer/           #   RAG 인덱싱
│   ├── m5_extraction_engine/     #   AI 추출 엔진 (Core)
│   │   ├── engine.py             #     추출 오케스트레이터
│   │   ├── ensemble.py           #     앙상블 교차검증
│   │   ├── model_router.py       #     프로바이더 팩토리/라우팅
│   │   ├── prompts.py            #     9속성 프롬프트 템플릿
│   │   └── providers/
│   │       ├── base.py           #     추상 프로바이더 인터페이스
│   │       ├── gemini_provider.py
│   │       ├── openai_provider.py
│   │       └── claude_provider.py
│   ├── m6_mapping_engine/        #   룰 기반 매핑
│   ├── m7_validation/            #   검증·HITL 리뷰
│   ├── m8_output_db/             #   Output DB · CSV 내보내기
│   ├── gw1_gateway/              #   SFTP 보안 전송
│   ├── i1_receiver/              #   CSV 수신·검증
│   └── i2_db_sync/              #   상품마스터DB 동기화
│
├── pipeline/
│   └── orchestrator.py           # 9단계 파이프라인 오케스트레이터
│
├── web_ui/                       # React 프론트엔드
│   ├── src/
│   │   ├── App.jsx               #   메인 앱 (탭 네비게이션)
│   │   └── components/
│   │       ├── Dashboard.jsx     #   대시보드 (통계·현황)
│   │       ├── ExtractionPanel.jsx  # 추출 실행 패널
│   │       ├── ReviewPanel.jsx   #   HITL 리뷰 패널
│   │       └── PipelineStatus.jsx   # 파이프라인 모니터링
│   ├── package.json
│   └── vite.config.js
│
├── data/                         # 런타임 데이터
│   ├── extraction.db             #   SQLite DB
│   ├── policy_storage/           #   약관 PDF 파일
│   ├── rag_cache/                #   전처리 Markdown 캐시
│   ├── mapping_tables/           #   FCDF131.xlsx 등
│   ├── csv_export/               #   CSV 내보내기
│   ├── transfer/                 #   SFTP 전송 스테이징
│   └── received/                 #   수신 CSV 파일
│
├── run.py                        # 서버 실행 진입점
└── requirements.txt              # Python 의존성
```

---

## Getting Started

### 사전 요구사항

- **Python** 3.10+
- **Node.js** 18+ (프론트엔드 빌드 시)
- AI 프로바이더 API 키 (최소 1개):
  - Google Gemini API Key
  - OpenAI API Key
  - Anthropic API Key

### 설치

```bash
# 1. 저장소 클론
git clone <repository-url>
cd InsuranceExtractionSystem

# 2. Python 가상환경 생성 및 활성화
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 3. Python 의존성 설치
pip install -r requirements.txt

# 4. 환경변수 설정 (.env 파일 생성)
cp .env.example .env  # 또는 직접 생성
```

### 환경변수 설정

프로젝트 루트에 `.env` 파일을 생성합니다:

```env
# AI Provider API Keys (최소 1개 필수)
GEMINI_API_KEY=your-gemini-api-key
OPENAI_API_KEY=your-openai-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key

# LLM 프로바이더 설정
PRIMARY_PROVIDER=gemini
SECONDARY_PROVIDER=openai

# 데이터베이스 (기본값: SQLite)
DATABASE_URL=sqlite:///data/extraction.db

# 검증 임계값
AUTO_CONFIRM_THRESHOLD=0.95
```

### 실행

```bash
# Backend 서버 실행 (포트 8000)
python run.py
```

Frontend 개발 서버가 필요한 경우:

```bash
# Frontend 의존성 설치 및 개발 서버 실행
cd web_ui
npm install
npm run dev
```

서버 실행 후:
- **API**: http://localhost:8000
- **API 문서 (Swagger)**: http://localhost:8000/docs
- **Web UI**: http://localhost:5175 (개발) 또는 http://localhost:8000 (빌드 후)

---

## Configuration

### 주요 설정 항목 (`config/settings.py`)

| 환경변수 | 기본값 | 설명 |
|---------|--------|------|
| `GEMINI_API_KEY` | - | Google Gemini API 키 |
| `OPENAI_API_KEY` | - | OpenAI API 키 |
| `ANTHROPIC_API_KEY` | - | Anthropic API 키 |
| `PRIMARY_PROVIDER` | `gemini` | 기본 LLM 프로바이더 |
| `SECONDARY_PROVIDER` | `openai` | 앙상블용 보조 프로바이더 |
| `DATABASE_URL` | `sqlite:///data/extraction.db` | DB 연결 문자열 |
| `MASTER_DB_URL` | - | 사내 상품마스터DB URL |
| `AUTO_CONFIRM_THRESHOLD` | `0.95` | 자동 확정 Confidence 임계값 |
| `CRAWLER_TARGET_URL` | `https://www.samsungfire.com` | 크롤링 대상 URL |
| `SFTP_HOST` | - | SFTP 서버 호스트 |
| `SFTP_USER` | - | SFTP 사용자명 |
| `SFTP_KEY_PATH` | - | SFTP 키 파일 경로 |

---

## API Reference

### 추출 (Extraction)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/extraction/analyze` | 단건 PDF 추출 (앙상블 옵션) |
| `GET` | `/api/extraction/results` | 추출 결과 목록 (페이지네이션, 필터) |
| `GET` | `/api/extraction/download/{id}` | 추출 결과 CSV 다운로드 |

### 리뷰 (HITL Review)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/review/pending` | 리뷰 대기 목록 |
| `POST` | `/api/review/{id}/decide` | 리뷰 결정 (승인/반려/수정) |
| `GET` | `/api/review/stats` | 리뷰 통계 |

### 파이프라인 (Pipeline)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `POST` | `/api/pipeline/trigger` | 전체 파이프라인 실행 |
| `GET` | `/api/pipeline/status` | 파이프라인 실행 상태 |
| `POST` | `/api/pipeline/export-csv` | CSV 내보내기 |
| `POST` | `/api/pipeline/transfer` | GW1 파일 전송 트리거 |
| `POST` | `/api/pipeline/validate` | M7 검증 실행 |

### 관리 (Admin)

| Method | Endpoint | 설명 |
|--------|----------|------|
| `GET` | `/api/admin/status` | 시스템 상태 |
| `POST` | `/api/admin/configure-provider` | LLM 프로바이더 설정 |
| `GET` | `/api/admin/providers` | 프로바이더 목록 |
| `GET` | `/api/admin/audit-logs` | 감사 로그 |
| `GET` | `/api/admin/transfer-logs` | 전송 이력 |
| `GET` | `/api/admin/storage` | 저장소 현황 |
| `GET` | `/api/admin/settings` | 현재 설정 (민감정보 마스킹) |

---

## Web UI

React 기반 웹 대시보드로 4개 탭을 제공합니다:

| 탭 | 컴포넌트 | 기능 |
|----|---------|------|
| **Dashboard** | `Dashboard.jsx` | 전체 통계, 최근 추출 현황, 시스템 상태 |
| **Extraction** | `ExtractionPanel.jsx` | PDF 업로드, 단건/배치 추출 실행, 결과 조회 |
| **Review** | `ReviewPanel.jsx` | HITL 리뷰 큐, 승인/반려/수정 워크플로우 |
| **Pipeline** | `PipelineStatus.jsx` | 파이프라인 실시간 모니터링, 단계별 진행 상태 |

---

## Extraction Attributes

시스템이 약관에서 추출하는 **9가지 핵심 속성**:

| # | 속성 | 코드명 | 설명 |
|:-:|------|--------|------|
| 1 | **진단코드** | `diagnosis_code` | KCD 질병분류코드 범위 (예: K00~K14) |
| 2 | **면책코드** | `exemption_code` | 보장 제외 질병/조건 코드 |
| 3 | **수술분류코드** | `edi_code` | EDI 수술/처치 분류코드 |
| 4 | **병원등급** | `hospital_grade` | 의료기관 등급 분류 |
| 5 | **병원분류** | `hospital_class` | 의료기관 유형 분류 |
| 6 | **사고유형** | `accident_type` | 사고 분류 (질병/상해/재해 등) |
| 7 | **입원한도일수** | `admission_limit` | 최대 입원 보장 일수 |
| 8 | **최소입원일수** | `min_admission` | 보장 시작 최소 입원 일수 |
| 9 | **보장기간** | `coverage_period` | 보험 보장 기간 |

---

## How It Works

### 1. 추출 프로세스 (Phase 1 + Phase 2)

```
                    ┌─────────────────────────────────────┐
                    │           약관 PDF 입력               │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  Phase 1: 광범위 분석                 │
                    │  - 약관 원문 + 매핑테이블 + 외부지식   │
                    │  - 9개 속성별 개별 프롬프트 실행       │
                    │  - JSON Schema 강제 출력              │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  Phase 2: 정밀 추론                   │
                    │  - Phase 1 결과를 컨텍스트로 주입      │
                    │  - 별표(부표) 우선 합의 도출           │
                    │  - 최종 코드값 확정                    │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  Ensemble 교차검증 (옵션)             │
                    │  - Primary + Secondary 모델 비교      │
                    │  - 일치 시 High Confidence             │
                    │  - 불일치 시 Primary 우선 + Low Conf.  │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────▼──────────────────────┐
                    │  FCDF131 룰 기반 매핑                  │
                    │  - KCD 코드 → 시스템 코드값 변환       │
                    │  - 범위 비교 로직 (100% 정확도)        │
                    └──────────────┬──────────────────────┘
                                   │
               ┌───────────────────┼───────────────────┐
               │                                       │
    ┌──────────▼──────────┐             ┌──────────────▼─────────┐
    │  Confidence >= 95%  │             │  Confidence < 95%      │
    │  → 자동 확정         │             │  → HITL 리뷰 큐        │
    │  → Output DB 저장    │             │  → 담당자 검토·수정     │
    └─────────────────────┘             └────────────────────────┘
```

### 2. 앙상블 검증 로직

두 LLM 모델의 결과를 비교하여 신뢰도를 산출합니다:

| 조건 | 결과 | Confidence |
|------|------|:----------:|
| 두 모델 결과 일치 | Primary 결과 채택 | **High** (0.95) |
| 결과 불일치, Primary High Conf. | Primary 결과 채택 | **Medium** (0.75) |
| 결과 불일치, 둘 다 Low Conf. | Primary 결과 채택 | **Low** (0.50) |

### 3. 데이터베이스 모델

시스템은 5개의 핵심 테이블을 사용합니다:

| 테이블 | 설명 |
|--------|------|
| `policies` | 약관 메타데이터 (상품코드, 유형, 상태, PDF 경로) |
| `extraction_results` | 추출 결과 (9개 속성, Confidence, 검증상태) |
| `review_queue` | HITL 리뷰 대기 항목 (담당자, 결정, 수정내용) |
| `transfer_logs` | 파일 전송 이력 (체크섬, 전송결과) |
| `audit_logs` | 감사 추적 (모든 시스템 이벤트) |

### 4. CSV Output 스키마

최종 CSV 출력에 포함되는 19개 컬럼:

```
상품코드, 상품명, 담보코드, 담보명, 세부담보코드, 세부담보명,
세부담보템플릿코드, 진단코드, 면책코드, 수술분류코드,
병원등급, 병원분류, 사고유형, 입원한도일수, 최소입원일수,
보장기간, confidence, 추출일시, 출처페이지
```

---

## License

Internal use only. All rights reserved.
