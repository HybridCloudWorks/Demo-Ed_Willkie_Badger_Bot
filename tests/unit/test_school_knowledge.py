"""The chatbot's 'library' must find real pages and admit when it can't."""

import json
import re

from app import school_knowledge as sk


def test_knowledge_file_loads_and_has_core_facts():
    data = sk.load()
    assert data["source"].startswith("https://ewms.emsisd.com")
    assert data["school"]["name"] == "Ed Willkie Middle School"
    assert data["school"]["mascot"] == "Badgers"
    assert len(data["pages"]) >= 20


def test_quick_facts_mentions_mascot_and_willkie_way():
    facts = sk.quick_facts()
    assert "Badgers" in facts
    assert "Willkie Way" in facts
    assert "{" not in facts and "}" not in facts  # ADK treats braces as templates


def test_willkie_way_question_finds_about_page():
    result = sk.search("What is the Willkie Way?")
    assert result["found"]
    assert any("about-us" in r["url"] for r in result["results"])
    assert "Exceptional, Wise, Mindful, and Safe" in result["results"][0]["text"]


def test_mascot_question_finds_badgers():
    result = sk.search("What is our school mascot?")
    assert result["found"]
    assert "Badgers" in result["quick_facts"]
    assert any("Badger" in r["text"] for r in result["results"])


def test_activities_question_finds_clubs_sports_or_fine_arts():
    result = sk.search("What activities can I join?")
    assert result["found"]
    urls = " ".join(r["url"] for r in result["results"])
    assert "extracurriculars" in urls


def test_unknown_school_question_is_not_found():
    result = sk.search("What is the cafeteria pizza recipe on Tuesdays?")
    assert result["found"] is False
    assert result["results"] == []
    assert "couldn't find" in result["note"]


def test_no_private_information_in_knowledge_file():
    raw = sk.KNOWLEDGE_FILE.read_text(encoding="utf-8")
    assert not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", raw), "no email addresses"
    assert not re.search(r"\b\d{6,}\b", raw), "no long ID-like numbers"
    assert "password" not in raw.lower()
    data = json.loads(raw)
    assert all(set(p) >= {"url", "title", "content"} for p in data["pages"])
