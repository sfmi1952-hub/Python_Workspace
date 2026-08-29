"""List available models from configured OpenAI-compatible endpoint.
Reads keys from environment variables (no command-line exposure).
"""
import os
from openai import OpenAI

base = os.environ.get("GPT_OSS_API_BASE", "https://api.openai.com/v1")
key = os.environ.get("GPT_OSS_API_KEY", "")
if not key:
    raise SystemExit("GPT_OSS_API_KEY env var not set")

client = OpenAI(api_key=key, base_url=base)
models = sorted([m.id for m in client.models.list()])
print(f"Endpoint     : {base}")
print(f"Total models : {len(models)}")

oss_like = [m for m in models if "oss" in m.lower()]
print(f"\n[Models containing 'oss']")
for m in oss_like:
    print(f"  - {m}")

print(f"\n[All models (first 30)]")
for m in models[:30]:
    print(f"  - {m}")
