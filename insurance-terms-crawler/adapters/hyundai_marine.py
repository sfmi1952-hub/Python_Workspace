# -*- coding: utf-8 -*-
"""현대해상 — 보험상품공시 CION3200G.jsp (JS/AJAX 렌더).

약관 PDF는 정적 GET:
  /FileActionServlet/preview/{0|1}/data/{YYYYMM}/{파일명}.pdf  또는  /data/{YYYYMM}/{한글파일명}.pdf
파일명이 해시/타임스탬프라 약관명만으로 URL 생성 불가 → 목록에서 링크를 긁어야 함.
"""
import config as cfg
from adapters.base import BaseAdapter
from models import TermRecord


class HyundaiMarineAdapter(BaseAdapter):
    key = "hyundai_marine"
    name = "현대해상"
    needs_browser = True
    base_url = "https://www.hi.co.kr"
    LIST_URL = "https://www.hi.co.kr/bin/CI/ON/CION3200G.jsp"
    TOKENS = ["FileActionServlet", "/data/"]

    def discover(self, rt):
        page, seen = rt.page, set()
        try:
            page.goto(self.LIST_URL, wait_until="networkidle", timeout=cfg.NAV_TIMEOUT_MS)
        except Exception as e:
            rt.log(f"  goto 실패: {e}")
            return
        for t in ("조회", "검색", "전체"):
            try:
                page.get_by_text(t, exact=False).first.click(timeout=1500)
                rt.sleep(1.0)
            except Exception:
                pass
        rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
        if rt.debug:
            rt.dump(page, self.key)
        for it in self.terms_links(page, self.TOKENS, self.base_url):
            u = it["url"]
            if "FileActionServlet" not in u and not u.lower().endswith(".pdf"):
                continue
            if u in seen:
                continue
            seen.add(u)
            yield TermRecord(
                company=self.key, company_name=self.name,
                product_name=it["product"], terms_title=it["title"],
                pdf_url=u, referer=self.LIST_URL, source="official",
            )
            if rt.limit and len(seen) >= rt.limit:
                return
