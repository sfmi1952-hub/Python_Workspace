# -*- coding: utf-8 -*-
"""어댑터 공통 베이스 + 런타임 컨텍스트 + 렌더후 PDF 링크 추출 헬퍼."""
import time
from abc import ABC, abstractmethod
from pathlib import Path

import config as cfg
from utils import SWEEP_JS, abs_url, is_terms_doc


class Runtime:
    """어댑터에 주입되는 실행 컨텍스트."""
    def __init__(self, page, session, debug=False, limit=0, log=print):
        self.page = page          # Playwright page (HTTP-only 어댑터는 None)
        self.session = session    # requests.Session
        self.debug = debug
        self.limit = limit        # 회사별 최대 수집 건수(0=무제한, 디버그용)
        self.log = log

    def sleep(self, sec):
        time.sleep(sec)

    def dump(self, page, key):
        """디버그: 렌더된 HTML과 후보 링크를 logs/에 저장(셀렉터 튜닝용)."""
        try:
            cfg.LOG_DIR.mkdir(parents=True, exist_ok=True)
            (cfg.LOG_DIR / f"{key}_rendered.html").write_text(page.content(), encoding="utf-8")
            self.log(f"    [debug] dumped logs/{key}_rendered.html")
        except Exception as e:
            self.log(f"    [debug dump failed] {e}")


class BaseAdapter(ABC):
    key = ""
    name = ""
    needs_browser = True
    base_url = ""

    @abstractmethod
    def discover(self, rt: "Runtime"):
        """약관 TermRecord 들을 yield."""
        raise NotImplementedError

    # ----- 공통 헬퍼 -----
    def sweep(self, page, tokens):
        """렌더된 페이지에서 token(경로조각)이 든 링크들을 컬럼헤더/상품명과 함께 추출."""
        try:
            return page.evaluate(SWEEP_JS, tokens) or []
        except Exception:
            return []

    def terms_links(self, page, tokens, base_url):
        """약관 컬럼/링크만 필터링한 (url, 상품명, 약관명) 리스트 반환(중복 url 제거)."""
        seen, out = set(), []
        for it in self.sweep(page, tokens):
            href = it.get("href") or ""
            # href 가 token을 가진 경우만 URL로 직접 사용(onclick-only는 어댑터가 별도 처리)
            if not any(t in href for t in tokens):
                continue
            url = abs_url(href, base_url)
            if not url or url in seen:
                continue
            col = it.get("colHeader") or ""
            txt = it.get("text") or ""
            aria = it.get("aria") or ""
            row = it.get("rowName") or ""
            # 약관 판별: 컬럼헤더/링크텍스트/aria 중 하나라도 '약관'이고 제외어 없으면 채택.
            # (헤더가 비어있고 판별불가면 보수적으로 채택하되 doc_type 표시)
            label = " ".join([col, txt, aria])
            if label.strip() and not is_terms_doc(label):
                continue
            seen.add(url)
            out.append({"url": url, "product": row or txt, "title": (txt or col or row).strip()})
        return out
