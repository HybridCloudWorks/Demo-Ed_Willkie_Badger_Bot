"""OPTIONAL: re-download the public school pages into app/school_knowledge.json.

The repository already ships with a reviewed copy, so you do not need to run
this before Career Day. Run it only if you want fresher text, then read the
diff before committing (keep only public, institutional information).

    python scripts/refresh_school_knowledge.py

Uses only the Python standard library. Pages that fail to download keep their
previously saved content.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

KNOWLEDGE = Path(__file__).resolve().parent.parent / "app" / "school_knowledge.json"
USER_AGENT = "WillkieBadgerAI-CareerDayDemo/1.0 (public pages only)"
MAX_CHARS = 2500
SKIP_TAGS = {"script", "style", "nav", "header", "footer", "noscript", "svg", "form"}


class TextExtractor(HTMLParser):
    """Collects visible text from the <main> element (or <body> if none)."""

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self._in_main = False
        self._saw_main = False
        self.chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "main":
            self._in_main = self._saw_main = True
        if tag in SKIP_TAGS:
            self._skip += 1
        if tag in {"p", "li", "br", "h1", "h2", "h3", "h4", "tr", "div"}:
            self.chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "main":
            self._in_main = False
        if tag in SKIP_TAGS and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if self._skip or (self._saw_main and not self._in_main):
            return
        self.chunks.append(data)

    def text(self) -> str:
        raw = "".join(self.chunks)
        raw = re.sub(r"[ \t\r\f\v]+", " ", raw)
        raw = re.sub(r"\n\s*\n+", "\n", raw)
        return raw.strip()


def extract_text(html: str) -> str:
    parser = TextExtractor()
    parser.feed(html)
    return parser.text()


def strip_emails(text: str) -> str:
    """Never store email addresses, even if a page shows them."""
    return re.sub(r"[\w.+-]+@[\w-]+\.[\w.]+", "[email removed]", text)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed https host
        return resp.read().decode("utf-8", errors="replace")


def main() -> int:
    data = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    updated = failed = 0
    for page in data["pages"]:
        url = page["url"]
        try:
            text = strip_emails(extract_text(fetch(url)))[:MAX_CHARS]
        except Exception as exc:  # noqa: BLE001
            print(f"skip  {url}  ({exc})")
            failed += 1
            continue
        if text and text != page["content"]:
            page["content"] = text
            updated += 1
            print(f"update {url}")
        else:
            print(f"same   {url}")
    KNOWLEDGE.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{updated} page(s) updated, {failed} failed. Review the diff before committing.")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
