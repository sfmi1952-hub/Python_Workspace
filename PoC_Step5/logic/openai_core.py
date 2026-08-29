import json
import time
import logging
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAICore:
    """OpenAI GPT client with rate-limit retry (no model fallback)."""

    # 모델별 max_completion_tokens 상한
    MODEL_MAX_TOKENS = {
        "gpt-5.2": 100_000,
        "gpt-5.1": 100_000,
        "gpt-4o": 16_384,
        "gpt-4o-mini": 16_384,
    }

    FALLBACK_MODEL = "gpt-5.1"

    MAX_RETRIES = 5  # rate-limit 재시도 횟수

    def __init__(self, api_key: str, model: str = "gpt-5.2"):
        self.client = OpenAI(api_key=api_key, timeout=1800.0)  # 30분 타임아웃
        self.primary_model = model
        self.current_model = model

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 500000,
    ) -> str:
        """Send a chat completion request.

        Rate limit → wait & retry (same model).
        All retries exhausted → fallback to FALLBACK_MODEL.
        """
        models_to_try = [self.primary_model]
        if self.FALLBACK_MODEL and self.FALLBACK_MODEL != self.primary_model:
            models_to_try.append(self.FALLBACK_MODEL)

        last_error = None
        for model in models_to_try:
            for attempt in range(1, self.MAX_RETRIES + 1):
                try:
                    return self._call(
                        model=model,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        json_mode=json_mode,
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                except Exception as e:
                    last_error = e
                    error_str = str(e)
                    if "429" in error_str or "rate_limit" in error_str.lower():
                        wait = self._parse_retry_after(error_str, default=15)
                        logger.warning(
                            f"[API] Rate limit on {model} (attempt {attempt}/{self.MAX_RETRIES}), "
                            f"waiting {wait}s..."
                        )
                        time.sleep(wait)
                        continue
                    elif "500" in error_str or "503" in error_str:
                        wait = 5 * attempt
                        logger.warning(
                            f"[API] Server error on {model} (attempt {attempt}), "
                            f"waiting {wait}s..."
                        )
                        time.sleep(wait)
                        continue
                    elif "timeout" in error_str.lower() or "timed out" in error_str.lower():
                        wait = 10 * attempt
                        logger.warning(
                            f"[API] Timeout on {model} (attempt {attempt}), "
                            f"waiting {wait}s..."
                        )
                        time.sleep(wait)
                        continue
                    else:
                        raise

            # 현재 모델 재시도 소진 → fallback
            if model != models_to_try[-1]:
                logger.warning(
                    f"[API] {model} retries exhausted, falling back to {models_to_try[-1]}..."
                )

        raise RuntimeError(
            f"All models failed after {self.MAX_RETRIES} retries each. "
            f"Last error: {last_error}"
        )

    @staticmethod
    def _parse_retry_after(error_str: str, default: float = 15) -> float:
        """에러 메시지에서 'Please try again in N.Ns' 형태의 대기 시간 추출."""
        import re
        m = re.search(r"try again in (\d+(?:\.\d+)?)s", error_str)
        if m:
            return float(m.group(1)) + 1  # 여유 1초 추가
        return default

    def _call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        # 모델별 max_tokens 상한 적용
        model_limit = self.MODEL_MAX_TOKENS.get(model, 16_384)
        effective_max = min(max_tokens, model_limit)

        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_completion_tokens": effective_max,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        prompt_chars = len(system_prompt) + len(user_prompt)
        logger.info(
            f"[API] Calling model={model}, json_mode={json_mode}, "
            f"max_tokens={effective_max:,}, prompt_size={prompt_chars:,} chars"
        )

        t0 = time.time()
        response = self.client.chat.completions.create(**kwargs)
        elapsed = time.time() - t0

        self.current_model = model
        choice = response.choices[0]
        content = choice.message.content or ""

        # Token usage
        usage = response.usage
        usage_str = ""
        if usage:
            usage_str = (
                f"prompt_tokens={usage.prompt_tokens:,}, "
                f"completion_tokens={usage.completion_tokens:,}, "
                f"total_tokens={usage.total_tokens:,}"
            )

        logger.info(
            f"[API] Done in {elapsed:.1f}s | finish_reason={choice.finish_reason} | "
            f"response={len(content):,} chars | {usage_str}"
        )

        if not content and choice.finish_reason == "length":
            logger.warning("[API] Response truncated (content=None, finish_reason=length)")
        return content

    def parse_json_response(self, text: str) -> Optional[list]:
        """Try to extract a JSON array from the LLM response."""
        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict):
                # LLM이 에러 메시지를 반환한 경우 무시
                if "error" in data or "need_clarification" in data or "suggested_next_step" in data or "need_user_choice" in data:
                    logger.warning(f"LLM returned error/clarification response, retrying: {str(data)[:200]}")
                    return None
                # json_mode wraps array in object — find the list value
                for key in data:
                    if isinstance(data[key], list):
                        return data[key]
                # Single object → wrap in list (only if it has expected fields)
                if "담보명" in data or "상품코드" in data:
                    return [data]
                logger.warning(f"LLM returned unexpected dict: {str(data)[:200]}")
                return None
        except json.JSONDecodeError:
            pass

        # Try to find JSON array in text
        import re
        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass

        # Try to find JSON in code block
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass

        return None
