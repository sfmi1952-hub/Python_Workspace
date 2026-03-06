import json
import time
import logging
from typing import Optional

from openai import OpenAI

logger = logging.getLogger(__name__)


class OpenAICore:
    """OpenAI GPT client with model fallback and JSON mode support."""

    FALLBACK_MODELS = ["gpt-5.2", "gpt-4o", "gpt-4o-mini"]

    def __init__(self, api_key: str, model: str = "gpt-5.2"):
        self.client = OpenAI(api_key=api_key)
        self.primary_model = model
        self.current_model = model

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool = False,
        temperature: float = 0.1,
        max_tokens: int = 16384,
    ) -> str:
        """Send a chat completion request with automatic fallback on rate limits."""
        models_to_try = [self.primary_model] + [
            m for m in self.FALLBACK_MODELS if m != self.primary_model
        ]

        last_error = None
        for model in models_to_try:
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
                    logger.warning(f"Rate limit on {model}, falling back...")
                    time.sleep(2)
                    continue
                elif "500" in error_str or "503" in error_str:
                    logger.warning(f"Server error on {model}, retrying...")
                    time.sleep(3)
                    continue
                else:
                    raise

        raise RuntimeError(
            f"All models failed. Last error: {last_error}"
        )

    def _call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        json_mode: bool,
        temperature: float,
        max_tokens: int,
    ) -> str:
        kwargs = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        logger.info(f"Calling OpenAI model={model}, json_mode={json_mode}")
        response = self.client.chat.completions.create(**kwargs)
        self.current_model = model
        return response.choices[0].message.content

    def parse_json_response(self, text: str) -> Optional[list]:
        """Try to extract a JSON array from the LLM response."""
        # Try direct parse
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "data" in data:
                return data["data"]
            if isinstance(data, dict):
                # Wrap single object in list
                return [data]
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
