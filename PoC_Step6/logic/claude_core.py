"""
Claude Opus 4.7 API 호출 클라이언트.
사외 SOTA LLM (Anthropic Claude) - AWS Bedrock 또는 Anthropic Direct API 호환.

사용 환경변수:
    ANTHROPIC_API_KEY        - Direct API 사용 시
    ANTHROPIC_MODEL          - 모델 ID (기본: claude-opus-4-7)
    ANTHROPIC_USE_BEDROCK    - "true" 일 경우 AWS Bedrock 경로 사용
    AWS_REGION               - Bedrock 사용 시 (기본: us-east-1)
"""
import os
import time
import base64


class ClaudeCore:
    PROVIDER_NAME = "Claude Opus 4.7 (사외 SOTA LLM)"

    def __init__(self, api_key=None, model_id=None, use_bedrock=False, region=None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.model_id = model_id or os.environ.get("ANTHROPIC_MODEL", "claude-opus-4-7")
        self.use_bedrock = use_bedrock or (os.environ.get("ANTHROPIC_USE_BEDROCK", "").lower() == "true")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.client = None
        self.bedrock_model_id = os.environ.get(
            "BEDROCK_MODEL_ID",
            "anthropic.claude-opus-4-7-20260101-v1:0",
        )
        self._init_client()

    def _init_client(self):
        if self.use_bedrock:
            try:
                from anthropic import AnthropicBedrock
                self.client = AnthropicBedrock(aws_region=self.region)
                self.model_name = self.bedrock_model_id
            except ImportError:
                raise ImportError("anthropic[bedrock] SDK가 필요합니다. pip install 'anthropic[bedrock]' boto3")
        else:
            try:
                from anthropic import Anthropic
                if not self.api_key:
                    raise ValueError("ANTHROPIC_API_KEY 환경변수가 설정되지 않았습니다.")
                self.client = Anthropic(api_key=self.api_key)
                self.model_name = self.model_id
            except ImportError:
                raise ImportError("anthropic SDK가 필요합니다. pip install anthropic")

    def get_model_name(self):
        return self.model_name

    @staticmethod
    def _file_to_block(path):
        """파일 경로를 Claude 메시지 콘텐츠 블록으로 변환."""
        ext = os.path.splitext(path)[1].lower()
        if ext == ".pdf":
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/pdf", "data": data},
            }
        elif ext in [".txt", ".md", ".csv"]:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                return {"type": "text", "text": f.read()}
        else:
            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")
            return {
                "type": "document",
                "source": {"type": "base64", "media_type": "application/octet-stream", "data": data},
            }

    def generate(self, prompt_text, files=None, max_tokens=16000, temperature=None, logger=print):
        """
        프롬프트 + 첨부 파일을 Claude에 전달하고 텍스트 응답을 반환.

        files: 파일 경로 리스트 (PDF 또는 텍스트). PDF는 base64로 전송.
        temperature: Opus 4.7+ 은 미지원이므로 기본 None (전달 안 함).
        """
        content_blocks = []
        if files:
            for p in files:
                try:
                    content_blocks.append(self._file_to_block(p))
                except Exception as e:
                    logger(f"  > [Claude] file convert fail {p}: {e}")
        content_blocks.append({"type": "text", "text": prompt_text})

        messages = [{"role": "user", "content": content_blocks}]

        last_err = None
        for attempt in range(3):
            try:
                kwargs = {
                    "model": self.model_name,
                    "max_tokens": max_tokens,
                    "messages": messages,
                }
                if temperature is not None:
                    kwargs["temperature"] = temperature
                resp = self.client.messages.create(**kwargs)
                text_out = "".join(
                    [blk.text for blk in resp.content if getattr(blk, "type", None) == "text"]
                )
                usage = getattr(resp, "usage", None)
                return {
                    "text": text_out,
                    "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
                    "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
                    "model": self.model_name,
                }
            except Exception as e:
                last_err = e
                err = str(e).lower()
                if any(k in err for k in ["429", "overloaded", "rate", "503", "timeout"]):
                    delay = 10 * (attempt + 1)
                    logger(f"  > [Claude] 일시 오류 (재시도 {attempt+1}/3, {delay}s): {e}")
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError(f"Claude 호출 실패 (3회 재시도): {last_err}")
