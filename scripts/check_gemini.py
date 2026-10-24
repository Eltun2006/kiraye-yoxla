"""Check the Gemini key and list models you can use for generateContent.

Usage:  python scripts/check_gemini.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google import genai  # noqa: E402

from backend.config import settings  # noqa: E402

if not settings.gemini_api_key:
    sys.exit("GEMINI_API_KEY .env faylında boşdur.")

client = genai.Client(api_key=settings.gemini_api_key)
names = [
    m.name.removeprefix("models/")
    for m in client.models.list()
    if "generateContent" in (m.supported_actions or []) and "gemini" in m.name
]
print("Açar işləyir ✓  İstifadə edilə bilən Gemini modelləri:")
for n in sorted(names):
    print(("  → " if n == settings.gemini_model else "    ") + n)
if settings.gemini_model not in names:
    print(f"\n⚠️ GEMINI_MODEL={settings.gemini_model} siyahıda yoxdur — yuxarıdakılardan birini .env-ə yazın.")
