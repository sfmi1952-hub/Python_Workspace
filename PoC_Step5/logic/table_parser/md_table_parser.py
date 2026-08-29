import re
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class TableCell:
    text: str
    row_span: int = 1
    col_span: int = 1


@dataclass
class ParsedTable:
    headers: List[str]
    rows: List[List[TableCell]]
    source_page: Optional[int] = None
    caption: Optional[str] = None
    raw_markdown: str = ""


class MarkdownTableParser:
    """Parse markdown pipe-delimited tables into structured objects."""

    def parse_all_tables(self, markdown_text: str) -> List[ParsedTable]:
        """Find all markdown tables in text and parse them."""
        tables: List[ParsedTable] = []
        lines = markdown_text.split("\n")
        i = 0

        while i < len(lines):
            # Look for table start: line with pipes
            if self._is_table_line(lines[i]):
                table_lines, caption = self._collect_table_lines(lines, i)
                if len(table_lines) >= 2:  # At least header + separator
                    parsed = self._parse_single_table(table_lines, caption)
                    if parsed:
                        tables.append(parsed)
                i += len(table_lines)
            else:
                i += 1

        # Post-processing
        tables = self._fill_merged_cells(tables)
        tables = self._reconstruct_cross_page_tables(tables)

        return tables

    def _is_table_line(self, line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2

    def _is_separator_line(self, line: str) -> bool:
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            return False
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        return all(re.match(r"^[-:]+$", c) for c in cells if c)

    def _collect_table_lines(self, lines: List[str], start: int):
        """Collect consecutive table lines. Also look for caption comment above."""
        caption = None
        # Check for HTML comment caption above
        if start > 0:
            prev = lines[start - 1].strip()
            match = re.match(r"<!--\s*(.+?)\s*-->", prev)
            if match:
                caption = match.group(1)

        table_lines: List[str] = []
        i = start
        while i < len(lines) and self._is_table_line(lines[i]):
            table_lines.append(lines[i])
            i += 1
        return table_lines, caption

    def _parse_single_table(self, table_lines: List[str], caption: Optional[str]) -> Optional[ParsedTable]:
        """Parse a list of markdown table lines into a ParsedTable."""
        if len(table_lines) < 2:
            return None

        raw_md = "\n".join(table_lines)

        # Find separator line index
        sep_idx = None
        for i, line in enumerate(table_lines):
            if self._is_separator_line(line):
                sep_idx = i
                break

        if sep_idx is None:
            # No separator found - treat first row as header
            headers = self._parse_row(table_lines[0])
            data_lines = table_lines[1:]
        else:
            # Headers are all lines before separator (usually just one)
            header_parts: List[str] = []
            for i in range(sep_idx):
                header_parts.append(table_lines[i])
            headers = self._parse_row(header_parts[-1]) if header_parts else []
            data_lines = table_lines[sep_idx + 1:]

        rows: List[List[TableCell]] = []
        for line in data_lines:
            cells_text = self._parse_row(line)
            row = [TableCell(text=t) for t in cells_text]
            rows.append(row)

        return ParsedTable(
            headers=headers,
            rows=rows,
            caption=caption,
            raw_markdown=raw_md,
        )

    def _parse_row(self, line: str) -> List[str]:
        """Parse a single markdown table row into cell texts."""
        stripped = line.strip()
        if stripped.startswith("|"):
            stripped = stripped[1:]
        if stripped.endswith("|"):
            stripped = stripped[:-1]
        cells = [c.strip() for c in stripped.split("|")]
        return cells

    def _fill_merged_cells(self, tables: List[ParsedTable]) -> List[ParsedTable]:
        """Fill empty cells by inheriting from the cell above (vertical merge heuristic)."""
        for table in tables:
            if not table.rows:
                continue
            for row_idx in range(1, len(table.rows)):
                for col_idx in range(min(len(table.rows[row_idx]), len(table.rows[row_idx - 1]))):
                    cell = table.rows[row_idx][col_idx]
                    if cell.text.strip() == "":
                        above = table.rows[row_idx - 1][col_idx]
                        cell.text = above.text
                        cell.row_span = 0  # Mark as inherited
        return tables

    def _reconstruct_cross_page_tables(self, tables: List[ParsedTable]) -> List[ParsedTable]:
        """Merge tables that appear to be continuations across pages."""
        if len(tables) <= 1:
            return tables

        merged: List[ParsedTable] = [tables[0]]

        for i in range(1, len(tables)):
            current = tables[i]
            prev = merged[-1]

            if self._is_continuation(prev, current):
                # Merge current rows into previous table
                prev.rows.extend(current.rows)
                prev.raw_markdown += "\n" + current.raw_markdown
            else:
                merged.append(current)

        return merged

    def _is_continuation(self, prev: ParsedTable, current: ParsedTable) -> bool:
        """Heuristic: a table is a continuation if it has no real headers
        and column count matches the previous table."""
        if not prev.headers or not current.headers:
            return False

        # Same number of columns
        if len(prev.headers) != len(current.headers):
            return False

        # Check if current "headers" look like data (not header-like)
        # Headers typically contain Korean text descriptors
        current_header_text = " ".join(current.headers)
        prev_header_text = " ".join(prev.headers)

        # If headers are identical, it's likely a continuation with repeated header
        if current_header_text == prev_header_text:
            return True

        return False

    def get_table_context(self, markdown_text: str, table: ParsedTable, chars: int = 300) -> tuple:
        """Get text context before and after a table for LLM prompt."""
        idx = markdown_text.find(table.raw_markdown)
        if idx == -1:
            return ("", "")

        before = markdown_text[max(0, idx - chars):idx].strip()
        after_start = idx + len(table.raw_markdown)
        after = markdown_text[after_start:after_start + chars].strip()

        return (before, after)
