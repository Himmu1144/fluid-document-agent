"""Settings read once from the environment (and a local .env file, if present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
# Same idea for Gemini: each model has its own free daily quota.
GEMINI_MODELS = [m.strip() for m in os.getenv("GEMINI_MODELS", "gemini-2.5-flash,gemini-2.5-flash-lite,gemini-flash-lite-latest").split(",") if m.strip()]
# Each Groq model has its own free limit (8,000 tokens a minute), so several models are tried in turn.
GROQ_MODELS = [m.strip() for m in os.getenv("GROQ_MODELS", "openai/gpt-oss-120b,openai/gpt-oss-20b,qwen/qwen3.8-27b").split(",") if m.strip()]

# Generated Word documents are written here and served by GET /documents/{id}.
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Which provider is asked first; the rest are fallbacks, in order. Groq first: in a side-by-side it planned
# as well as Gemini, 3-5x faster, and Gemini's free tier allows only 5 requests a minute and 20 a day.
LLM_ORDER = [p.strip() for p in os.getenv("LLM_ORDER", "groq,gemini").split(",") if p.strip()]

# A model call that takes longer than this is abandoned and the next model is tried.
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "30"))

# The self-check (the agent's one improvement) can be switched off, so the eval can measure what it's worth.
SELF_CHECK = os.getenv("SELF_CHECK", "1") != "0"

# The "how this document was produced" appendix: off by default (a client-facing document shouldn't carry
# the agent's internals; the API response already has the task list and self-check).
INCLUDE_APPENDIX = os.getenv("INCLUDE_APPENDIX", "0") == "1"

# For testing the fallback: e.g. SKIP_PROVIDERS=gemini makes Groq answer.
SKIP_PROVIDERS = {p.strip() for p in os.getenv("SKIP_PROVIDERS", "").split(",") if p.strip()}
