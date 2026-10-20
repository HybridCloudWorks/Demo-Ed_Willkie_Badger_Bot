"""The web page, chat endpoint, and voice fallbacks work without any API key."""

import pytest
from fastapi.testclient import TestClient

from app import fast_api_app as web
from app.agent import root_agent


@pytest.fixture
def client(scripted_llm, monkeypatch):
    monkeypatch.setattr(root_agent, "model", scripted_llm)
    web.reset_runner()
    with TestClient(web.app) as c:
        yield c
    web.reset_runner()


def test_chat_page_is_served_at_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Willkie Badger AI" in r.text
    assert "Read Aloud" in client.get("/static/app.js").text
    assert client.get("/static/style.css").status_code == 200


def test_health_reports_model_and_library(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok"
    assert h["knowledge_pages"] >= 20
    assert h["cloud_tts"] is False


def test_chat_endpoint_round_trip(client):
    r = client.post("/api/chat", json={"message": "What is the Willkie Way?"})
    assert r.status_code == 200
    body = r.json()
    assert body["reply"].startswith("Found it.")
    assert body["session_id"]
    # Same session can be reused for a follow-up.
    r2 = client.post("/api/chat", json={"message": "What is our mascot?", "session_id": body["session_id"]})
    assert r2.status_code == 200 and r2.json()["session_id"] == body["session_id"]


def test_chat_explains_its_steps_for_a_school_question(client):
    body = client.post("/api/chat", json={"message": "What is our mascot?"}).json()
    titles = [s["title"] for s in body["steps"]]
    assert titles[0] == "Opened the school library"
    assert titles[1].startswith("Found ")
    assert "Gemini wrote the answer" in titles[-1]
    assert all({"icon", "title", "detail"} <= set(s) for s in body["steps"])


def test_chat_explains_the_not_found_step(client):
    body = client.post("/api/chat", json={"message": "What is the cafeteria pizza recipe on Tuesdays?"}).json()
    assert "couldn't find" in body["reply"]
    assert any(s["icon"] == "🤷" for s in body["steps"])


def test_chat_page_has_demo_chips_and_welcome_panel(client):
    page = client.get("/").text
    assert "Badger Bridge" in page
    assert "mascota" in page


def test_mascot_clips_are_served(client):
    page = client.get("/").text
    assert "__V__" not in page                      # version placeholder was filled in
    assert "/static/app.js?v=" in page and "/static/style.css?v=" in page
    assert 'data-v="' in page
    video = client.get("/static/mascot/wave.mp4")
    assert video.status_code == 200 and video.headers["content-type"].startswith("video/mp4")
    assert len(video.content) < 2_000_000  # keep the page quick on school Wi-Fi
    assert client.get("/static/mascot/wave.jpg").status_code == 200


def test_chat_page_has_mascot_stage_and_how_i_work(client):
    page = client.get("/").text
    assert 'id="stage"' in page and 'id="mascot-caption"' in page
    assert "How I work" in page


def test_chat_rejects_empty_or_huge_messages(client):
    assert client.post("/api/chat", json={"message": ""}).status_code == 422
    assert client.post("/api/chat", json={"message": "x" * 501}).status_code == 422


def test_chat_survives_model_failure(client, monkeypatch):
    async def boom(*_, **__):
        raise RuntimeError("no internet")
        yield  # pragma: no cover - makes this an async generator

    monkeypatch.setattr(web.get_runner(), "run_async", boom)
    r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 502
    assert "try again" in r.json()["detail"].lower()


def test_read_aloud_endpoint_fails_softly_when_disabled(client):
    # Cloud TTS is off by default: the page falls back to the browser voice.
    r = client.post("/api/tts", json={"text": "Hello Badgers"})
    assert r.status_code == 503
    # Chat keeps working regardless of the voice feature.
    assert client.post("/api/chat", json={"message": "What is our mascot?"}).status_code == 200


def test_read_aloud_endpoint_fails_softly_when_cloud_call_breaks(client, monkeypatch):
    monkeypatch.setattr(web, "CLOUD_TTS_ENABLED", True)
    monkeypatch.setattr(web, "synthesize_speech", lambda text: (_ for _ in ()).throw(RuntimeError("no creds")))
    assert client.post("/api/tts", json={"text": "Hello Badgers"}).status_code == 503


def test_read_aloud_endpoint_returns_audio_when_cloud_works(client, monkeypatch):
    monkeypatch.setattr(web, "CLOUD_TTS_ENABLED", True)
    monkeypatch.setattr(web, "synthesize_speech", lambda text: b"ID3fake-mp3")
    r = client.post("/api/tts", json={"text": "Go Badgers"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert r.content == b"ID3fake-mp3"


def test_adk_developer_ui_is_still_available(client):
    r = client.get("/dev-ui/", follow_redirects=False)
    assert r.status_code == 200
