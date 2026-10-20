"""Run the Career Day questions through the real agent and print the answers.

Usage (needs a Gemini API key or Vertex AI credentials in .env):
    python scripts/career_day_check.py

Each answer is printed with a simple PASS / CHECK flag so you can read through
the output in under a minute before the presentation.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402
from google.adk.runners import Runner  # noqa: E402
from google.adk.sessions import InMemorySessionService  # noqa: E402
from google.genai import types  # noqa: E402

from app.agent import app as adk_app  # noqa: E402

# (question, words that must appear, words that must NOT appear)
SCENARIOS = [
    ("What is the Willkie Way?", ["exceptional", "wise", "mindful", "safe"], []),
    ("What is our school mascot?", ["badger"], []),
    ("What activities can I join?", ["club", "band", "choir", "athletic", "sport"], []),
    ("What does a Cloud Architect do?", [], []),
    ("How does this chatbot work?", [], []),
    # Not on the website -> the bot must say it couldn't find it, not invent an answer.
    ("Who won the 7th grade spelling bee last year?", ["couldn't find", "could not find"], []),
    # The slide-deck "Badger Test": the bridge does not exist. The library still returns
    # mascot/namesake pages, so this checks Gemini does not stitch a story together from them.
    (
        "Tell me about the famous Badger Bridge at Ed Willkie Middle School, built in 1901.",
        ["couldn't find", "could not find"],
        ["was built in 1901", "the bridge was", "historic bridge"],
    ),
    # Students may ask in Spanish; the bot should answer in Spanish.
    ("¿Cuál es la mascota de la escuela?", ["tejón", "badger"], []),
]


def configured() -> bool:
    return bool(os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")) or (
        os.getenv("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true"
        and os.getenv("GOOGLE_CLOUD_PROJECT")
    )


async def ask(runner: Runner, question: str) -> str:
    msg = types.Content(role="user", parts=[types.Part.from_text(text=question)])
    texts: list[str] = []
    async for ev in runner.run_async(user_id="check", session_id="career-day", new_message=msg):
        if ev.is_final_response() and ev.content:
            texts += [p.text for p in ev.content.parts if p.text]
    return "\n".join(texts).strip()


async def main() -> int:
    load_dotenv()
    if not configured():
        print("No Gemini credentials found. Copy .env.example to .env and set GEMINI_API_KEY (or Vertex AI).")
        return 2
    runner = Runner(app=adk_app, session_service=InMemorySessionService(), auto_create_session=True)
    failures = 0
    for question, must_have, must_not in SCENARIOS:
        print("=" * 72)
        print("STUDENT:", question)
        try:
            answer = await ask(runner, question)
        except Exception as exc:  # noqa: BLE001
            print("ERROR:", exc)
            failures += 1
            continue
        print("BADGER AI:", answer)
        low = answer.lower()
        ok = (not must_have or any(w in low for w in must_have)) and not any(w in low for w in must_not)
        sentences = max(1, answer.count(". ") + answer.count("! ") + 1)
        if sentences > 8:
            ok = False
            print("note: answer looks long for middle schoolers")
        print("RESULT:", "PASS" if ok else "CHECK (read the answer above)")
        failures += 0 if ok else 1
    print("=" * 72)
    print("All scenarios passed." if failures == 0 else f"{failures} scenario(s) need a look.")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
