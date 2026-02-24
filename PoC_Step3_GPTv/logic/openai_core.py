# OpenAI Client for PoC Step 3 GPT Version
# Replaces gemini_core.py — uses Responses API + file_search (Vector Store)
import time
import os
import tempfile
from openai import OpenAI


class OpenAICore:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.client = None
        self.model_name = None
        if api_key:
            self.configure(api_key)

    def configure(self, api_key):
        self.api_key = api_key
        self.client = OpenAI(api_key=api_key)

        # Strategy:
        # Tier 1 (Primary): gpt-5.2
        # Tier 2 (Mid): gpt-5.2-chat-latest (Instant — faster)
        # Tier 3 (Fast): gpt-4.1-mini
        self.model_tiers = [
            "gpt-5.2",
            "gpt-5.2-chat-latest",
            "gpt-4.1-mini",
        ]
        self.current_tier = 0
        self.model_name = self.model_tiers[0]
        print(f"DEBUG: Selected Initial OpenAI Model: {self.model_name}")

    def get_model_name(self):
        return self.model_name

    # ── Vector Store 관리 ─────────────────────────────────────────────────

    def create_vector_store(self, name="poc_store", logger=print):
        """RAG용 Vector Store를 생성합니다."""
        vs = self.client.vector_stores.create(name=name)
        logger(f"  > Vector Store 생성: {vs.id} ({name})")
        return vs

    def upload_to_vector_store(self, vector_store_id, path, logger=print):
        """파일을 Vector Store에 업로드합니다. Excel → CSV 자동 변환."""
        path_to_upload = path
        ext = os.path.splitext(path)[1].lower()

        # Auto-convert Excel to CSV (Vector Store에서 xlsx 미지원)
        if ext in [".xlsx", ".xls"]:
            try:
                import pandas as pd
                logger(f"  Converting Excel {os.path.basename(path)} to CSV for Vector Store...")
                engine = "openpyxl" if ext == ".xlsx" else None
                df = pd.read_excel(path, engine=engine)
                fd, csv_path = tempfile.mkstemp(suffix=".csv")
                os.close(fd)
                df.to_csv(csv_path, index=False)
                path_to_upload = csv_path
                logger(f"    > Conversion successful: {os.path.basename(csv_path)}")
            except Exception as e:
                logger(f"    > Warning: Excel conversion failed ({e}). Skipping file.")
                return None

        logger(f"  Uploading {os.path.basename(path_to_upload)} to Vector Store...")

        try:
            result = self.client.vector_stores.files.upload_and_poll(
                vector_store_id=vector_store_id,
                file=open(path_to_upload, "rb"),
            )
            logger(f"    > Upload complete: {result.id} (status={result.status})")
            return result
        except Exception as e:
            logger(f"    > Upload failed: {e}")
            return None

    def delete_vector_store(self, vector_store_id, logger=print):
        """Vector Store를 삭제합니다."""
        try:
            self.client.vector_stores.delete(vector_store_id=vector_store_id)
            logger(f"  > Vector Store 삭제: {vector_store_id}")
        except Exception:
            pass  # 삭제 실패는 치명적이지 않음

    # ── LLM 호출 (Responses API) ──────────────────────────────────────────

    def generate_content(self, prompt_text, vector_store_ids=None, retries=3, base_delay=10):
        """
        OpenAI Responses API를 통한 LLM 호출.
        vector_store_ids가 주어지면 file_search 도구를 활성화합니다.
        3-tier 모델 폴백 포함.
        """
        if not self.client:
            raise ValueError("Client not initialized")

        current_delay = base_delay

        for attempt in range(retries):
            try:
                if attempt > 0:
                    time.sleep(current_delay)

                # Build tools list
                tools = []
                if vector_store_ids:
                    tools.append({
                        "type": "file_search",
                        "vector_store_ids": vector_store_ids,
                        "max_num_results": 50,
                    })

                # Build request kwargs
                kwargs = {
                    "model": self.model_name,
                    "input": prompt_text,
                }
                if tools:
                    kwargs["tools"] = tools

                response = self.client.responses.create(**kwargs)
                return response

            except Exception as e:
                err_str = str(e).lower()
                retry_keywords = ["429", "rate_limit", "rate limit", "quota", "too many requests"]
                server_error_keywords = ["500", "502", "503", "504", "timeout", "server_error", "service unavailable"]

                is_rate_limit = any(k in err_str for k in retry_keywords)
                is_server_error = any(k in err_str for k in server_error_keywords)

                if is_rate_limit:
                    print(f"WARNING: API Rate Limit Hit ({e}).")
                    # Fallback to next tier
                    if self.current_tier < len(self.model_tiers) - 1:
                        self.current_tier += 1
                        old_model = self.model_name
                        self.model_name = self.model_tiers[self.current_tier]
                        print(f"  > Switching Model: {old_model} -> {self.model_name}")
                        time.sleep(1)
                        continue

                    print(f"  > Retrying in {current_delay}s... (Attempt {attempt+1}/{retries})")
                    time.sleep(current_delay)
                    current_delay *= 2

                elif is_server_error:
                    print(f"WARNING: Server Error ({e}). Retrying in {current_delay}s... (Attempt {attempt+1}/{retries})")
                    time.sleep(current_delay)
                    current_delay *= 2
                else:
                    raise e

        raise Exception(f"Failed to generate content after {retries} retries.")

    # ── 응답 텍스트 추출 헬퍼 ──────────────────────────────────────────────

    @staticmethod
    def extract_text(response):
        """Responses API 응답에서 텍스트를 추출합니다."""
        texts = []
        for item in response.output:
            if hasattr(item, "content"):
                for block in item.content:
                    if hasattr(block, "text"):
                        texts.append(block.text)
        return "\n".join(texts)
