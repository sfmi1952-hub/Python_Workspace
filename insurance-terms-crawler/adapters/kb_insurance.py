# -*- coding: utf-8 -*-
"""KB손해보험 — 공시실 상품목록 CG802030001.ec (detail() AJAX 라우팅).

약관 PDF는 파일스토어 정적 GET:
  - 장기/인보험: /extrnl/clause/ltins/{코드}.pdf
  - 일반/물보험: /images/clause/gnins/{파일명}.pdf
  - 다이렉트(DTC): direct.kbinsure.co.kr/dwlddoc/{...}.pdf
목록→상세(detail) 클릭으로 약관 a[href] 를 렌더한 뒤 그 URL을 수집.
"""
import config as cfg
from adapters.base import BaseAdapter
from models import TermRecord


class KBInsuranceAdapter(BaseAdapter):
    key = "kb_insurance"
    name = "KB손해보험"
    needs_browser = True
    base_url = "https://www.kbinsure.co.kr"
    LIST_URL = "https://www.kbinsure.co.kr/CG802030001.ec"
    TOKENS = ["extrnl/clause", "images/clause", "/dwlddoc/", "direct.kbinsure.co.kr"]

    def discover(self, rt):
        page, seen = rt.page, set()
        try:
            page.goto(self.LIST_URL, wait_until="networkidle", timeout=cfg.NAV_TIMEOUT_MS)
        except Exception as e:
            rt.log(f"  goto 실패: {e}")
            return
        rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
        # 1차: 목록에 직접 노출된 약관 링크
        yield from self._emit(rt, page, seen, self.LIST_URL)
        # 2차: detail() 행 순회 → 상세에서 약관 링크
        try:
            handles = page.query_selector_all("[onclick*='detail(']")
        except Exception:
            handles = []
        cap = rt.limit or 10 ** 9
        for h in handles:
            if len(seen) >= cap:
                break
            try:
                h.click(timeout=2000)
                rt.sleep(1.0)
            except Exception:
                continue
            yield from self._emit(rt, page, seen, self.LIST_URL)
            try:
                page.go_back(timeout=3000)
                rt.sleep(0.6)
            except Exception:
                pass
        if rt.debug:
            rt.dump(page, self.key)

    def _emit(self, rt, page, seen, referer):
        for it in self.terms_links(page, self.TOKENS, self.base_url):
            if it["url"] in seen:
                continue
            seen.add(it["url"])
            yield TermRecord(
                company=self.key, company_name=self.name,
                product_name=it["product"], terms_title=it["title"] or "약관",
                pdf_url=it["url"], referer=referer, source="official",
            )
