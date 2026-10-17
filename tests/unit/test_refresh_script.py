"""The optional refresh script keeps only visible text and strips emails."""

import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "refresh", Path(__file__).resolve().parents[2] / "scripts" / "refresh_school_knowledge.py"
)
refresh = importlib.util.module_from_spec(spec)
spec.loader.exec_module(refresh)

SAMPLE = """
<html><head><title>x</title><style>p{}</style><script>var a=1;</script></head>
<body><nav><a href="/">Menu item</a></nav>
<main><h1>About Us</h1><p>Home of the <b>Badgers</b>.</p>
<ul><li>Band</li><li>Choir</li></ul><p>Email coach@example.com for info.</p></main>
<footer>Footer junk</footer></body></html>
"""


def test_extract_text_keeps_main_content_only():
    text = refresh.extract_text(SAMPLE)
    assert "About Us" in text and "Badgers" in text and "Band" in text
    assert "Menu item" not in text and "Footer junk" not in text and "var a" not in text


def test_strip_emails():
    assert "@" not in refresh.strip_emails(refresh.extract_text(SAMPLE))
