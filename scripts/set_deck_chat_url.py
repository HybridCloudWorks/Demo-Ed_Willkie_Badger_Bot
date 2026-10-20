"""Put the chatbot's web address (and a matching QR code) into the Career Day deck.

The deck in docs/ ships with a placeholder address. After you deploy to Cloud Run
(or decide to show the laptop URL), run this once and the URL text and the QR
codes on the demo slide and the closing slide are replaced in place:

    python scripts/set_deck_chat_url.py https://willkie-badger-ai-xxxxx-uc.a.run.app
    python scripts/set_deck_chat_url.py https://willkie-badger-ai-xxxxx-uc.a.run.app docs/Career_Day_2026_EWMS.pptx

Requires `pip install -e ".[dev]"` (for the tiny pure-Python `segno` QR library).

How it finds the spots: every text box whose shape name starts with "ChatUrl"
gets the new address, and every picture whose shape name starts with "ChatQr"
gets a freshly generated QR code. Nothing else in the deck is touched.
"""

from __future__ import annotations

import io
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

DEFAULT_DECK = Path(__file__).resolve().parent.parent / "docs" / "Career_Day_2026_EWMS.pptx"
PLACEHOLDER_URL = "https://YOUR-CLOUD-RUN-URL.a.run.app"


def display_text(url: str) -> str:
    """What students read on the slide: the address without the scheme."""
    return re.sub(r"^https?://", "", url.strip()).rstrip("/")


def qr_png(url: str) -> bytes:
    import segno  # imported here so the rest of the app never needs it

    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="png", scale=12, border=2, dark="161616", light="ffffff")
    return buf.getvalue()


def _shape_blocks(xml: str, tag: str, name_prefix: str):
    """Yield (match) for every <p:sp>/<p:pic> whose cNvPr name starts with the prefix."""
    pattern = re.compile(rf"<p:{tag}>.*?</p:{tag}>", re.S)
    for m in pattern.finditer(xml):
        name = re.search(r'<p:cNvPr id="\d+" name="([^"]*)"', m.group(0))
        if name and name.group(1).startswith(name_prefix):
            yield m


def apply_chat_url(unpacked: Path, url: str) -> int:
    """Rewrite ChatUrl text boxes and ChatQr pictures inside an unpacked deck. Returns spots changed."""
    changed = 0
    png = qr_png(url)
    text = escape(display_text(url))
    for slide in sorted((unpacked / "ppt" / "slides").glob("slide*.xml")):
        xml = slide.read_text(encoding="utf-8")
        original = xml
        for m in list(_shape_blocks(xml, "sp", "ChatUrl")):
            block = m.group(0)
            new_block = re.sub(r"<a:t>[^<]*</a:t>", f"<a:t>{text}</a:t>", block, count=1)
            xml = xml.replace(block, new_block)
            changed += 1
        rels_path = slide.parent / "_rels" / f"{slide.name}.rels"
        rels = rels_path.read_text(encoding="utf-8") if rels_path.exists() else ""
        for m in _shape_blocks(xml, "pic", "ChatQr"):
            rid = re.search(r'r:embed="([^"]+)"', m.group(0))
            target = rid and re.search(rf'Id="{rid.group(1)}"[^>]*Target="([^"]+)"', rels)
            if target:
                media = (slide.parent / target.group(1)).resolve()
                media.write_bytes(png)
                changed += 1
        if xml != original:
            slide.write_text(xml, encoding="utf-8")
    return changed


def main(argv: list[str]) -> int:
    if len(argv) < 2 or not argv[1].startswith("http"):
        print(__doc__)
        return 2
    url = argv[1]
    deck = Path(argv[2]) if len(argv) > 2 else DEFAULT_DECK
    if not deck.exists():
        print(f"Deck not found: {deck}")
        return 1
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "deck"
        with zipfile.ZipFile(deck) as z:
            z.extractall(work)
        changed = apply_chat_url(work, url)
        out = Path(tmp) / "out.pptx"
        with zipfile.ZipFile(deck) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in src.infolist():  # keep the original part order
                if info.is_dir():
                    continue
                dst.writestr(info, (work / info.filename).read_bytes())
        shutil.copyfile(out, deck)
    print(f"Updated {changed} spot(s) in {deck} with {url}")
    return 0 if changed else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
