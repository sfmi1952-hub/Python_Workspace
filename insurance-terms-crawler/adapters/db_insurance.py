# -*- coding: utf-8 -*-
"""DB손해보험 — 공시실 상품목록/기초서류(FWMAIV1534=판매중, 1535=판매중지).

약관 PDF는 정적 GET(/pcweb/bizxpress/pdc/...). 파일명이 한글 상품명+판매시기라 약관 판별 쉬움.
'판매시기별 전체 개정본'을 위해 판매중 + 판매중지 목록을 모두 순회한다.
"""
import re
import config as cfg
from adapters.base import BaseAdapter
from models import TermRecord

REV = re.compile(r"(\d{6})(?:\.pdf|적용|~|\))", re.I)


class DBInsuranceAdapter(BaseAdapter):
    key = "db_insurance"
    name = "DB손해보험"
    needs_browser = True
    base_url = "https://www.idbins.com"
    LIST_URLS = [
        "https://www.idbins.com/FWMAIV1534.do",   # 판매중
        "https://www.idbins.com/FWMAIV1535.do",   # 판매중지(과거 개정본)
    ]
    TOKENS = ["/pcweb/bizxpress/pdc/"]

    def discover(self, rt):
        page, seen = rt.page, set()
        for url in self.LIST_URLS:
            try:
                page.goto(url, wait_until="networkidle", timeout=cfg.NAV_TIMEOUT_MS)
            except Exception as e:
                rt.log(f"  goto 실패 {url}: {e}")
                continue
            # best-effort: 상품군 '전체' + 넓은 판매기간 + 조회 (셀렉터는 사이트 개편 시 튜닝)
            for t in ("전체", "조회", "검색"):
                try:
                    page.get_by_text(t, exact=False).first.click(timeout=1500)
                    rt.sleep(0.8)
                except Exception:
                    pass
            rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
            if rt.debug:
                rt.dump(page, self.key)
            for it in self.terms_links(page, self.TOKENS, self.base_url):
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                m = REV.search(it["url"])
                yield TermRecord(
                    company=self.key, company_name=self.name,
                    product_name=it["product"], terms_title=it["title"],
                    revision_date=(m.group(1) if m else ""),
                    pdf_url=it["url"], referer=url, source="official",
                )
                if rt.limit and len(seen) >= rt.limit:
                    return
