# -*- coding: utf-8 -*-
"""삼성화재(자사) — 보험상품공시 VH.REIF0012.do (Angular SPA).

약관 PDF는 정적 GET: /publication/pdf/{상품코드}_0_{개정일YYYYMMDD}_file1.pdf
사업방법서·상품요약서도 같은 경로라 '약관 컬럼'만 추려야 함(base.terms_links 의 컬럼헤더 필터).
"""
import re
import config as cfg
from adapters.base import BaseAdapter
from models import TermRecord

URLP = re.compile(r"/publication/pdf/([A-Za-z0-9]+)_0_(\d{8})_file\d+\.pdf")


class SamsungFireAdapter(BaseAdapter):
    key = "samsung_fire"
    name = "삼성화재"
    needs_browser = True
    base_url = "https://www.samsungfire.com"
    LIST_URL = "https://www.samsungfire.com/vh/page/VH.REIF0012.do"
    TOKENS = ["/publication/pdf/"]

    def discover(self, rt):
        page, seen = rt.page, set()
        try:
            page.goto(self.LIST_URL, wait_until="networkidle", timeout=cfg.NAV_TIMEOUT_MS)
        except Exception as e:
            rt.log(f"  goto 실패: {e}")
            return
        # 보험종류 탭을 돌며 조회. (판매기간 위젯은 사이트별 튜닝 지점 — 전체 개정본 확보 시 날짜 확장 필요)
        for tab in ("자동차", "장기", "일반", "퇴직"):
            try:
                page.get_by_text(tab, exact=False).first.click(timeout=1500)
                rt.sleep(1.0)
            except Exception:
                pass
            for t in ("조회", "검색"):
                try:
                    page.get_by_role("button", name=re.compile(t)).first.click(timeout=1500)
                    rt.sleep(1.2)
                except Exception:
                    pass
            rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
            for it in self.terms_links(page, self.TOKENS, self.base_url):
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                m = URLP.search(it["url"])
                code = m.group(1) if m else ""
                rev = m.group(2) if m else ""
                yield TermRecord(
                    company=self.key, company_name=self.name,
                    product_name=it["product"] or code,
                    terms_title=it["title"] or "약관",
                    product_code=code, revision_date=rev,
                    pdf_url=it["url"], referer=self.LIST_URL, source="official",
                )
                if rt.limit and len(seen) >= rt.limit:
                    return
        if rt.debug:
            rt.dump(page, self.key)
