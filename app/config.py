"""Settings read once from the environment (and a local .env file, if present)."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# Generated Word documents are written here and served by GET /documents/{id}.
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# For testing the fallback: e.g. SKIP_PROVIDERS=gemini makes Groq answer.
SKIP_PROVIDERS = {p.strip() for p in os.getenv("SKIP_PROVIDERS", "").split(",") if p.strip()}
