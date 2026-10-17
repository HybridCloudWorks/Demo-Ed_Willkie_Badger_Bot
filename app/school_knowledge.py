"""The chatbot's "library": a saved copy of public Ed Willkie Middle School pages.

The pages in school_knowledge.json were collected from https://ewms.emsisd.com/
(see scripts/refresh_school_knowledge.py). Keeping them in the repo means the
Career Day demo works even if the school website is slow or offline.

Only public, institutional information is stored here. No student information.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

KNOWLEDGE_FILE = Path(__file__).with_name("school_knowledge.json")

# Words that are too common to help find the right page.
_STOP_WORDS = {
    "a", "an", "and", "are", "at", "be", "can", "do", "does", "for", "from",
    "have", "how", "i", "in", "is", "it", "me", "my", "of", "on", "or", "our",
    "school", "tell", "that", "the", "there", "this", "to", "us", "we", "what",
    "when", "where", "which", "who", "why", "willkie", "ed", "middle", "ewms",
    "about", "any", "with", "you", "your", "get", "join", "like", "some",
}

# Everyday student words -> words that actually appear on the website.
_SYNONYMS = {
    "mascot": ["badger", "badgers"],
    "mascots": ["badger", "badgers"],
    "badger": ["mascot"],
    "activities": ["clubs", "athletics", "fine arts", "extracurriculars"],
    "activity": ["clubs", "athletics", "fine arts", "extracurriculars"],
    "sports": ["athletics"],
    "sport": ["athletics"],
    "teams": ["athletics"],
    "club": ["clubs"],
    "music": ["band", "choir"],
    "art": ["visual arts"],
    "drama": ["theatre"],
    "principal": ["administration"],
    "hours": ["bell schedule"],
    "time": ["bell schedule"],
    "start": ["bell schedule"],
    "end": ["bell schedule"],
    "lunch": ["bell schedule"],
    "phone": ["contact"],
    "address": ["contact"],
    "located": ["contact", "address"],
    "motto": ["willkie way"],
    "values": ["willkie way"],
    "way": ["willkie way"],
    "named": ["namesake"],
    "history": ["namesake"],
    "colors": ["mascot"],
    "mission": ["mission"],
    "reading": ["library", "english"],
    "books": ["library"],
    "math": ["mathematics"],
    "counselor": ["counseling"],
    "military": ["military families"],
}


@lru_cache(maxsize=1)
def load() -> dict[str, Any]:
    """Load the saved school pages once and keep them in memory."""
    with KNOWLEDGE_FILE.open(encoding="utf-8") as f:
        return json.load(f)


def quick_facts() -> str:
    """A few always-true facts, written as plain text for the AI's instructions."""
    s = load()["school"]
    lines = [
        f"School name: {s.get('name')}",
        f"Mascot: {s.get('mascot')}",
        f"Grades: {s.get('grades')}",
        f"District: {s.get('district')}",
        f"Address: {s.get('address')}",
        f"Main office phone: {s.get('phone')}",
        f"Mission: {s.get('mission')}",
        f"Motto and values: {s.get('motto_or_values')}",
        f"Website: {load().get('source')}",
    ]
    return "\n".join(line for line in lines if not line.endswith("None"))


def _terms(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9']+", text.lower())
    terms = [w for w in words if w not in _STOP_WORDS and len(w) > 1]
    expanded = list(terms)
    for w in terms:
        expanded.extend(_SYNONYMS.get(w, []))
    return expanded


def _score(page: dict[str, Any], terms: list[str]) -> int:
    title = page.get("title", "").lower()
    topics = " ".join(page.get("topics", [])).lower()
    content = page.get("content", "").lower()
    score = 0
    for t in set(terms):
        if t in topics:
            score += 4
        if t in title:
            score += 3
        score += min(content.count(t), 3)
    return score


def _snippet(content: str, terms: list[str], width: int = 1400) -> str:
    if len(content) <= width:
        return content
    low = content.lower()
    first = min((low.find(t) for t in terms if low.find(t) >= 0), default=0)
    start = max(0, first - width // 4)
    piece = content[start : start + width]
    return ("..." if start else "") + piece + ("..." if start + width < len(content) else "")


def search(question: str, limit: int = 3) -> dict[str, Any]:
    """Find the saved school pages that best match a question.

    Returns a dict with:
      found        - True if at least one page matched the question
      quick_facts  - always-available basic facts about the school
      results      - up to `limit` matching pages: title, url, text
      note         - what the AI should do if the answer is not in the results
    """
    terms = _terms(question)
    scored = [(_score(p, terms), p) for p in load()["pages"]]
    scored.sort(key=lambda item: item[0], reverse=True)
    hits = [(s, p) for s, p in scored if s >= 3][:limit]
    return {
        "found": bool(hits),
        "source": load().get("source"),
        "quick_facts": quick_facts(),
        "results": [
            {"title": p["title"], "url": p["url"], "text": _snippet(p["content"], terms)}
            for _, p in hits
        ],
        "note": (
            "Only use facts that appear above. If the specific answer is not "
            "here, say you couldn't find it on the Ed Willkie Middle School website."
        ),
    }
