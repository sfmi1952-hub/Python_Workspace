# -*- coding: utf-8 -*-
"""메리츠화재 — 공시실 product-list.do (SPA + 웹방화벽).

정상 브라우저(UA)로 접근해야 WAF를 통과. 약관 링크는 AJAX/onclick 으로 렌더.
공식 경로가 막히면 손해보험협회(KNIA) 소비자포털을 폴백으로 사용.
"""
import config as cfg
from adapters.base import BaseAdapter
from models import TermRecord


class MeritzFireAdapter(BaseAdapter):
    key = "meritz_fire"
    name = "메리츠화재"
    needs_browser = True
    base_url = "https://www.meritzfire.com"
    LIST_URL = "https://www.meritzfire.com/disclosure/product-announcement/product-list.do?vMode=PC"
    TOKENS = [".pdf", "cmdown.meritzfire.com"]

    def discover(self, rt):
        page, seen, count = rt.page, set(), 0
        try:
            page.goto(self.LIST_URL, wait_until="networkidle", timeout=cfg.NAV_TIMEOUT_MS)
            for t in ("조회", "검색", "전체"):
                try:
                    page.get_by_text(t, exact=False).first.click(timeout=1500)
                    rt.sleep(1.0)
                except Exception:
                    pass
            rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
            if rt.debug:
                rt.dump(page, self.key)
            for it in self.terms_links(page, [".pdf"], self.base_url):
                if it["url"] in seen:
                    continue
                seen.add(it["url"])
                count += 1
                yield TermRecord(
                    company=self.key, company_name=self.name,
                    product_name=it["product"], terms_title=it["title"],
                    pdf_url=it["url"], referer=self.LIST_URL, source="official",
                )
                if rt.limit and count >= rt.limit:
                    return
        except Exception as e:
            rt.log(f"  메리츠 공식 공시실 접근 실패(WAF 가능성): {e}")

        if count == 0:
            # ── KNIA 폴백 골격 ──────────────────────────────────────────────
            # 손보협회 소비자포털 회사별공시(메리츠화재) → kpub.knia.or.kr/file/download/{id}.do (단순 GET)
            # 실제 회사코드/목록 AJAX 파라미터는 라이브 DevTools 1회 캡처로 확정해야 함(튜닝 지점).
            rt.log("  → 공식 경로 0건. KNIA 소비자포털 폴백 필요(consumer.knia.or.kr/disclosure → 메리츠화재).")
            yield from self._knia_fallback(rt)

    def _knia_fallback(self, rt):
        page = rt.page
        url = "https://consumer.knia.or.kr/disclosure"
        try:
            page.goto(url, wait_until="networkidle", timeout=cfg.NAV_TIMEOUT_MS)
            rt.sleep(cfg.SEARCH_WAIT_MS / 1000)
            if rt.debug:
                rt.dump(page, self.key + "_knia")
            for it in self.terms_links(page, ["/file/download/", ".pdf"], "https://kpub.knia.or.kr"):
                yield TermRecord(
                    company=self.key, company_name=self.name,
                    product_name=it["product"], terms_title=it["title"],
                    pdf_url=it["url"], referer=url, source="knia",
                )
        except Exception as e:
            rt.log(f"  KNIA 폴백도 실패: {e}")
