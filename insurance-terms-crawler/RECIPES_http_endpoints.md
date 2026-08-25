# 보험사 약관 HTTP 수집 레시피 (검증됨 2026-06-30)

> **핵심 성과**: 6개사 중 5개사(삼성화재 자사 + DB·KB·현대·메리츠 타사) 모두 **브라우저 없이 `requests`만으로**
> 보험약관 PDF 직접 수집 가능함을 실측 검증. 회사별 약관 10개씩(합계 50개) 다운로드·검증 완료.
> → 기존 Playwright(SPA 렌더링) 접근을 **HTTP 직접 호출**로 대체한다. 삼성생명은 리스트 확정 후 추가.

공통: `requests.Session` + 정상 Chrome User-Agent + 목록페이지 GET으로 세션쿠키 확보 → 데이터 조회 → PDF GET.
약관 식별은 메커니즘별 필드/접미사로 하고, 최종적으로 pypdf 1~3페이지 텍스트에 '약관' 포함 & '사업방법서/요약서/설명서'로 시작하지 않음으로 재검증.

---

## 1. 삼성화재 (자사) — GET XML
- **목록(전상품 9,273건)**: `GET https://www.samsungfire.com/vh/page/VH.RPMY0133.do` → XML.
  노드 `<product name=..>` 필드: `productcode`, `gubun`, `sellstart(YYYYMMDD)`, `sellend`, `productgun/productgubun`, `prdfilename1~4(Y/N)`.
- **약관 PDF**: `GET /publication/pdf/{productcode}_{gubun}_{sellstart}_file{N}.pdf` (단순 GET, 로그인·세션 불필요).
  **`file1`=보험약관**, file2=사업방법서, file3/4=요약서/설명서 (3개 상품 본문 검증).
- **엑셀 매칭**: `상품리스트_260617_v2.xlsx/장기상품목록` 의 `상품코드(ZPRCD)` ↔ XML `productcode`. 약관필요(Y) 1,912건 중 **1,278건 코드 매칭**.
- 상태: ✅ 10/10 (2026 최신본, 엑셀 Y-리스트 매칭).

## 2. DB손보 — POST JSON (Step2→3→4)
- 전송: POST `application/json` (body=JSON.stringify). 목록페이지 `GET /FWMAIV1534.do`로 쿠키.
- 카테고리: 페이지의 `getStep2('장기보험','Off-Line','건강'...)` triplet (채널 Off-Line/TM·CM/방카, 중분류 간병/건강/상해/연금/운전자/재물/저축/질병).
- 체인:
  - `POST /insuPcPbanFindProductStep2_AX.do` body=`{arc_knd_lgcg_nm, sl_chn_nm, arc_knd_mdcg_nm, arc_pdc_sl_yn:"1"}` → `result[].PDC_NM`
  - `POST /insuPcPbanFindProductStep3_AX.do` body=위 + `{pdc_nm:PDC_NM}` → `result[].SQNO`(판매시기별 버전, SL_STR_DT/SL_FIN_DT)
  - `POST /insuPcPbanFindProductStep4_AX.do` body=위 + `{sqno:SQNO}` → `result[0].INPL_FINM`(약관), BIZ_MDDC_FINM(사방), CNSL_SMAR_FINM(요약)
- **약관 PDF**: `GET /cYakgwanDown.do?FilePath=InsProduct/{INPL_FINM}` (예 INPL_FINM=`약관_31085(03)_20260101.pdf`).
- 판매중지(과거 개정본)는 `/FWMAIV1535.do` 의 대응 엔드포인트.
- 상태: ✅ 10/10 (판매중). ⚠ 엑셀 DB리스트는 대부분 **판매중지**라 정확 매칭엔 1535 + 이름정규화 필요.

