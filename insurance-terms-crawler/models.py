# -*- coding: utf-8 -*-
"""수집 레코드(TermRecord) + 버전 인덱스(SQLite)."""
import sqlite3
from dataclasses import dataclass, asdict
from datetime import datetime

from utils import short_hash


@dataclass
class TermRecord:
    company: str                 # 'samsung_fire'
    company_name: str            # '삼성화재'
    product_name: str            # 상품명
    terms_title: str = ""        # 약관명(컬럼/링크 텍스트)
    product_code: str = ""       # 상품코드(있으면)
    revision_date: str = ""      # 개정/시행일 또는 판매시기(YYYYMMDD 등)
    pdf_url: str = ""            # 최종 PDF 직접 URL
    referer: str = ""            # 다운로드 시 필요한 Referer
    source: str = "official"     # official | knia(협회) | direct
    doc_type: str = "약관"
    note: str = ""

    def key(self) -> str:
        # 동일 PDF URL = 동일 버전. URL이 없으면 회사+상품+개정일로 키.
        basis = self.pdf_url or f"{self.company}|{self.product_name}|{self.revision_date}"
        return short_hash(basis, 16)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
  key TEXT PRIMARY KEY,
  company TEXT, company_name TEXT,
  product_name TEXT, terms_title TEXT, product_code TEXT,
  revision_date TEXT, pdf_url TEXT, doc_type TEXT, source TEXT,
  file_path TEXT, bytes INTEGER, status TEXT,
  downloaded_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_company ON records(company);
"""


class Index:
    def __init__(self, db_path):
        self.con = sqlite3.connect(str(db_path))
        self.con.executescript(_SCHEMA)
        self.con.commit()

    def has(self, key: str) -> bool:
        cur = self.con.execute("SELECT 1 FROM records WHERE key=? AND status='ok'", (key,))
        return cur.fetchone() is not None

    def upsert(self, rec: TermRecord, file_path: str, nbytes: int, status: str):
        self.con.execute(
            """INSERT INTO records
               (key, company, company_name, product_name, terms_title, product_code,
                revision_date, pdf_url, doc_type, source, file_path, bytes, status, downloaded_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(key) DO UPDATE SET
                 file_path=excluded.file_path, bytes=excluded.bytes,
                 status=excluded.status, downloaded_at=excluded.downloaded_at""",
            (rec.key(), rec.company, rec.company_name, rec.product_name, rec.terms_title,
             rec.product_code, rec.revision_date, rec.pdf_url, rec.doc_type, rec.source,
             file_path, nbytes, status, datetime.now().isoformat(timespec="seconds")),
        )
        self.con.commit()

    def stats(self):
        cur = self.con.execute(
            "SELECT company_name, COUNT(*) FROM records WHERE status='ok' GROUP BY company")
        return cur.fetchall()

    def rows(self, company=None):
        if company:
            cur = self.con.execute("SELECT * FROM records WHERE company=?", (company,))
        else:
            cur = self.con.execute("SELECT * FROM records")
        cols = [c[0] for c in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    def close(self):
        self.con.close()
