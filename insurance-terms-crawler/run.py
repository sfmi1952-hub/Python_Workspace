# -*- coding: utf-8 -*-
"""6개 보험사 약관(보험약관) 크롤러 — 오케스트레이터.

전략: 목록/키 수집(Playwright 헤드리스 or 협회 HTTP) → 공용 단순 GET 다운로드.
버전: pdf_url 단위로 dedup → 같은 상품의 판매시기/개정본을 각각 보존(덮어쓰기 없음).
범위: 보험약관 전용(사업방법서/상품요약서/설명서는 다운로더가 파일명으로 제외).

예)
  python run.py --companies samsung_life            # 가장 가벼운 검증(브라우저 불필요)
  python run.py --companies samsung_life --limit 5  # 5건만 스모크 테스트
  python run.py --companies all                     # 6개사 전체
  python run.py --companies db_insurance --debug --headful
"""
import argparse
import csv
import importlib
import sys
import traceback
from datetime import datetime

import requests
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except Exception:  # pragma: no cover
    Retry = None

import config as cfg
from models import Index
from downloader import Downloader


def log(msg=""):
    print(msg, flush=True)


def build_session():
    s = requests.Session()
    s.headers.update({"User-Agent": cfg.USER_AGENT,
                      "Accept": "*/*",
                      "Accept-Language": "ko-KR,ko;q=0.9"})
    if Retry:
        retry = Retry(total=3, backoff_factor=0.6,
                      status_forcelist=(429, 500, 502, 503, 504),
                      allowed_methods=("GET", "POST"))
        ad = HTTPAdapter(max_retries=retry, pool_maxsize=8)
        s.mount("https://", ad)
        s.mount("http://", ad)
    return s


def load_adapter(key):
    meta = cfg.COMPANIES[key]
    mod = importlib.import_module(meta["module"])
    return getattr(mod, meta["cls"])()


def resolve_companies(arg):
    if not arg or arg == "all":
        return cfg.DEFAULT_ORDER
    keys = [k.strip() for k in arg.split(",") if k.strip()]
    bad = [k for k in keys if k not in cfg.COMPANIES]
    if bad:
        log(f"알 수 없는 회사키: {bad}\n사용가능: {list(cfg.COMPANIES)}")
        sys.exit(2)
    return keys


def write_manifest(index):
    cfg.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    path = cfg.OUTPUT_DIR / "manifest.csv"
    rows = index.rows()
    if not rows:
        return path
    cols = ["company", "company_name", "product_name", "terms_title", "product_code",
            "revision_date", "doc_type", "source", "pdf_url", "file_path", "bytes", "status",
            "downloaded_at"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


def run_adapter(adapter, rt, downloader):
    got = 0
    try:
        for rec in adapter.discover(rt):
            saved = downloader.download(rec)
            if saved:
                got += 1
    except KeyboardInterrupt:
        raise
    except Exception:
        log(f"  [어댑터 예외] {adapter.key}\n{traceback.format_exc()}")
    return got


def main():
    ap = argparse.ArgumentParser(description="보험사 약관 크롤러")
    ap.add_argument("--companies", default="all",
                    help="콤마구분 회사키 또는 all (예: samsung_life,db_insurance)")
    ap.add_argument("--limit", type=int, default=0, help="회사별 최대 다운로드 건수(0=무제한)")
    ap.add_argument("--headful", action="store_true", help="브라우저 창 표시(디버그)")
    ap.add_argument("--debug", action="store_true", help="렌더 HTML 덤프(logs/)")
    ap.add_argument("--list", action="store_true", help="회사 목록만 출력")
    args = ap.parse_args()

    if args.list:
        for k in cfg.DEFAULT_ORDER:
            m = cfg.COMPANIES[k]
            log(f"  {k:16} {m['name']} ({m['category']})")
        return

    keys = resolve_companies(args.companies)
    adapters = [load_adapter(k) for k in keys]
    need_browser = any(a.needs_browser for a in adapters)

    index = Index(cfg.DB_PATH)
    session = build_session()
    downloader = Downloader(session, index, cfg.OUTPUT_DIR, log=log)

    log(f"== 약관 크롤러 시작 {datetime.now():%Y-%m-%d %H:%M:%S} ==")
    log(f"   대상: {', '.join(keys)}  | 브라우저: {'필요' if need_browser else '불필요'}")

    browser = ctx = pw = None
    try:
        if need_browser:
            from playwright.sync_api import sync_playwright
            pw = sync_playwright().start()
            browser = pw.chromium.launch(headless=not args.headful)
            ctx = browser.new_context(user_agent=cfg.USER_AGENT, accept_downloads=True,
                                      locale="ko-KR")
            ctx.set_default_timeout(cfg.NAV_TIMEOUT_MS)

        from adapters.base import Runtime
        totals = {}
        for a in adapters:
            log(f"\n[{a.name}] ({a.key}) 수집 시작…")
            page = ctx.new_page() if (a.needs_browser and ctx) else None
            rt = Runtime(page=page, session=session, debug=args.debug,
                         limit=args.limit, log=log)
            totals[a.key] = run_adapter(a, rt, downloader)
            if page:
                try:
                    page.close()
                except Exception:
                    pass
            log(f"[{a.name}] 신규 다운로드: {totals[a.key]} 건")
    except KeyboardInterrupt:
        log("\n중단됨(KeyboardInterrupt).")
    finally:
        if ctx:
            ctx.close()
        if browser:
            browser.close()
        if pw:
            pw.stop()

    log("\n== 누적 인덱스(상태=ok) ==")
    for name, cnt in index.stats():
        log(f"   {name}: {cnt} 건")
    mpath = write_manifest(index)
    log(f"\n매니페스트: {mpath}")
    log(f"저장 위치 : {cfg.OUTPUT_DIR}")
    index.close()


if __name__ == "__main__":
    main()
