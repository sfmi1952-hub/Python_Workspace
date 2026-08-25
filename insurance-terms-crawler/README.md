# 보험사 약관(보험약관) 크롤러

삼성화재(자사) + 삼성생명·메리츠화재·현대해상·DB손해보험·KB손해보험(타사)의 **공시실에 공개된 보험약관 PDF**를
프로그램으로 수집한다. 약관정보 추출 구축사업 벤더 제공용.

> 약관은 보험업법상 **공시 의무가 있는 공개자료**다. 다만 협회 포털 등은 robots/이용약관 정책이 있으니
> 요청 간격(rate-limit)·정상 User-Agent를 지키고, 필요 시 수집 근거(공개 공시자료)를 명확히 하라.

## 핵심 설계

```
목록/키 수집(Phase1)            PDF 다운로드(Phase2)
─────────────────────         ─────────────────────
삼성생명  : 협회 HTTP-only  ─┐
손보 5개사: Playwright 렌더 ─┼─▶ 공용 GET 다운로더 ─▶ downloads/<회사>/ + index.sqlite
            (DOM 약관링크)   ┘     (pdf_url 단위 버전 dedup, 약관만 필터)
```

- **버전 정책**: `pdf_url` 1개 = 1버전. 같은 상품의 **판매시기/개정본을 각각 보존**(덮어쓰기 없음).
  파일명: `downloads/<회사>/<상품명>__<개정일>__<해시>.pdf`
- **문서범위**: **보험약관 전용**. 사업방법서·상품요약서·설명서는 `utils.is_terms_doc()`가 파일명/약관명/컬럼헤더로 제외.
- **인덱스/매니페스트**: `index.sqlite`(재실행 시 받은 버전 자동 스킵), `downloads/manifest.csv`(엑셀 검수용, UTF-8-SIG).

## 설치

```powershell
cd C:\Users\Shin-Nyum\Desktop\Python_Workspace\insurance-terms-crawler
pip install -r requirements.txt
python -m playwright install chromium
```

## 실행

```powershell
# 회사 목록
python run.py --list

# 가장 가벼운 검증(브라우저 불필요, 협회 HTTP) — 5건만
python run.py --companies samsung_life --limit 5

# 개별 회사
python run.py --companies db_insurance --debug --headful

# 6개사 전체
python run.py --companies all
```

| 옵션 | 설명 |
|---|---|
| `--companies` | `all` 또는 콤마구분 키(`samsung_fire,samsung_life,meritz_fire,hyundai_marine,db_insurance,kb_insurance`) |
| `--limit N` | 회사별 최대 N건만(스모크 테스트) |
| `--headful` | 브라우저 창 표시 |
| `--debug` | 렌더된 HTML을 `logs/<회사>_rendered.html`로 덤프(셀렉터 튜닝용) |

## 회사별 수집 방식 (요약)

| 회사 | 진입 | PDF 취득 | 특이점 |
|---|---|---|---|
| 삼성생명 | 자사 `samsunglife.com/.../disclosure/...` (SPA) | 보험약관 컬럼 링크 GET | ⚠ 생보협회 비교공시는 **요약서만**(약관 없음, 실측 확인) → 자사 사이트로 수집 |
| DB손해보험 | `idbins.com/FWMAIV1534·1535.do` | `/pcweb/bizxpress/pdc/...pdf` GET | 한글 파일명, 판매중+판매중지 |
| 삼성화재 | `samsungfire.com/.../VH.REIF0012.do` | `/publication/pdf/{코드}_0_{개정일}_file1.pdf` GET | Angular SPA, 약관 컬럼만 |
| KB손해보험 | `kbinsure.co.kr/CG802030001.ec` | `/extrnl/clause`·`/images/clause`·`/dwlddoc/` GET | detail() 클릭 후 약관 링크 |
| 현대해상 | `hi.co.kr/.../CION3200G.jsp` | `/FileActionServlet/.../{YYYYMM}/{파일}.pdf` GET | 해시 파일명→목록 의존 |
| 메리츠화재 | `meritzfire.com/.../product-list.do` | onclick/AJAX → GET | **WAF**(정상 UA 필요), 실패 시 KNIA 폴백 |

## 검증 결과 (2026-06-30, 실측)

- **다운로드 파이프라인·버전 dedup·파일명 한글복구(이중 UTF-8) = 정상 작동** 확인.
- **생명보험협회 통합공시(pub.insure.or.kr 비교공시)는 '상품요약서'만 제공, '보험약관' 전문 없음**
  (컬럼=상품요약서 단일, 약관 0건, FileDown 파일명 전부 `...요약서.pdf`). → 삼성생명 약관은 **자사 공시실**에서 수집하도록 변경.
- 6개사 목록 페이지가 모두 SPA(JS 렌더)라, 아래 '튜닝 지점'의 셀렉터/토큰을 라이브 1회 캡처로 보정해야
  실제 약관이 채워진다(프레임워크/필터/다운로더/버전관리는 검증됨).

## 튜닝이 필요할 수 있는 지점 (중요)

손보 5개사 목록 페이지는 자바스크립트로 렌더되는 SPA다. **PDF 추출·필터·다운로드·버전관리 로직은 범용으로 견고**하지만,
각 사이트의 **검색 버튼/상품군 선택/판매기간 위젯/페이지네이션 셀렉터**는 사이트 개편에 따라 달라질 수 있어
**최초 1회 라이브 튜닝**이 필요할 수 있다. 절차:

1. `--debug --headful` 로 실행 → `logs/<회사>_rendered.html` 와 화면을 확인.
2. 브라우저 DevTools(Network)로 목록 로딩 XHR·약관 다운로드 onclick 함수/파라미터를 1회 캡처.
3. 해당 어댑터(`adapters/<회사>.py`)의 클릭 텍스트/셀렉터·`TOKENS`·날짜범위 부분만 보정.

'전체 개정본'을 위해선 각 사 **판매기간 범위를 넓게**(예: 2010~오늘) 설정하고 **판매중지 목록**까지 포함해야 한다
(DB는 1535.do로 이미 반영). 날짜 위젯 조작이 사별 튜닝의 핵심.

## 구조

```
config.py            경로/정중함/회사 레지스트리
utils.py             약관판별·파일명·인코딩·링크추출 JS
models.py            TermRecord + SQLite 버전 인덱스
downloader.py        공용 GET 다운로더(dedup·rate-limit·약관 재검증)
adapters/base.py     BaseAdapter + Runtime + 약관링크 추출
adapters/*.py        회사별 어댑터 6종
run.py               오케스트레이터(CLI)
```
