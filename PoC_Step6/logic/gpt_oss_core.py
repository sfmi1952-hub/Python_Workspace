"""
사내 sLM (GPT-OSS) API 호출 클라이언트.
OpenAI 호환 Chat Completions API 가정 (vLLM, TGI, Ollama, llama.cpp-server 등).

사용 환경변수:
    GPT_OSS_API_BASE     - 사내 sLM 엔드포인트 (예: http://gpt-oss.internal:8000/v1)
    GPT_OSS_API_KEY      - 인증 키 (없으면 "EMPTY")
    GPT_OSS_MODEL        - 모델명 (기본: gpt-oss-120b)
"""
import os
import time


class GPTOSSCore:
    PROVIDER_NAME = "GPT-OSS (사내 sLM)"

    def __init__(self, api_base=None, api_key=None, model=None):
        self.api_base = api_base or os.environ.get("GPT_OSS_API_BASE", "http://localhost:8000/v1")
        self.api_key = api_key or os.environ.get("GPT_OSS_API_KEY", "EMPTY")
        self.model_name = model or os.environ.get("GPT_OSS_MODEL", "gpt-oss-120b")
        self.client = None
        self._init_client()

    def _init_client(self):
        try:
            from openai import OpenAI
            self.client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        except ImportError:
            raise ImportError("openai SDK가 필요합니다. pip install openai>=1.0")

    def get_model_name(self):
        return self.model_name

    def generate(self, prompt_text, files=None, max_tokens=16000, temperature=0.0, logger=print):
        """
        프롬프트 + 추출된 텍스트 파일을 GPT-OSS에 전달.
        GPT-OSS는 PDF 멀티모달을 지원하지 않으므로 호출 측에서 PDF→텍스트 변환 후 전달.

        files: 텍스트 파일 경로 리스트. 본문 앞에 첨부 텍스트로 합쳐 전송.
        """
        attached = []
        if files:
            for p in files:
                try:
                    with open(p, "r", encoding="utf-8", errors="ignore") as f:
                        body = f.read()
                    attached.append(f"\n===== 첨부: {os.path.basename(p)} =====\n{body}\n")
                except Exception as e:
                    logger(f"  > [GPT-OSS] 첨부 로드 실패 {p}: {e}")

        full_user = (
            "\n".join(attached) + "\n\n" + prompt_text
            if attached
            else prompt_text
        )

        messages = [
            {"role": "system", "content": "당신은 한국어 보험 약관 분석 전문가입니다. 지시에 따라 JSON 형식으로만 응답하세요."},
            {"role": "user", "content": full_user},
        ]

        last_err = None
        for attempt in range(3):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model_name,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                msg = resp.choices[0].message
                text_out = msg.content or ""
                # reasoning 모델(gpt-oss 등)은 reasoning trace 가 별도 필드에 있으면 폴백
                if not text_out and hasattr(msg, "reasoning") and msg.reasoning:
                    text_out = msg.reasoning
                usage = getattr(resp, "usage", None)
                reasoning_tokens = 0
                if usage and getattr(usage, "completion_tokens_details", None):
                    reasoning_tokens = getattr(usage.completion_tokens_details, "reasoning_tokens", 0) or 0
                finish = resp.choices[0].finish_reason
                if finish == "length":
                    logger(f"  > [GPT-OSS] WARNING finish_reason=length (응답 잘림). max_tokens 증가 필요. reasoning_tokens={reasoning_tokens}")
                return {
                    "text": text_out,
                    "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
                    "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
                    "reasoning_tokens": reasoning_tokens,
                    "finish_reason": finish,
                    "model": self.model_name,
                }
            except Exception as e:
                last_err = e
                err = str(e).lower()
                if any(k in err for k in ["429", "rate", "503", "timeout", "overload"]):
                    delay = 10 * (attempt + 1)
                    logger(f"  > [GPT-OSS] 일시 오류 (재시도 {attempt+1}/3, {delay}s): {e}")
                    time.sleep(delay)
                    continue
                raise

        raise RuntimeError(f"GPT-OSS 호출 실패 (3회 재시도): {last_err}")