## 3. 메리츠화재 — POST JSON 게이트웨이 (json.smart)
- 단일 게이트웨이: `POST https://www.meritzfire.com/json.smart?v=2.0.82` (Content-Type application/json).
  body=`{"header":{rcvmsgSrvId:서비스ID, encryDivCd:'0', reqRespnsDivCd:'Q', syncDivCd:'S', langDivCd:'KR', transGrpCd:'F', screenId:'/disclosure/product-announcement/product-list.do', teleMsgReqDttm:타임스탬프, ...빈문자열}, "body":{...}}`. 성공=`header.prcesResultDivCd=='0'`.
- 서비스ID:
  - `f.cg.he.cu.ua.o.bc.PbanBc.retrievePdList` body=`{notfYn:'Y', srtSq:'1'~'16'}` → 카테고리/상세상품(nwPdCd, ttlNm)
  - `f.cg.he.cu.ua.o.bc.PbanBc.retrieveSalPdListForCdNm` body=`{notfYn:'Y', nwPdCd:상품코드}` → `salPdList`, 각 항목 **file1=약관**/file2=사방/file3=요약/file4=설명, + 세션암호화값 `file1#[E]`, ttlNm, putupStDdTm.
- **약관 PDF(2단계, 동일 Session)**: orgFileName=`makeURIParam(ttlNm+'약관.pdf')`
  - STEP1 `POST /hp/fileDownload.do` data=`{path:file1#[E], id:file1#[E], orgFileName, check:'Y'}` → `{resultMsg:''}`(통과)
  - STEP2 `GET /hp/fileDownload.do?path=file1#[E]&id=file1#[E]&orgFileName=..&check:'N'` → PDF
  - ⚠ `file1#[E]`는 세션쿠키 종속 → 목록조회와 다운로드를 같은 Session에서.
- WAF: 정상 UA+Referer+Origin이면 통과(폴백 불필요). 상태: ✅ 10/10.

## 4. 현대해상 — POST JSON (ajax.xhi, 2-tran)
- 단일 엔드포인트: `POST https://www.hi.co.kr/ajax.xhi` (application/json).
  body=`{"header":{gId:<12hex+18digit>, tranId:<전문>, channelId:"HI-HOME", clientIp:"127.0.0.1", menuId:"100931", loginId:null}, "request":{...}}`. 쿠키는 `/bin/CI/ON/CION3200G.jsp` GET.
- **목록**: tranId=`HHCA0310M38S`, request=`{}` → `data.slYProdList`(판매중 2,326)/`slNProdList`(판매중지 4,479). 행: prodNm, prodCatCd(03=장기), slStDt, **clauApnflId(약관 UUID)**, userMthdApnflId(사방), prodSmryApnflId(요약), prodNoteApnflId(설명).
- **약관 파일 해석**: tranId=`HHCA0310M26S`, request=`{apnflId:clauApnflId}` → `savPath`(예 /data/202606), `savFileNm`(해시), `flExts`(pdf), `originalFileNm`('..._약관.pdf').
- **약관 PDF**: `GET /FileActionServlet/preview/0{savPath}/{savFileNm}.{flExts}` (예 `/FileActionServlet/preview/0/data/202606/{hash}.pdf`).
  ⚠ 직접 `/data/...` GET은 404 — 반드시 `/FileActionServlet/preview/0` 접두.
- 상태: ✅ 10/10. (상품명에 `(Hi####)` 코드 포함 → 엑셀 매칭 키로 유용.)

