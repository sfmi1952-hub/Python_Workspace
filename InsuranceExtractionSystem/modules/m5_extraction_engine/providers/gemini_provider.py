"""
M5 Provider: Google Gemini (3.1 Pro → 3.0 Pro → Flash 폴백)
PoC_Step3/logic/gemini_core.py 기반 이식
"""
import os
import time
import tempfile

import google.generativeai as genai

from .base import BaseLLMProvider, LLMResponse


class GeminiProvider(BaseLLMProvider):
    provider_name = "gemini"

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.model = None
        self.model_name = None
        self.available_models = []
        if api_key:
            self.configure(api_key)

    def configure(self, api_key: str):
        self.api_key = api_key
        genai.configure(api_key=api_key)

        try:
            self.available_models = [m.name for m in genai.list_models()]
        except Exception as e:
            print(f"Warning: Could not list models: {e}")

        # Tier 1: Gemini 3.1 Pro → 3.0 Pro
        target = self._find_model(["gemini-3.1-pro", "gemini-3.1", "gemini-3.0-pro", "gemini-3-pro"])
        if not target:
            target = "gemini-1.5-pro"

        self.model = genai.GenerativeModel(target)
        self.model_name = target
        print(f"[Gemini] Selected model: {self.model_name}")

    def _find_model(self, keywords: list[str]) -> str | None:
        for k in keywords:
            for m in self.available_models:
                if k.lower() in m.lower():
                    return m
        return None

    def get_model_name(self) -> str:
        return self.model_name or "unknown"

    def upload_file(self, path: str, mime_type: str = None, logger=print) -> object:
        if not self.api_key:
            raise ValueError("API Key not configured")

        path_to_upload = path

        # Excel → CSV 자동 변환
        ext = os.path.splitext(path)[1].lower()
        if ext in [".xlsx", ".xls"]:
            try:
                import pandas as pd
                logger(f"  Converting {os.path.basename(path)} to CSV...")
                engine = "openpyxl" if ext == ".xlsx" else None
                df = pd.read_excel(path, engine=engine)
                fd, csv_path = tempfile.mkstemp(suffix=".csv")
                os.close(fd)
                df.to_csv(csv_path, index=False)
                path_to_upload = csv_path
                mime_type = "text/csv"
            except Exception as e:
                logger(f"  > Excel conversion failed ({e}). Uploading original.")
                mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

        if not mime_type:
            ext = os.path.splitext(path_to_upload)[1].lower()
            mime_map = {".pdf": "application/pdf", ".csv": "text/csv", ".txt": "text/plain", ".md": "text/plain"}
            mime_type = mime_map.get(ext)

        logger(f"  Uploading {os.path.basename(path_to_upload)} (MIME: {mime_type})...")
        f = genai.upload_file(path_to_upload, mime_type=mime_type)

        while f.state.name == "PROCESSING":
            time.sleep(1)
            f = genai.get_file(f.name)

        if f.state.name != "ACTIVE":
            raise Exception(f"File upload failed: {f.state.name}")

        logger(f"  > File active: {f.name}")
        return f

    def cleanup_file(self, file_ref: object):
        try:
            if hasattr(genai, "files") and hasattr(genai.files, "delete"):
                genai.files.delete(name=file_ref.name)
            elif hasattr(genai, "delete_file"):
                getattr(genai, "delete_file")(file_ref.name)
        except Exception:
            pass

    def generate(self, prompt: str, files: list = None, **kwargs) -> LLMResponse:
        if not self.model:
            raise ValueError("Model not initialized")

        contents = [prompt]
        if files:
            contents.extend(files)

        timeout = kwargs.get("timeout", 600)
        retries = kwargs.get("retries", 3)
        base_delay = kwargs.get("base_delay", 10)
        current_delay = base_delay

        for attempt in range(retries):
            try:
                if attempt > 0:
                    time.sleep(current_delay)

                response = self.model.generate_content(
                    contents, request_options={"timeout": timeout}
                )
                return LLMResponse(
                    text=response.text or "",
                    model_used=self.model_name,
                    provider=self.provider_name,
                )

            except Exception as e:
                err = str(e).lower()
                is_rate = any(k in err for k in ["429", "resource has been exhausted", "quota"])
                is_server = any(k in err for k in ["503", "504", "deadline exceeded", "timeout"])

                if is_rate:
                    print(f"WARNING: Gemini quota hit ({e})")
                    next_model = self._get_fallback_model()
                    if next_model and next_model != self.model_name:
                        print(f"  > Switching: {self.model_name} → {next_model}")
                        self.model = genai.GenerativeModel(next_model)
                        self.model_name = next_model
                        time.sleep(1)
                        continue

                    time.sleep(current_delay)
                    current_delay *= 2

                elif is_server:
                    print(f"WARNING: Server error ({e}). Retry in {current_delay}s...")
                    time.sleep(current_delay)
                    current_delay *= 2
                else:
                    raise

        raise Exception(f"Gemini: Failed after {retries} retries")

    def _get_fallback_model(self) -> str | None:
        curr = self.model_name.lower()
        if "flash" not in curr and "2.5" not in curr and "1.5" not in curr:
            # Tier 1 → Tier 2
            tier2 = self._find_model(["gemini-3.0-pro", "gemini-2.5-pro"])
            return tier2 or "gemini-1.5-pro"
        elif ("2.5" in curr or "1.5" in curr) and "flash" not in curr:
            # Tier 2 → Tier 3
            tier3 = self._find_model(["gemini-3.0-flash", "gemini-2.0-flash"])
            return tier3 or "gemini-1.5-flash"
        return None
