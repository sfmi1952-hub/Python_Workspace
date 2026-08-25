# -*- coding: utf-8 -*-
"""공용 PDF 다운로더 — requests 단순 GET + 버전 dedup + 호스트별 rate-limit + 약관 재검증."""
import time
from pathlib import Path
from urllib.parse import urlparse

import config as cfg
from utils import sanitize_filename, cd_filename, is_terms_doc, short_hash


class Downloader:
    def __init__(self, session, index, output_dir: Path, delay: float = cfg.REQUEST_DELAY_SEC,
                 enforce_terms: bool = True, log=print):
        self.s = session
        self.index = index
        self.out = Path(output_dir)
        self.delay = delay
        self.enforce_terms = enforce_terms
        self.log = log
        self._last = {}  # host -> ts

    def _throttle(self, url: str):
        host = urlparse(url).netloc
        now = time.time()
        wait = self.delay - (now - self._last.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        self._last[host] = time.time()

    def _dest(self, rec, filename: str) -> Path:
        base = sanitize_filename(filename or rec.product_name or rec.product_code or "terms")
        if not base.lower().endswith(".pdf"):
            base += ".pdf"
        stem = base[:-4]
        tag = rec.revision_date or ""
        h = short_hash(rec.pdf_url, 6)
        name = f"{stem}__{tag}__{h}.pdf" if tag else f"{stem}__{h}.pdf"
        d = self.out / rec.company
        d.mkdir(parents=True, exist_ok=True)
        return d / sanitize_filename(name, 180)

    def download(self, rec) -> str:
        """성공 시 저장 경로, 스킵/실패 시 빈 문자열."""
        key = rec.key()
        if self.index.has(key):
            return ""  # 이미 받은 버전
        if not rec.pdf_url:
            return ""
        self._throttle(rec.pdf_url)
        headers = {}
        if rec.referer:
            headers["Referer"] = rec.referer
        try:
            r = self.s.get(rec.pdf_url, headers=headers, timeout=60, allow_redirects=True)
        except Exception as e:
            self.log(f"    [download error] {rec.pdf_url} :: {e}")
            self.index.upsert(rec, "", 0, "error")
            return ""
        if r.status_code != 200 or not r.content:
            self.log(f"    [http {r.status_code}] {rec.pdf_url}")
            self.index.upsert(rec, "", 0, f"http_{r.status_code}")
            return ""

        ctype = (r.headers.get("Content-Type") or "").lower()
        fname = cd_filename(r.headers.get("Content-Disposition")) or Path(urlparse(rec.pdf_url).path).name

        # PDF 여부 확인(헤더 또는 매직넘버)
        is_pdf = ("pdf" in ctype) or r.content[:5] == b"%PDF-" or fname.lower().endswith(".pdf")
        if not is_pdf:
            self.log(f"    [not-pdf {ctype}] {rec.pdf_url}")
            self.index.upsert(rec, "", len(r.content), "not_pdf")
            return ""

        # 약관 재검증(파일명/약관명 기준). 범위=약관 전용일 때만.
        if self.enforce_terms and not is_terms_doc(fname, rec.terms_title, rec.doc_type):
            self.index.upsert(rec, "", len(r.content), "skip_not_terms")
            return ""

        if len(r.content) > cfg.MAX_DOWNLOAD_MB * 1024 * 1024:
            self.index.upsert(rec, "", len(r.content), "too_large")
            return ""

        dest = self._dest(rec, fname)
        dest.write_bytes(r.content)
        self.index.upsert(rec, str(dest), len(r.content), "ok")
        self.log(f"    ✓ {dest.name}  ({len(r.content)//1024} KB)")
        return str(dest)
