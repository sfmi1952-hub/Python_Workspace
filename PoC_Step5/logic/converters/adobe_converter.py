import io
import json
import logging
import re
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional

import requests

from .base_converter import BaseConverter, ConversionResult

logger = logging.getLogger(__name__)


class AdobeConverter(BaseConverter):
    """Method 2: PDF -> markdown via Adobe PDF Extract REST API."""

    ADOBE_IMS_URL = "https://ims-na1.adobelogin.com/ims/token/v3"
    ADOBE_API_BASE = "https://pdf-services.adobe.io"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    def name(self) -> str:
        return "adobe_pdf_services"

    def convert(self, file_path: str) -> ConversionResult:
        start = time.time()
        errors = []
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"PDF file not found: {file_path}")

        try:
            # Step 1: Authenticate
            token = self._authenticate()

            # Step 2: Upload PDF asset
            asset_id, upload_uri = self._get_upload_uri(token, path.name)
            self._upload_file(upload_uri, path)

            # Step 3: Create Extract PDF job
            job_url = self._create_extract_job(token, asset_id)

            # Step 4: Poll until complete
            result_uri = self._poll_job(token, job_url)

            # Step 5: Download and parse result
            markdown_text = self._download_and_parse(token, result_uri)

        except Exception as e:
            errors.append(f"Adobe API error: {e}")
            logger.error(f"Adobe conversion failed: {e}")
            markdown_text = ""

        elapsed = time.time() - start
        return ConversionResult(
            markdown_text=markdown_text,
            page_count=self._count_pages_heuristic(markdown_text),
            conversion_time_sec=elapsed,
            source_path=str(path),
            method_name=self.name(),
            errors=errors,
        )

    # ── Authentication ──────────────────────────────────────────

    def _authenticate(self) -> str:
        """Get access token from Adobe IMS. Cache until expiry."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        logger.info("Authenticating with Adobe IMS...")
        resp = requests.post(
            self.ADOBE_IMS_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "openid,AdobeID,read_organizations",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        self._token_expiry = time.time() + data.get("expires_in", 3600) - 60
        return self._access_token

    # ── Asset Upload ────────────────────────────────────────────

    def _get_upload_uri(self, token: str, filename: str):
        """Request a pre-signed upload URI from Adobe."""
        resp = requests.post(
            f"{self.ADOBE_API_BASE}/assets",
            headers=self._auth_headers(token),
            json={"mediaType": "application/pdf"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["assetID"], data["uploadUri"]

    def _upload_file(self, upload_uri: str, file_path: Path):
        """Upload the PDF file to the pre-signed URI."""
        with open(file_path, "rb") as f:
            resp = requests.put(
                upload_uri,
                data=f,
                headers={"Content-Type": "application/pdf"},
            )
        resp.raise_for_status()
        logger.info(f"Uploaded {file_path.name}")

    # ── Extract PDF Job ─────────────────────────────────────────

    def _create_extract_job(self, token: str, asset_id: str) -> str:
        """Create an Extract PDF job with table structure extraction."""
        resp = requests.post(
            f"{self.ADOBE_API_BASE}/operation/extractpdf",
            headers=self._auth_headers(token),
            json={
                "assetID": asset_id,
                "elementsToExtract": ["text", "tables"],
                "tableOutputFormat": "csv",
                "renditionsToExtract": [],
            },
        )
        resp.raise_for_status()
        # Job location from headers
        job_url = resp.headers.get("location") or resp.headers.get("x-request-id")
        if not job_url:
            # Fallback: check response body
            data = resp.json()
            job_url = data.get("location", data.get("jobID", ""))

        logger.info(f"Extract job created: {job_url}")
        return job_url

    def _poll_job(self, token: str, job_url: str, timeout: int = 300) -> str:
        """Poll the job status until completion. Returns the download URI."""
        start = time.time()
        while time.time() - start < timeout:
            resp = requests.get(job_url, headers=self._auth_headers(token))
            resp.raise_for_status()
            data = resp.json()
            status = data.get("status", "")

            if status == "done":
                logger.info(f"Job done. Response keys: {list(data.keys())}")
                logger.info(f"content keys: {list(data.get('content', {}).keys()) if isinstance(data.get('content'), dict) else 'N/A'}")
                logger.info(f"resource keys: {list(data.get('resource', {}).keys()) if isinstance(data.get('resource'), dict) else 'N/A'}")

                # Prefer 'resource' (usually the ZIP), then 'content'
                download_uri = data.get("resource", {}).get("downloadUri", "")
                if not download_uri:
                    download_uri = data.get("content", {}).get("downloadUri", "")
                if not download_uri:
                    for key in data:
                        if isinstance(data[key], dict) and "downloadUri" in data[key]:
                            download_uri = data[key]["downloadUri"]
                            break
                if not download_uri:
                    raise RuntimeError(f"Job done but no downloadUri in: {json.dumps(data, indent=2)[:2000]}")
                logger.info(f"Download URI obtained from response (len={len(download_uri)})")
                return download_uri
            elif status == "failed":
                raise RuntimeError(f"Adobe Extract job failed: {data}")

            logger.info(f"Job status: {status}, waiting...")
            time.sleep(5)

        raise TimeoutError(f"Adobe Extract job timed out after {timeout}s")

    # ── Download & Parse ────────────────────────────────────────

    def _download_and_parse(self, token: str, download_uri: str) -> str:
        """Download result, extract structured data, convert to markdown.

        Adobe PDF Extract API returns a ZIP file containing:
        - structuredData.json (text elements, paragraphs, headings)
        - tables/*.csv (extracted tables)

        CSV tables are interleaved into the document flow at the positions
        where they appear in structuredData.json, replacing the flat cell text.
        """
        # Pre-signed S3 URL: do NOT send auth headers or Content-Type
        resp = requests.get(download_uri)
        resp.raise_for_status()

        content = resp.content
        logger.info(f"Downloaded {len(content):,} bytes, first bytes: {content[:4]}")

        markdown_parts = []

        # Check if it's a ZIP file (magic bytes: PK\x03\x04)
        if content[:4] == b'PK\x03\x04':
            logger.info("Response is ZIP format")
            with zipfile.ZipFile(io.BytesIO(content)) as zf:
                names = zf.namelist()
                logger.info(f"ZIP contains {len(names)} files: {names[:20]}")

                # Step 1: Load all CSV tables in order (fileoutpart0, 1, 2, ...)
                csv_tables: List[str] = []
                csv_files = [n for n in names if n.endswith(".csv")]
                csv_files_sorted = sorted(csv_files, key=self._csv_sort_key)
                for csv_name in csv_files_sorted:
                    with zf.open(csv_name) as f:
                        csv_content = f.read().decode("utf-8", errors="replace")
                    md_table = self._csv_to_markdown(csv_content, csv_name)
                    csv_tables.append(md_table if md_table else "")
                logger.info(f"Loaded {len(csv_tables)} CSV tables")

                # Step 2: Parse structuredData.json with CSV tables interleaved
                if "structuredData.json" in names:
                    with zf.open("structuredData.json") as f:
                        structured = json.loads(f.read())
                    markdown_parts.append(
                        self._structured_to_markdown(structured, csv_tables)
                    )
                elif csv_tables:
                    # No structured data, just append CSV tables
                    markdown_parts.extend(t for t in csv_tables if t)

        # Check if it's JSON directly
        elif content[:1] in (b'{', b'['):
            logger.info("Response is JSON format (not ZIP)")
            try:
                data = json.loads(content)
                if isinstance(data, dict) and "elements" in data:
                    markdown_parts.append(self._structured_to_markdown(data, []))
                elif isinstance(data, dict):
                    for key in data:
                        if isinstance(data[key], dict) and "elements" in data[key]:
                            markdown_parts.append(
                                self._structured_to_markdown(data[key], [])
                            )
                    if not markdown_parts:
                        markdown_parts.append(json.dumps(data, indent=2, ensure_ascii=False)[:50000])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse as JSON: {e}")
                markdown_parts.append(content.decode("utf-8", errors="replace")[:50000])
        else:
            logger.warning(f"Unknown response format, first 100 bytes: {content[:100]}")
            text = content.decode("utf-8", errors="replace")
            if text.strip():
                markdown_parts.append(text[:100000])

        result = "\n\n".join(markdown_parts)
        logger.info(f"Parsed markdown: {len(result):,} chars")
        return result

    def _structured_to_markdown(
        self, data: dict, csv_tables: List[str] = None
    ) -> str:
        """Convert Adobe's structuredData.json to markdown.

        Table cell elements (path containing /Table) are skipped because
        their content is already captured in CSV files. Instead, the
        corresponding CSV markdown table is inserted at the position
        where each table first appears in the document flow.
        """
        if csv_tables is None:
            csv_tables = []

        parts = []
        elements = data.get("elements", [])
        seen_tables: set = set()
        table_counter = 0

        for elem in elements:
            path = elem.get("Path", "")
            text = elem.get("Text", "")

            # Detect table elements by path (e.g., /Document/Table, /Document/Table[2])
            table_match = re.search(r"/Table(?:\[(\d+)\])?", path)
            if table_match:
                # Extract unique table identifier from path
                # e.g., "/Document/Table" or "/Document/Table[2]/TR[1]/TD[1]/P"
                # We want just the table-level path up to /Table or /Table[N]
                table_id = path[: table_match.end()]

                if table_id not in seen_tables:
                    seen_tables.add(table_id)
                    # Insert the corresponding CSV table
                    if table_counter < len(csv_tables) and csv_tables[table_counter]:
                        parts.append(f"\n{csv_tables[table_counter]}\n")
                    table_counter += 1
                # Skip all table cell text (already in CSV)
                continue

            # Headings
            if "/H" in path:
                level = 1
                for i in range(1, 7):
                    if f"/H{i}" in path:
                        level = i
                        break
                parts.append(f"{'#' * level} {text}")

            # Paragraphs
            elif "/P" in path:
                if text.strip():
                    parts.append(text)

            # List items
            elif "/Li" in path or "/Lbl" in path:
                if text.strip():
                    parts.append(f"- {text}")

        # Append any remaining CSV tables not matched to structured data
        for i in range(table_counter, len(csv_tables)):
            if csv_tables[i]:
                parts.append(f"\n{csv_tables[i]}\n")

        logger.info(
            f"Structured to markdown: {len(elements)} elements, "
            f"{len(seen_tables)} tables found, {len(csv_tables)} CSVs available"
        )
        return "\n\n".join(parts)

    def _csv_to_markdown(self, csv_content: str, name: str) -> str:
        """Convert a CSV table (from Adobe Extract) to markdown table format."""
        lines = csv_content.strip().split("\n")
        if len(lines) < 2:
            return ""

        import csv as csv_mod
        reader = csv_mod.reader(lines)
        rows = list(reader)

        if not rows:
            return ""

        md_lines = [f"<!-- Adobe Table: {name} -->"]

        # Header
        header = rows[0]
        md_lines.append("| " + " | ".join(header) + " |")
        md_lines.append("| " + " | ".join(["---"] * len(header)) + " |")

        # Data
        for row in rows[1:]:
            # Pad row to match header length
            while len(row) < len(header):
                row.append("")
            md_lines.append("| " + " | ".join(row) + " |")

        return "\n".join(md_lines)

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _csv_sort_key(name: str) -> int:
        """Sort CSV filenames by numeric part (fileoutpart0, fileoutpart1, ...)."""
        m = re.search(r"(\d+)\.csv$", name)
        return int(m.group(1)) if m else 0

    def _auth_headers(self, token: str) -> dict:
        return {
            "Authorization": f"Bearer {token}",
            "x-api-key": self.client_id,
            "Content-Type": "application/json",
        }

    @staticmethod
    def _count_pages_heuristic(text: str) -> int:
        if not text:
            return 0
        # Rough estimate: ~3000 chars per page
        return max(1, len(text) // 3000)
