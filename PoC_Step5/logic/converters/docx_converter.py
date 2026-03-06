"""Method 1: Word(.docx) → Markdown 변환기.

mammoth 대신 python-docx를 사용하여 문서 순서를 유지하면서
표(table)를 마크다운 테이블 형식으로 정확히 변환합니다.

문서 body의 자식 요소(paragraph, table)를 순서대로 순회하여
단락은 텍스트로, 표는 | col1 | col2 | 형태로 변환합니다.
"""

import re
import time
from pathlib import Path
from typing import List, Optional

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.oxml.ns import qn

from .base_converter import BaseConverter, ConversionResult


class DocxConverter(BaseConverter):
    """Method 1: Word(.docx) -> markdown via python-docx (table structure preserved)."""

    def name(self) -> str:
        return "baseline_python_docx"

    def convert(self, file_path: str) -> ConversionResult:
        start = time.time()
        errors: List[str] = []
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"DOCX file not found: {file_path}")

        try:
            doc = Document(str(path))
            markdown = self._doc_to_markdown(doc)
        except Exception as e:
            errors.append(f"python-docx conversion failed: {e}")
            markdown = ""

        elapsed = time.time() - start
        return ConversionResult(
            markdown_text=markdown,
            page_count=self._estimate_pages(path),
            conversion_time_sec=elapsed,
            source_path=str(path),
            method_name=self.name(),
            errors=errors,
        )

    # ── Document → Markdown (순서 유지) ──────────────────────

    def _doc_to_markdown(self, doc: Document) -> str:
        """문서 body 요소를 순서대로 순회하며 마크다운으로 변환.

        doc.element.body 하위에는 <w:p>(단락)와 <w:tbl>(표)가 섞여 있다.
        이를 순서대로 처리하여 문서 구조를 보존한다.
        """
        parts: List[str] = []
        table_idx = 0

        for child in doc.element.body:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag

            if tag == "p":
                para = Paragraph(child, doc)
                md_line = self._paragraph_to_markdown(para)
                if md_line is not None:
                    parts.append(md_line)

            elif tag == "tbl":
                table = Table(child, doc)
                table_idx += 1
                md_table = self._table_to_markdown(table, table_idx)
                if md_table:
                    parts.append(f"\n{md_table}\n")

        return "\n".join(parts)

    # ── 단락 변환 ────────────────────────────────────────────

    def _paragraph_to_markdown(self, para: Paragraph) -> Optional[str]:
        """단락을 마크다운 텍스트로 변환."""
        text = para.text.strip()
        if not text:
            return ""

        # 스타일 기반 헤딩 처리
        style_name = (para.style.name or "").lower() if para.style else ""

        if "heading 1" in style_name:
            return f"# {text}"
        elif "heading 2" in style_name:
            return f"## {text}"
        elif "heading 3" in style_name:
            return f"### {text}"
        elif "heading 4" in style_name:
            return f"#### {text}"

        # Bold 체크 (전체 run이 bold인 경우)
        all_bold = all(
            run.bold for run in para.runs if run.text.strip()
        ) if para.runs else False

        if all_bold and len(text) < 200:
            return f"**{text}**"

        return text

    # ── 표 변환 ──────────────────────────────────────────────

    def _table_to_markdown(self, table: Table, table_idx: int) -> str:
        """표를 마크다운 테이블로 변환 (병합셀 처리 포함).

        1. 모든 셀을 2D 배열로 읽기
        2. 세로 병합(vMerge) 처리: 이전 행의 값 상속
        3. 가로 병합(gridSpan) 처리: 중복 셀 제거
        4. 마크다운 테이블 포맷으로 출력
        """
        try:
            num_rows = len(table.rows)
            num_cols = len(table.columns)

            if num_rows == 0 or num_cols == 0:
                return ""

            # Step 1: 원시 셀 텍스트 읽기 + 병합 처리
            grid = self._build_cell_grid(table, num_rows, num_cols)

            if not grid:
                return ""

            # Step 2: 가로 병합 중복 제거
            cleaned_grid = self._clean_horizontal_merges(table, grid, num_rows, num_cols)

            # Step 3: 컬럼 수 정규화
            max_cols = max(len(row) for row in cleaned_grid) if cleaned_grid else 0
            if max_cols == 0:
                return ""

            for row in cleaned_grid:
                while len(row) < max_cols:
                    row.append("")

            # Step 4: 마크다운 테이블 생성
            lines: List[str] = []
            lines.append(f"<!-- Table {table_idx} -->")

            # 헤더 행
            header = cleaned_grid[0]
            lines.append("| " + " | ".join(self._escape_pipe(c) for c in header) + " |")
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")

            # 데이터 행
            for row in cleaned_grid[1:]:
                lines.append("| " + " | ".join(self._escape_pipe(c) for c in row) + " |")

            return "\n".join(lines)

        except Exception as e:
            return f"<!-- Table {table_idx}: extraction error: {e} -->"

    def _build_cell_grid(
        self, table: Table, num_rows: int, num_cols: int
    ) -> List[List[str]]:
        """표의 모든 셀을 2D 그리드로 변환, 세로 병합 처리 포함.

        python-docx의 table.cell(row, col)은 병합된 셀의 경우
        동일한 Cell 객체를 반환하므로, XML을 직접 파싱하여
        vMerge(세로병합)를 정확히 처리한다.
        """
        grid: List[List[str]] = []

        for row_idx in range(num_rows):
            row_cells: List[str] = []
            row_el = table.rows[row_idx]._tr

            # 해당 행의 <w:tc> 요소들을 직접 순회
            tc_elements = row_el.findall(qn("w:tc"))

            col_pos = 0
            for tc in tc_elements:
                cell_text = self._get_tc_text(tc).strip()
                cell_text = cell_text.replace("\n", " / ").replace("\r", "")

                # gridSpan 확인 (가로 병합)
                tc_pr = tc.find(qn("w:tcPr"))
                grid_span = 1
                if tc_pr is not None:
                    gs = tc_pr.find(qn("w:gridSpan"))
                    if gs is not None:
                        grid_span = int(gs.get(qn("w:val"), "1"))

                # vMerge 확인 (세로 병합)
                is_vmerge_continue = False
                if tc_pr is not None:
                    vm = tc_pr.find(qn("w:vMerge"))
                    if vm is not None:
                        val = vm.get(qn("w:val"), "")
                        if val != "restart":
                            # 병합 계속 → 위 행의 값 상속
                            is_vmerge_continue = True

                if is_vmerge_continue and row_idx > 0 and col_pos < len(grid[row_idx - 1]):
                    cell_text = grid[row_idx - 1][col_pos]

                # gridSpan만큼 셀 추가
                row_cells.append(cell_text)
                for _ in range(1, grid_span):
                    row_cells.append(cell_text)  # 병합된 열에 같은 값

                col_pos += grid_span

            grid.append(row_cells)

        return grid

    def _clean_horizontal_merges(
        self,
        table: Table,
        grid: List[List[str]],
        num_rows: int,
        num_cols: int,
    ) -> List[List[str]]:
        """가로 병합으로 인한 중복 셀을 처리.

        gridSpan으로 병합된 셀은 이미 같은 텍스트로 채워져 있으므로,
        실제 표의 논리적 컬럼 구조를 유지하기 위해
        표의 XML에서 실제 tc 개수를 기반으로 정리한다.
        """
        cleaned: List[List[str]] = []

        for row_idx in range(num_rows):
            row_el = table.rows[row_idx]._tr
            tc_elements = row_el.findall(qn("w:tc"))
            row_cells: List[str] = []

            for tc in tc_elements:
                cell_text = self._get_tc_text(tc).strip()
                cell_text = cell_text.replace("\n", " / ").replace("\r", "")

                # vMerge 계속인 경우 위 행에서 상속
                tc_pr = tc.find(qn("w:tcPr"))
                is_vmerge_continue = False
                if tc_pr is not None:
                    vm = tc_pr.find(qn("w:vMerge"))
                    if vm is not None:
                        val = vm.get(qn("w:val"), "")
                        if val != "restart":
                            is_vmerge_continue = True

                if is_vmerge_continue and row_idx > 0:
                    # 위 행의 같은 위치에서 상속
                    col_pos = len(row_cells)
                    if col_pos < len(cleaned[row_idx - 1]):
                        cell_text = cleaned[row_idx - 1][col_pos]

                row_cells.append(cell_text)

            cleaned.append(row_cells)

        return cleaned

    def _get_tc_text(self, tc) -> str:
        """<w:tc> 요소에서 텍스트를 추출."""
        texts = []
        for p in tc.findall(qn("w:p")):
            p_texts = []
            for r in p.findall(qn("w:r")):
                for t in r.findall(qn("w:t")):
                    if t.text:
                        p_texts.append(t.text)
            if p_texts:
                texts.append("".join(p_texts))
        return "\n".join(texts)

    def _escape_pipe(self, text: str) -> str:
        """마크다운 테이블 내 파이프(|) 문자 이스케이프."""
        return text.replace("|", "\\|")

    def _estimate_pages(self, path: Path) -> int:
        """파일 크기 기반 대략적 페이지 수 추정."""
        size_kb = path.stat().st_size / 1024
        return max(1, int(size_kb / 50))
