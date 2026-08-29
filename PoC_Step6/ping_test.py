"""Quick API connectivity check before full PoC run."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print(" API connectivity ping test")
print("=" * 60)

# Claude
print("\n[1] Claude Opus 4.7")
try:
    from logic.claude_core import ClaudeCore
    c = ClaudeCore()
    r = c.generate('ping. reply with single word: OK', max_tokens=500)
    print(f"  model    : {r['model']}")
    print(f"  response : {r['text'].strip()[:100]}")
    print(f"  tokens   : in={r['input_tokens']}, out={r['output_tokens']}")
    print("  STATUS   : " + ("OK" if r['text'].strip() else "EMPTY RESPONSE"))
except Exception as e:
    print(f"  STATUS   : FAIL - {e}")

# GPT-OSS
print("\n[2] GPT-OSS 120b (reasoning model)")
try:
    from logic.gpt_oss_core import GPTOSSCore
    g = GPTOSSCore()
    r = g.generate('ping. reply with single word: OK', max_tokens=500)
    print(f"  model    : {r['model']}")
    print(f"  response : {r['text'].strip()[:100]}")
    print(f"  tokens   : in={r['input_tokens']}, out={r['output_tokens']}, reasoning={r.get('reasoning_tokens', 0)}")
    print(f"  finish   : {r.get('finish_reason', '?')}")
    print("  STATUS   : " + ("OK" if r['text'].strip() else "EMPTY RESPONSE"))
except Exception as e:
    print(f"  STATUS   : FAIL - {e}")

print("\n" + "=" * 60)
