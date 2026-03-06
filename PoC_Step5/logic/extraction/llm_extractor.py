import logging
import math
from dataclasses import dataclass, asdict
from typing import List, Callable, Dict

import pandas as pd

from ..openai_core import OpenAICore
from .prompts import SYSTEM_PROMPT, BATCH_EXTRACTION_PROMPT, FALLBACK_BATCH_PROMPT

logger = logging.getLogger(__name__)

ALL_COLUMNS = [
    "상품코드", "담보PMID", "담보명", "담보구분",
    "보기", "보기구분", "납기", "납기구분",
    "시작연령", "시작연령유형", "끝연령", "끝연령유형",
]

# Fields that come from the ground truth (input)
INPUT_FIELDS = ["상품코드", "담보PMID", "담보명"]

# Fields that LLM must fill
FILL_FIELDS = [
    "담보구분", "보기", "보기구분", "납기", "납기구분",
    "시작연령", "시작연령유형", "끝연령", "끝연령유형",
]

BATCH_SIZE = 100


@dataclass
class ExtractionRow:
    상품코드: str = ""
    담보PMID: str = ""
    담보명: str = ""
    담보구분: str = "0"
    보기: str = ""
    보기구분: str = ""
    납기: str = ""
    납기구분: str = ""
    시작연령: str = ""
    시작연령유형: str = "1"
    끝연령: str = ""
    끝연령유형: str = "1"


