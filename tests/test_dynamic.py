"""Offline tests for the dynamic (JS-rendered) layer.

No browser, no network: the parse logic is a pure static method fed a saved HTML
snippet, mirroring tests/test_knockout.py. This is what keeps the JS-rendered
source unit-testable in CI without launching Chrome.
"""
from src.scraper.dynamic_render import DynamicRenderScraper
from src.validator import validate_quote

# Markup as it looks AFTER the page's JavaScript has built the .quote blocks
# (they don't exist in the raw HTML response).
RENDERED_HTML = """
<div class="container">
  <div class="quote">
    <span class="text">"The world as we have created it is a process of our thinking."</span>
    <span>by <small class="author">Albert Einstein</small></span>
    <div class="tags"><a class="tag">change</a><a class="tag">deep-thoughts</a></div>
  </div>
  <div class="quote">
    <span class="text">"It is our choices that show what we truly are."</span>
    <span>by <small class="author">J.K. Rowling</small></span>
    <div class="tags"><a class="tag">abilities</a></div>
  </div>
</div>
"""


def test_parse_extracts_js_rendered_records():
    rows = DynamicRenderScraper._parse_quotes(RENDERED_HTML)
    assert len(rows) == 2
    assert rows[0]["author"] == "Albert Einstein"
    assert rows[0]["tags"] == "change, deep-thoughts"
    assert rows[1]["quote"].startswith('"It is our choices')
    assert rows[1]["tags"] == "abilities"


def test_parse_skips_incomplete_blocks():
    html = '<div class="quote"><span class="text">no author here</span></div>'
    assert DynamicRenderScraper._parse_quotes(html) == []


def test_parse_empty_when_no_rendered_content():
    # Mimics the raw (un-rendered) HTML: no .quote blocks exist yet.
    assert DynamicRenderScraper._parse_quotes("<html><body>loading...</body></html>") == []


def test_validate_quote_trims_and_flags():
    cleaned, errors = validate_quote({"quote": "  hello  ", "author": "", "tags": " a "})
    assert cleaned["quote"] == "hello"      # trimmed
    assert cleaned["author"] is None        # blank -> None
    assert cleaned["tags"] == "a"
    assert any("author" in e for e in errors)