## 5. KB손보 — form POST (CG802030001→002→003.ec)
- 목록: `GET /CG802030001.ec`(쿠키+HTML). 행에 `detail('bojongNo','gubun','bojongSeq')`. 페이징=같은 URL form POST, `devonTargetRow`=1,11,21...
- 상세: `POST /CG802030002.ec` body(urlencoded)=`{depth1:2, depth2:3, devonTargetRow:1, gubun, bojongNo, bojongSeq, ...}` → 약관표(td: 판매시작/종료/**보험약관**/사방/요약/설명).
- **약관 PDF**: 파일명 패턴 `{YYYYMMDD}_{bojongNo}_{N}.pdf` (**`_1`=보험약관**, _2=사방, _3=요약). 다운로드 프록시 `GET /CG802030003.ec?fileNm={파일명}`.
- ⚠ **fileNm은 EUC-KR 퍼센트인코딩**으로 보내야 PDF가 내려옴(`quote(fileNm, encoding='euc-kr')`). UTF-8로 보내면 서버가 EUC-KR 오류 HTML 반환.
- 판매중지(LIG 등 구상품)는 `search_onsale_yn=N`. LIG 구약관은 1~3p가 '개인신용정보 안내' 표지라 약관 텍스트가 p4~6부터 → 검증 시 앞 6p 스캔.
- 정적 직접 GET도 가능: `/extrnl/clause/ltins/{코드}.pdf`(장기/인보험), `/images/clause/gnins/{파일}.pdf`(일반), `direct.kbinsure.co.kr/dwlddoc/`(다이렉트).
- 상태: ✅ 10/10. ⚠ 받은 10건이 일반손보(화재/배상)라 엑셀 KB(장기인보험) 매칭 0건 → `search_gubun`(질병d/통합a) 지정 또는 전수 페이징 후 이름매칭 필요.

## 6. 삼성생명 — Vue SPA + form 게이트웨이 + XView 뷰어 (검증됨)
> 협회 통합공시(pub.insure.or.kr)는 **상품요약서만**(약관 없음). 약관은 **자사 samsunglife.com**.
- 목록 API(**form-urlencoded!** JSON이면 "필수 입력 항목" 에러): `POST https://www.samsunglife.com/gw/api/product/disclosure/product/prdt/salesPrdtList`(판매중) / `salesAllPrdtList`(전체) / `salesStopPrdtList`(판매중지).
  body=`{mCode,gCode,sCode,searchYear,goodsName,pageNo,pageRows}`, **"전체"=공백 `" "`**(빈문자 아님). 응답 `response[]`: goodsName, goodsCode, fromdate(판매개시), mCode(개인/단체상품/방카슈랑스/온라인/제도성특약/법인상품), totalRows.
- **약관 PDF (개인 등 비법인) 3단계**:
  1. `GET https://pcms.samsunglife.com/partnerpage/CustomerPage_Unit.jsp?goodsCode={goodsCode}&docType=301&saleDate={fromdate}&pageGubun=prdt` → HTML의 `var listAll=[[name,'{docID}','PDF']]` 에서 **docID** 추출.
  2. `GET https://pcms.samsunglife.com/XView.do?docID={docID}&name={enc}&isDown=false&loadingType=1` → HTML(kukuviewer)의 `"filepath":'../uploadDir/doc/{YYYY}/{MMDD}/{goodsCode[:9]}/301/{docID}.pdf'` 추출.
  3. `GET` urljoin(PCMS, filepath) → PDF.
- **docType 301=보험약관** (101=상품요약서, 401=사업방법서).
- 법인상품: 목록 응답의 `filepath1/filename1`(=약관) → `pcms.../partnerpage/CustomerPage_Corp.jsp?path={filepath1}&fname={filename1}`.
- 특약(rider, 상품명에 '특약')은 본상품 아님 → 필요 시 제외.
- 상태: ✅ 판매중 본상품 약관 10/10 검증(111~1,020p).

---

## 본구축 적용 메모
- 어댑터를 **Playwright → HTTP(requests)** 로 전환 가능(메리츠/현대만 세션·암호화값/2단계 주의).
- "판매시기별 전체 개정본": 각 사 버전 키 — 삼성화재 sellstart, DB SQNO·SL_STR_DT, 현대 slStDt, 메리츠 putupStDdTm, KB 판매시작일. **판매중+판매중지 모두** 순회.
- 약관 식별: 삼성화재 file1 / DB INPL_FINM / 메리츠 file1 / 현대 clauApnflId / KB _1. + pypdf 본문 재검증.
- 엑셀 리스트 정확 매칭: 상품명 정규화(무배당·괄호·판매시기 제거) + 코드(삼성화재 productcode, 현대 Hi####) 활용.