class LLMExtractor:
    """Use OpenAI GPT to fill coverage parameters from document in batches of 100."""

    def __init__(self, openai_core: OpenAICore, batch_size: int = BATCH_SIZE):
        self.llm = openai_core
        self.batch_size = batch_size

    @staticmethod
    def load_coverage_list(ground_truth_path: str) -> List[Dict[str, str]]:
        """Load ground truth Excel, extract unique (상품코드, 담보PMID, 담보명) rows."""
        df = pd.read_excel(ground_truth_path, engine="openpyxl")

        # Ensure required columns exist
        for col in INPUT_FIELDS:
            if col not in df.columns:
                raise ValueError(
                    f"Ground truth Excel must have column '{col}'. "
                    f"Found columns: {list(df.columns)}"
                )

        # Deduplicate by (상품코드, 담보PMID, 담보명) to get unique coverage items
        subset = df[INPUT_FIELDS].drop_duplicates().reset_index(drop=True)

        coverages = []
        for _, row in subset.iterrows():
            coverages.append({
                "상품코드": str(row["상품코드"]).strip(),
                "담보PMID": str(row["담보PMID"]).strip(),
                "담보명": str(row["담보명"]).strip(),
            })

        return coverages

    def extract_with_batches(
        self,
        coverages: List[Dict[str, str]],
        document_markdown: str,
        log: Callable = print,
    ) -> List[ExtractionRow]:
        """Process coverages in batches of BATCH_SIZE through LLM.

        Args:
            coverages: List of dicts with 상품코드/담보PMID/담보명
            document_markdown: Full markdown text of the document (tables included)
            log: Logging callback

        Returns:
            List of ExtractionRow with all fields filled.
        """
        total = len(coverages)
        num_batches = math.ceil(total / self.batch_size)
        log(f"[LLM] Total coverages: {total}, batch size: {self.batch_size}, "
            f"batches: {num_batches}")

        all_rows: List[ExtractionRow] = []

        for batch_idx in range(num_batches):
            start = batch_idx * self.batch_size
            end = min(start + self.batch_size, total)
            batch = coverages[start:end]

            log(f"[LLM] Batch {batch_idx + 1}/{num_batches} "
                f"({len(batch)} coverages, items {start + 1}~{end})...")

            rows = self._process_batch(batch, document_markdown, log)
            log(f"[LLM] Batch {batch_idx + 1}: {len(rows)} rows extracted")
            all_rows.extend(rows)

        return all_rows

    def _process_batch(
        self,
        batch: List[Dict[str, str]],
        document_markdown: str,
        log: Callable,
    ) -> List[ExtractionRow]:
        """Send one batch of coverages to LLM for parameter extraction."""
        # Build coverage list text
        coverage_lines = []
        for i, cov in enumerate(batch, 1):
            coverage_lines.append(
                f"{i}. 상품코드={cov['상품코드']}, "
                f"담보PMID={cov['담보PMID']}, "
                f"담보명={cov['담보명']}"
            )
        coverage_list_text = "\n".join(coverage_lines)

        prompt = BATCH_EXTRACTION_PROMPT.format(
            document_markdown=document_markdown,
            batch_size=len(batch),
            coverage_list=coverage_list_text,
        )

        # Call LLM
        try:
            response = self.llm.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                json_mode=True,
                temperature=0.1,
            )
        except Exception as e:
            log(f"  [LLM] Error: {e}")
            return self._empty_rows(batch)

        # Parse response
        data = self.llm.parse_json_response(response)
        if data is None:
            log("  [LLM] Failed to parse JSON, trying fallback prompt...")
            return self._fallback_batch(batch, document_markdown, log)

        return self._data_to_rows(data, batch)

    def _fallback_batch(
        self,
        batch: List[Dict[str, str]],
        document_markdown: str,
        log: Callable,
    ) -> List[ExtractionRow]:
        """Retry with simplified fallback prompt."""
        coverage_lines = []
        for i, cov in enumerate(batch, 1):
            coverage_lines.append(
                f"{i}. 상품코드={cov['상품코드']}, "
                f"담보PMID={cov['담보PMID']}, "
                f"담보명={cov['담보명']}"
            )

        prompt = FALLBACK_BATCH_PROMPT.format(
            document_markdown=document_markdown,
            coverage_list="\n".join(coverage_lines),
        )

        try:
            response = self.llm.chat(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                json_mode=True,
                temperature=0.0,
            )
            data = self.llm.parse_json_response(response)
            if data:
                return self._data_to_rows(data, batch)
        except Exception as e:
            log(f"  [LLM] Fallback also failed: {e}")

        return self._empty_rows(batch)

    def _data_to_rows(
        self, data: list, batch: List[Dict[str, str]]
    ) -> List[ExtractionRow]:
        """Convert LLM JSON output to ExtractionRow objects."""
        rows: List[ExtractionRow] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            row = ExtractionRow(
                상품코드=str(item.get("상품코드", "")).strip(),
                담보PMID=str(item.get("담보PMID", "")).strip(),
                담보명=str(item.get("담보명", "")).strip(),
                담보구분=str(item.get("담보구분", "0")).strip(),
                보기=str(item.get("보기", "")).strip(),
                보기구분=str(item.get("보기구분", "")).strip(),
                납기=str(item.get("납기", "")).strip(),
                납기구분=str(item.get("납기구분", "")).strip(),
                시작연령=str(item.get("시작연령", "")).strip(),
                시작연령유형=str(item.get("시작연령유형", "1")).strip(),
                끝연령=str(item.get("끝연령", "")).strip(),
                끝연령유형=str(item.get("끝연령유형", "1")).strip(),
            )
            rows.append(row)
        return rows

    def _empty_rows(self, batch: List[Dict[str, str]]) -> List[ExtractionRow]:
        """Return placeholder rows with empty fill fields when LLM fails."""
        rows = []
        for cov in batch:
            rows.append(ExtractionRow(
                상품코드=cov["상품코드"],
                담보PMID=cov["담보PMID"],
                담보명=cov["담보명"],
            ))
        return rows

    @staticmethod
    def export_to_excel(rows: List[ExtractionRow], output_path: str) -> str:
        """Write extraction results to Excel file."""
        data = [asdict(r) for r in rows]
        df = pd.DataFrame(data, columns=ALL_COLUMNS)
        df.to_excel(output_path, index=False, engine="openpyxl")
        return output_path
