"""
M5 Provider: OpenAI (GPT-5.2 → gpt-5.2-chat-latest → gpt-4.1-mini 폴백)
PoC_Step3_GPTv/logic/openai_core.py 기반 이식
"""
import os
import time
import tempfile

from openai import OpenAI

from .base import BaseLLMProvider, LLMResponse


class OpenAIProvider(BaseLLMProvider):
    provider_name = "openai"

    MODEL_TIERS = [
        "gpt-5.2",
        "gpt-5.2-chat-latest",
        "gpt-4.1-mini",
    ]

    def __init__(self, api_key: str = None):
        self.api_key = api_key
        self.client = None
        self.model_name = None
        self.current_tier = 0
        if api_key:
            self.configure(api_key)

    def configure(self, api_key: str):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)
        self.current_tier = 0
        self.model_name = self.MODEL_TIERS[0]
        print(f"[OpenAI] Selected model: {self.model_name}")

    def get_model_name(self) -> str:
        return self.model_name or "unknown"

    def supports_file_upload(self) -> bool:
        return False  # OpenAI는 Vector Store 방식 사용

    def supports_vector_store(self) -> bool:
        return True

    # ── Vector Store 관리 ─────────────────────────────────────────────────

    def create_vector_store(self, name: str = "extraction_store", logger=print) -> object:
        vs = self.client.vector_stores.create(name=name)
        logger(f"  > Vector Store created: {vs.id} ({name})")
        return vs

    def upload_to_vector_store(self, vs_id: str, path: str, logger=print) -> object | None:
        path_to_upload = path
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
            except Exception as e:
                logger(f"  > Excel conversion failed ({e}). Skipping.")
                return None

        logger(f"  Uploading {os.path.basename(path_to_upload)} to Vector Store...")
        try:
            result = self.client.vector_stores.files.upload_and_poll(
                vector_store_id=vs_id,
                file=open(path_to_upload, "rb"),
            )
            logger(f"  > Upload complete: {result.id} (status={result.status})")
            return result
        except Exception as e:
            logger(f"  > Upload failed: {e}")
            return None

    def delete_vector_store(self, vs_id: str, logger=print):
        try:
            self.client.vector_stores.delete(vector_store_id=vs_id)
            logger(f"  > Vector Store deleted: {vs_id}")
        except Exception:
            pass

    # ── Dummy file methods (Vector Store 방식이므로 미사용) ────────────────

    def upload_file(self, path: str, mime_type: str = None, logger=print) -> object:
        raise NotImplementedError("OpenAI uses Vector Store instead of direct file upload")

    def cleanup_file(self, file_ref: object):
        pass

    # ── LLM 호출 ─────────────────────────────────────────────────────────

    def generate(self, prompt: str, files: list = None, **kwargs) -> LLMResponse:
        if not self.client:
            raise ValueError("Client not initialized")

        vector_store_ids = kwargs.get("vector_store_ids")
        retries = kwargs.get("retries", 3)
        base_delay = kwargs.get("base_delay", 10)
        current_delay = base_delay

        for attempt in range(retries):
            try:
                if attempt > 0:
                    time.sleep(current_delay)

                tools = []
                if vector_store_ids:
                    tools.append({
                        "type": "file_search",
                        "vector_store_ids": vector_store_ids,
                        "max_num_results": 50,
                    })

                req = {"model": self.model_name, "input": prompt}
                if tools:
                    req["tools"] = tools

                response = self.client.responses.create(**req)
                text = self._extract_text(response)

                return LLMResponse(
                    text=text,
                    model_used=self.model_name,
                    provider=self.provider_name,
                )

            except Exception as e:
                err = str(e).lower()
                is_rate = any(k in err for k in ["429", "rate_limit", "rate limit", "quota"])
                is_server = any(k in err for k in ["500", "502", "503", "504", "timeout"])

                if is_rate:
                    print(f"WARNING: OpenAI rate limit ({e})")
                    if self.current_tier < len(self.MODEL_TIERS) - 1:
                        self.current_tier += 1
                        old = self.model_name
                        self.model_name = self.MODEL_TIERS[self.current_tier]
                        print(f"  > Switching: {old} → {self.model_name}")
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

        raise Exception(f"OpenAI: Failed after {retries} retries")

    @staticmethod
    def _extract_text(response) -> str:
        texts = []
        for item in response.output:
            if hasattr(item, "content"):
                for block in item.content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
        return "\n".join(texts)
