"""The web server: serves the chat page and connects it to the ADK agent.

Routes
  GET  /            the student chat page (frontend/index.html)
  POST /api/chat    send a question to the agent, get the answer back
  POST /api/tts     optional Google Cloud Text-to-Speech (off by default)
  GET  /api/health  quick status check used by the page on load
  GET  /dev-ui/     Google ADK's built-in developer UI (shows tool calls)

Everything the standard ADK server provides (/run, /run_sse, /dev-ui, ...)
is still here; we only add a student-friendly front door on top.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from collections import OrderedDict
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel, Field

from app import school_knowledge
from app.agent import MODEL
from app.agent import app as adk_app

load_dotenv()
log = logging.getLogger("badger")

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend"

CLOUD_TTS_ENABLED = os.getenv("ENABLE_CLOUD_TTS", "false").lower() == "true"
# Cloud voices: one per language. The badger is a kid, so the defaults are
# "Puck", Google's youthful, upbeat male Chirp 3 HD voice. es-US is Latin
# American Spanish. Chirp 3 HD voices reject a pitch change, so pitch stays 0
# unless you switch to a Neural2 voice (for example en-US-Neural2-D, pitch 3).
CLOUD_TTS_VOICES = {
    "en-US": os.getenv("CLOUD_TTS_VOICE", "en-US-Chirp3-HD-Puck"),
    "es-US": os.getenv("CLOUD_TTS_VOICE_ES", "es-US-Chirp3-HD-Puck"),
}
CLOUD_TTS_PITCH = float(os.getenv("CLOUD_TTS_PITCH", "0"))        # semitones, -20..20
CLOUD_TTS_RATE = float(os.getenv("CLOUD_TTS_RATE", "1.05"))
MAX_QUESTION_CHARS = 500
MAX_TTS_CHARS = 1500

# Standard ADK FastAPI app (API routes + developer UI at /dev-ui/).
app = get_fast_api_app(
    agents_dir=str(ROOT_DIR),
    web=True,
    allow_origins=os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None,
    otel_to_cloud=os.getenv("OTEL_TO_CLOUD", "false").lower() == "true",
)
app.title = "Willkie Badger AI"
app.description = "Career Day demo chatbot for Ed Willkie Middle School."

# ADK redirects "/" to its developer UI. Students should land on the chat page
# instead, so drop that one route and serve our own page at "/".
app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/"]
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="frontend")


def asset_version() -> str:
    """Short hash of the frontend files, computed once per process.

    index.html references its stylesheet, script and mascot clips with
    ?v=<this>, so browsers fetch fresh copies after every deploy instead of
    showing a cached stylesheet with a new page.
    """
    digest = hashlib.sha256()
    for path in sorted(FRONTEND_DIR.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(FRONTEND_DIR).as_posix().encode())
            digest.update(str(path.stat().st_mtime_ns).encode())
            digest.update(str(path.stat().st_size).encode())
    return digest.hexdigest()[:10]


ASSET_VERSION = asset_version()


@app.get("/", include_in_schema=False)
async def chat_page() -> HTMLResponse:
    html = (FRONTEND_DIR / "index.html").read_text(encoding="utf-8").replace("__V__", ASSET_VERSION)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


# --------------------------------------------------------------------------
# Chat: web page -> ADK Runner -> agent -> Gemini -> answer
# --------------------------------------------------------------------------
_session_service = InMemorySessionService()
_runner: Runner | None = None


def get_runner() -> Runner:
    """One Runner for the whole process; created on first use."""
    global _runner
    if _runner is None:
        _runner = Runner(
            app=adk_app,
            session_service=_session_service,
            auto_create_session=True,
        )
    return _runner


def reset_runner() -> None:
    """Used by tests to swap the model."""
    global _runner
    _runner = None


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=MAX_QUESTION_CHARS)
    session_id: str | None = Field(default=None, max_length=64)


class Step(BaseModel):
    """One thing the agent did on the way to its answer, in student words.

    The chat page shows these under each answer ("How I answered") so students
    can see the AI open the school "library" before the Gemini "brain" writes.
    """

    icon: str
    title: str
    detail: str = ""


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    steps: list[Step] = Field(default_factory=list)


def describe_steps(events: list) -> list[Step]:
    """Turn ADK events (tool calls, tool results, final text) into plain-English steps."""
    steps: list[Step] = []
    used_library = False
    for event in events:
        if not (event.content and event.content.parts):
            continue
        for part in event.content.parts:
            if part.function_call:
                used_library = True
                question = (part.function_call.args or {}).get("question", "")
                steps.append(Step(icon="🔎", title="Opened the school library", detail=f'Looked up: "{question}"'))
            elif part.function_response:
                data = part.function_response.response or {}
                results = data.get("results") or []
                if data.get("found") and results:
                    titles = ", ".join(r.get("title", "") for r in results if r.get("title"))
                    steps.append(Step(icon="📚", title=f"Found {len(results)} matching page{'s' if len(results) != 1 else ''}", detail=titles))
                else:
                    steps.append(
                        Step(
                            icon="🤷",
                            title="Nothing on the school website about that",
                            detail="So I say 'I couldn't find it' instead of making something up.",
                        )
                    )
    if used_library:
        steps.append(Step(icon="🧠", title="Gemini wrote the answer from those pages", detail=f"Model: {MODEL}"))
    else:
        steps.append(
            Step(
                icon="🧠",
                title="Gemini answered from general knowledge",
                detail="Not a school fact, so the library was not needed.",
            )
        )
    return steps


@app.post("/api/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    session_id = req.session_id or uuid.uuid4().hex
    message = types.Content(role="user", parts=[types.Part.from_text(text=req.message.strip())])
    chunks: list[str] = []
    events: list = []
    try:
        async for event in get_runner().run_async(
            user_id="career-day-demo", session_id=session_id, new_message=message
        ):
            events.append(event)
            if event.is_final_response() and event.content and event.content.parts:
                chunks.extend(p.text for p in event.content.parts if p.text)
    except Exception as exc:  # noqa: BLE001 - any failure becomes a friendly message
        log.exception("agent call failed")
        raise HTTPException(
            status_code=502,
            detail="The AI could not answer right now. Check the API key or internet connection and try again.",
        ) from exc
    reply = "\n".join(chunks).strip() or "Hmm, I didn't get an answer that time. Please try again."
    return ChatResponse(reply=reply, session_id=session_id, steps=describe_steps(events))


# --------------------------------------------------------------------------
# Optional Google Cloud Text-to-Speech. The page falls back to the browser's
# built-in voice whenever this endpoint is disabled or fails.
# --------------------------------------------------------------------------
class TtsRequest(BaseModel):
    text: str = Field(min_length=1, max_length=MAX_TTS_CHARS)
    lang: Literal["en-US", "es-US"] = "en-US"


_tts_cache: OrderedDict[str, bytes] = OrderedDict()


_tts_client = None


def tts_client():
    """One Text-to-Speech client per process (creating one costs ~0.5 s)."""
    global _tts_client
    if _tts_client is None:
        from google.cloud import texttospeech  # imported lazily: optional dependency

        _tts_client = texttospeech.TextToSpeechClient()
    return _tts_client


def synthesize_speech(text: str, lang: str = "en-US") -> bytes:
    """Call Google Cloud Text-to-Speech and return MP3 bytes."""
    from google.cloud import texttospeech  # imported lazily: optional dependency

    voice_name = CLOUD_TTS_VOICES.get(lang, CLOUD_TTS_VOICES["en-US"])
    client = tts_client()
    response = client.synthesize_speech(
        input=texttospeech.SynthesisInput(text=text),
        voice=texttospeech.VoiceSelectionParams(language_code=voice_name[:5], name=voice_name),
        audio_config=texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            speaking_rate=CLOUD_TTS_RATE,
            **({"pitch": CLOUD_TTS_PITCH} if CLOUD_TTS_PITCH else {}),
        ),
    )
    return response.audio_content


@app.post("/api/tts")
async def tts(req: TtsRequest) -> Response:
    if not CLOUD_TTS_ENABLED:
        raise HTTPException(status_code=503, detail="Cloud Text-to-Speech is not enabled.")
    text = req.text.strip()
    key = f"{req.lang}:{text}"
    if key not in _tts_cache:
        try:
            # Off the event loop: a 3 s synthesis must not stall other students' questions.
            _tts_cache[key] = await asyncio.to_thread(synthesize_speech, text, req.lang)
        except Exception as exc:  # noqa: BLE001
            log.exception("cloud tts failed")
            raise HTTPException(status_code=503, detail="Cloud Text-to-Speech failed.") from exc
        if len(_tts_cache) > 50:
            _tts_cache.popitem(last=False)
    return Response(content=_tts_cache[key], media_type="audio/mpeg")


@app.get("/api/health")
async def health() -> dict:
    return {
        "status": "ok",
        "model": MODEL,
        "cloud_tts": CLOUD_TTS_ENABLED,
        "knowledge_pages": len(school_knowledge.load()["pages"]),
        "knowledge_source": school_knowledge.load().get("source"),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
