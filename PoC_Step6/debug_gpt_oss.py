"""Debug Groq gpt-oss-120b response structure (reasoning model handling)."""
import os, json
from openai import OpenAI

c = OpenAI(api_key=os.environ["GPT_OSS_API_KEY"], base_url=os.environ["GPT_OSS_API_BASE"])

resp = c.chat.completions.create(
    model=os.environ["GPT_OSS_MODEL"],
    messages=[
        {"role": "system", "content": "You are a helpful assistant. Reply with JSON only."},
        {"role": "user", "content": 'reply with JSON: {"answer": "OK"}'},
    ],
    max_tokens=500,
    temperature=0.0,
)

print("=== Full response (model_dump) ===")
print(json.dumps(resp.model_dump(), indent=2, default=str)[:3000])
