"""
M3: 전처리 엔진 (preprocessor)
약관 PDF를 추출에 최적화된 형태로 가공

- PDF → 텍스트 추출 (pdfplumber 우선, pypdf 폴백)
- 약관 구조 파싱: 조/항/호 계층 인식
- 별표·부가자료 섹션 분리 및 인덱싱
- 테이블 추출: 별표 내 질병분류표 구조화
- 담보별 청킹
"""
import os
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import pypdf

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from config.settings import settings


class Preprocessor:
    """약관 PDF 전처리 엔진"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or settings.cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ── PDF 텍스트 추출 (PoC 이식 + 개선) ────────────────────────────────

    def extract_text(self, pdf_path: str, use_cache: bool = True, logger=print) -> str:
        """
        PDF 텍스트 추출.
        캐시 우선 → pdfplumber(테이블 우선) → pypdf 폴백.
        테이블이 있는 페이지는 마크다운 테이블만 사용하여 중복 방지.
        """
        filename = os.path.basename(pdf_path)
        cache_path = self.cache_dir / f"{filename}.md"

        # 1. 캐시 확인
        if use_cache and cache_path.exists():
            try:
                text = cache_path.read_text(encoding="utf-8")
                logger(f"  > [Cache] Loaded: {cache_path.name}")
                return text
            except Exception as e:
                logger(f"  > [Cache] Read failed: {e}")

        text_content = ""

        # 2. pdfplumber — 테이블이 있는 페이지는 마크다운만, 없으면 텍스트만
        if pdfplumber:
            try:
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages, 1):
                        tables = page.extract_tables()
                        if tables:
                            for table in tables:
                                cleaned = [
                                    [str(cell) if cell else "" for cell in row]
                                    for row in table
                                ]
                                if len(cleaned) > 1:
                                    try:
                                        df_table = pd.DataFrame(cleaned[1:], columns=cleaned[0])
                                        text_content += f"\n<!-- Page {page_num} Table -->\n"
                                        text_content += df_table.to_markdown(index=False) + "\n"
                                    except Exception:
                                        pass
                        else:
                            page_text = page.extract_text() or ""
                            if page_text.strip():
                                text_content += f"\n<!-- Page {page_num} -->\n{page_text}\n"
                logger(f"  > [Extraction] pdfplumber: {filename}")
            except Exception as e:
                logger(f"  > [Extraction] pdfplumber failed ({e}), falling back to pypdf...")
                text_content = ""

        # 3. pypdf 폴백
        if not text_content:
            try:
                with open(pdf_path, "rb") as f:
                    reader = pypdf.PdfReader(f)
                    parts = []
                    for page_num, page in enumerate(reader.pages, 1):
                        page_text = page.extract_text() or ""
                        if page_text.strip():
                            parts.append(f"\n<!-- Page {page_num} -->\n{page_text}")
                    text_content = "\n".join(parts)
                logger(f"  > [Extraction] pypdf: {filename}")
            except Exception as e:
                logger(f"  > [Extraction] pypdf failed for {pdf_path}: {e}")
                return ""

        # 4. 캐시 저장
        if text_content and use_cache:
            try:
                cache_path.write_text(text_content, encoding="utf-8")
                logger(f"  > [Cache] Saved: {cache_path.name}")
            except Exception as e:
                logger(f"  > [Cache] Save failed: {e}")

        return text_content

    # ── 약관 구조 파싱 ────────────────────────────────────────────────────

    def parse_structure(self, text: str) -> dict:
        """
        약관 텍스트에서 조/항/호 계층 구조를 인식합니다.
        Returns: {"articles": [{"number": "제1조", "title": "...", "content": "...", "items": [...]}]}
        """
        articles = []
        current_article = None

        # 조(Article) 패턴: 제N조, 제N조의N
        article_pattern = re.compile(r"^(제\d+조(?:의\d+)?)\s*[\(（](.+?)[\)）]", re.MULTILINE)
        # 항(Paragraph) 패턴: ① ② ③ ...
        paragraph_pattern = re.compile(r"^([①②③④⑤⑥⑦⑧⑨⑩])\s*(.+)", re.MULTILINE)
        # 호(Item) 패턴: 1. 2. 3. ...
        item_pattern = re.compile(r"^\s*(\d+)\.\s+(.+)", re.MULTILINE)

        for line in text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # 조 매칭
            art_match = article_pattern.match(line)
            if art_match:
                if current_article:
                    articles.append(current_article)
                current_article = {
                    "number": art_match.group(1),
                    "title": art_match.group(2),
                    "content": "",
                    "paragraphs": [],
                }
                continue

            if current_article:
                # 항 매칭
                para_match = paragraph_pattern.match(line)
                if para_match:
                    current_article["paragraphs"].append({
                        "marker": para_match.group(1),
                        "text": para_match.group(2),
                        "items": [],
                    })
                    continue

                # 호 매칭
                item_match = item_pattern.match(line)
                if item_match and current_article["paragraphs"]:
                    current_article["paragraphs"][-1]["items"].append({
                        "number": item_match.group(1),
                        "text": item_match.group(2),
                    })
                    continue

                current_article["content"] += line + "\n"

        if current_article:
            articles.append(current_article)

        return {"articles": articles}

    # ── 별표 섹션 분리 ────────────────────────────────────────────────────

    def extract_appendices(self, text: str) -> list[dict]:
        """
        별표(Appendix) 섹션을 분리하고 인덱싱합니다.
        Returns: [{"name": "별표[질병관련1]", "start_page": 45, "content": "..."}]
        """
        appendices = []
        # 별표 시작 패턴
        appendix_pattern = re.compile(
            r"(별표\s*[\[【\(]?\s*(?:질병관련|수술관련|상해관련|보장관련)?\s*\d*\s*[\]】\)]?)",
            re.IGNORECASE,
        )

        segments = appendix_pattern.split(text)
        for i in range(1, len(segments), 2):
            name = segments[i].strip()
            content = segments[i + 1] if i + 1 < len(segments) else ""

            # 페이지 번호 추출
            page_match = re.search(r"<!-- Page (\d+) -->", content)
            start_page = int(page_match.group(1)) if page_match else 0

            appendices.append({
                "name": name,
                "start_page": start_page,
                "content": content.strip()[:50000],  # 최대 50K 자
            })

        return appendices

    # ── 담보별 청킹 ──────────────────────────────────────────────────────

    def chunk_by_benefit(self, text: str, chunk_size: int = 8000) -> list[dict]:
        """
        약관 텍스트를 담보(특약) 단위로 청킹합니다.
        """
        chunks = []
        # 특약/담보 시작 패턴
        benefit_pattern = re.compile(
            r"((?:무배당\s+)?(?:\S+)\s*특약\s*약관|(?:제\d+관)\s+(?:\S+)\s+특약)",
            re.MULTILINE,
        )

        parts = benefit_pattern.split(text)
        for i in range(0, len(parts), 2):
            content = parts[i]
            title = parts[i - 1] if i > 0 else "메인 약관"

            # 크기 초과 시 분할
            if len(content) > chunk_size:
                for j in range(0, len(content), chunk_size):
                    sub = content[j:j + chunk_size]
                    chunks.append({
                        "title": f"{title} (part {j // chunk_size + 1})",
                        "content": sub,
                        "char_count": len(sub),
                    })
            elif content.strip():
                chunks.append({
                    "title": title,
                    "content": content.strip(),
                    "char_count": len(content.strip()),
                })

        return chunks

    # ── 통합 전처리 ──────────────────────────────────────────────────────

    def preprocess(self, pdf_path: str, logger=print) -> dict:
        """
        PDF → 전처리 결과 (텍스트 + 구조 + 별표 + 청크)
        """
        logger(f"[M3] 전처리 시작: {os.path.basename(pdf_path)}")

        text = self.extract_text(pdf_path, logger=logger)
        if not text:
            return {"error": "PDF 텍스트 추출 실패"}

        structure = self.parse_structure(text)
        appendices = self.extract_appendices(text)
        chunks = self.chunk_by_benefit(text)

        logger(f"  > 조항 수: {len(structure['articles'])}")
        logger(f"  > 별표 수: {len(appendices)}")
        logger(f"  > 청크 수: {len(chunks)}")

        return {
            "raw_text": text,
            "structure": structure,
            "appendices": appendices,
            "chunks": chunks,
            "metadata": {
                "filename": os.path.basename(pdf_path),
                "total_chars": len(text),
                "article_count": len(structure["articles"]),
                "appendix_count": len(appendices),
                "chunk_count": len(chunks),
            },
        }
