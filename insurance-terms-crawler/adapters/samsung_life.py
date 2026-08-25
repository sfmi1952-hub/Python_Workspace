# -*- coding: utf-8 -*-
"""삼성생명 (생명보험) — 자사 공시실(samsunglife.com)에서 '보험약관' 수집.

[검증 결과 2026-06-30]
  생명보험협회 통합공시(pub.insure.or.kr 상품비교공시)는 컬럼이 '상품요약서' 하나뿐이고
  '보험약관' 전문을 제공하지 않음(실측: 약관 0건, 다운로드 파일명 전부 ...요약서.pdf).
  따라서 삼성생명 '약관'은 자사 공시실에서 받아야 함.
  → 협회의 상품요약서 일괄수집 로직은 fetch_summaries_from_association() 에 보존(향후 교차검증용, 범위 밖).

자사 공시실은 강한 SPA(클라이언트 렌더 + /gw/ 게이트웨이 API)라 헤드리스 렌더 후
'보험약관' 컬럼의 PDF 링크를 추출한다. 정확한 PDF 경로/onclick 함수는 라이브 1회 캡처로
TOKENS 를 보정하면 견고해진다(튜닝 지점).
"""
import re

import config as cfg
from adapters.base import BaseAdapter
from models import TermRecord
from utils import decode_bytes

PUB = "https://pub.insure.or.kr"
MEMBER_SAMSUNG_LIFE = "L03"


class SamsungLifeAdapter(BaseAdapter):
    key = "samsung_life"
    name = "삼성생명"
    needs_browser = True
    base_url = "https://www.samsunglife.com"

    # 상품군별 공시 목록 페이지(보험약관 컬럼 보유)
    LIST_URLS = [
        "https://www.samsunglife.com/individual/products/disclosure/sales/PDO-PRPRI010110M",     # 보험상품목록
        "https://www.samsunglife.com/individual/products/disclosure/variable/PDO-PRPRV011100M",  # 변액
        "https://www.samsunglife.com/individual/products/disclosure/pension/PDO-PRPRP010100M",   # 연금저축
    ]
    # 자사 약관 PDF 경로 토큰(라이브 캡처로 보정 권장). 우선 광범위하게 .pdf + 다운로드 핸들러를 훑는다.
    TOKENS = [".pdf", "/gw/", "fileDown", "download", "clause", "약관"]

    def discover(self, rt):
        page, seen = rt.page, set()
        for url in self.LIST_URLS:
            try:
                page.goto(url, wait_until="networkidle", timeout=cfg.NAV_TIMEOUT_MS)
            except Exception as e:
                rt.log(f"  goto 실패 {url}: {e}")
                continue
            rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
            for t in ("조회", "검색", "전체"):
                try:
                    page.get_by_text(t, exact=False).first.click(timeout=1500)
                    rt.sleep(1.0)
                except Exception:
                    pass
            rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
            if rt.debug:
                rt.dump(page, self.key)
            # '보험약관' 컬럼/링크만 추려 수집(base.terms_links 의 컬럼헤더 필터)
            for it in self.terms_links(page, self.TOKENS, self.base_url):
                u = it["url"]
                if not u.lower().endswith(".pdf"):
                    continue  # SPA 다운로드 핸들러는 라이브 캡처로 토큰 보정 후 확장
                if u in seen:
                    continue
                seen.add(u)
                yield TermRecord(
                    company=self.key, company_name=self.name,
                    product_name=it["product"], terms_title=it["title"] or "약관",
                    pdf_url=u, referer=url, source="official",
                )
                if rt.limit and len(seen) >= rt.limit:
                    return

    # ── (범위 밖·보존) 생보협회 통합공시에서 '상품요약서' 일괄수집 ──────────────────
    # 약관이 아닌 상품요약서가 필요할 때만 사용. HTTP-only, stateless 로 검증됨.
    @staticmethod
    def fetch_summaries_from_association(session, member_cd=MEMBER_SAMSUNG_LIFE, max_pages=40):
        """yield (product_name, pdf_url). 다운로드 파일명은 '...요약서.pdf'."""
        FN = re.compile(r"fn_fileDown\(\s*'(\d+)'\s*,\s*'(\w+)'\s*\)")
        groups = [f"0244000100{n:02d}" for n in range(1, 12)]
        list_url = f"{PUB}/compareDis/prodCompare/assurance/list.do"
        session.get(list_url, timeout=30)
        seen = set()
        for grp in groups:
            for pidx in range(1, max_pages + 1):
                r = session.post(list_url,
                                 data={"pageIndex": str(pidx), "search_memberCd": member_cd,
                                       "search_prodGroup": grp},
                                 headers={"Referer": list_url}, timeout=30)
                html = decode_bytes(r.content)
                pairs = FN.findall(html)
                if not pairs:
                    break
                fresh = 0
                for no, seq in pairs:
                    url = f"{PUB}/FileDown.do?fileNo={no}&seq={seq}"
                    if url in seen:
                        continue
                    seen.add(url)
                    fresh += 1
                    yield ("", url)
                if fresh == 0:
                    break
