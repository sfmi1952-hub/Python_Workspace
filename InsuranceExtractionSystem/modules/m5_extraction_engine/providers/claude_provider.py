"""
M5 Provider: Anthropic Claude (Sonnet 4.6 → Haiku 4.5 폴백)
"""
import os
import time
import base64

import anthropic

from .base import BaseLLMProvider, LLMResponse


class ClaudeProvider(BaseLLMProvider):
    provider_name = "claude"

    MODEL_TIERS = [
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001",
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
        self.client = anthropic.Anthropic(api_key=api_key)
        self.current_tier = 0
        self.model_name = self.MODEL_TIERS[0]
        print(f"[Claude] Selected model: {self.model_name}")

    def get_model_name(self) -> str:
        return self.model_name or "unknown"

    def supports_file_upload(self) -> bool:
        return True  # PDF를 base64로 직접 전달

    def upload_file(self, path: str, mime_type: str = None, logger=print) -> object:
        """PDF를 base64 인코딩하여 메모리에 보관"""
        if not mime_type:
            ext = os.path.splitext(path)[1].lower()
            mime_map = {".pdf": "application/pdf", ".csv": "text/csv", ".txt": "text/plain"}
            mime_type = mime_map.get(ext, "application/octet-stream")

        with open(path, "rb") as f:
            data = base64.standard_b64encode(f.read()).decode("utf-8")

        logger(f"  > File loaded: {os.path.basename(path)} ({mime_type})")
        return {"data": data, "mime_type": mime_type, "filename": os.path.basename(path)}

    def cleanup_file(self, file_ref: object):
        pass  # 메모리 기반이므로 별도 정리 불필요

    def generate(self, prompt: str, files: list = None, **kwargs) -> LLMResponse:
        if not self.client:
            raise ValueError("Client not initialized")

        retries = kwargs.get("retries", 3)
        base_delay = kwargs.get("base_delay", 10)
        max_tokens = kwargs.get("max_tokens", 16384)
        current_delay = base_delay

        # 메시지 구성
        content = []

        # 파일 첨부 (base64 PDF)
        if files:
            for f in files:
                if isinstance(f, dict) and "data" in f:
                    if f["mime_type"] == "application/pdf":
                        content.append({
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": f["data"],
                            },
                        })
                    else:
                        # 텍스트 계열은 디코딩하여 텍스트로 추가
                        try:
                            text_data = base64.standard_b64decode(f["data"]).decode("utf-8")
                            content.append({
                                "type": "text",
                                "text": f"=== {f['filename']} ===\n{text_data}",
                            })
                        except Exception:
                            pass

        content.append({"type": "text", "text": prompt})

        for attempt in range(retries):
            try:
                if attempt > 0:
                    time.sleep(current_delay)

                response = self.client.messages.create(
                    model=self.model_name,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": content}],
                )

                text = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text += block.text

                return LLMResponse(
                    text=text,
                    model_used=self.model_name,
                    provider=self.provider_name,
                    usage={
                        "input_tokens": response.usage.input_tokens,
                        "output_tokens": response.usage.output_tokens,
                    },
                )

            except Exception as e:
                err = str(e).lower()
                is_rate = any(k in err for k in ["429", "rate_limit", "overloaded"])
                is_server = any(k in err for k in ["500", "502", "503", "529"])

                if is_rate:
                    print(f"WARNING: Claude rate limit ({e})")
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

        raise Exception(f"Claude: Failed after {retries} retries")
