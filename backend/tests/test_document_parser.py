"""Unit tests for the checker-specific document parser (ADR-0019)."""
import pymupdf
import pytest

from services.document_parser import ParseLimitExceeded, parse_document

BODY = [
    "Deep learning has transformed natural language processing across many tasks and domains.",
    "Figure 1 shows the pipeline.",   # 5 words: short, but a real passage — must be kept
    "The transformer architecture relies entirely on self-attention mechanisms to draw global "
    "dependencies between input and output sequences.",
]


def _pdf(pages: int = 3, *, header: bool = True, references: bool = True, hyphen: bool = False) -> bytes:
    doc = pymupdf.open()
    for pno in range(1, pages + 1):
        page = doc.new_page()
        y = 72
        if header:
            page.insert_textbox(pymupdf.Rect(72, 30, 540, 50), "Running Title — Journal of Examples 2026", fontsize=9)
        # Body text differs per page (as real prose does); only header/footer repeat.
        tag = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"][pno - 1]
        for para in BODY:
            page.insert_textbox(pymupdf.Rect(72, y, 540, y + 60), f"{tag} section. {para}", fontsize=10)
            y += 70
        if hyphen and pno == 1:
            page.insert_textbox(pymupdf.Rect(72, y, 540, y + 40), "A trans-\nformer reads the whole pair jointly.", fontsize=10)
            y += 50
        if references and pno == pages:
            page.insert_textbox(pymupdf.Rect(72, y, 540, y + 20), "References", fontsize=11)
            y += 30
            for i in range(1, 4):
                page.insert_textbox(pymupdf.Rect(72, y, 540, y + 30),
                                    f"[{i}] Author {i}. A paper title. Journal, 202{i}.", fontsize=9)
                y += 32
        page.insert_textbox(pymupdf.Rect(72, 780, 540, 800), str(pno), fontsize=9)
    return doc.tobytes()


# ── Plain text ────────────────────────────────────────────────────────────────

def test_plaintext_paragraphs_keep_offsets():
    raw = b"First paragraph here.\r\n\r\nSecond one.\n\n\n  Third, indented.  "
    d = parse_document("a.txt", raw)
    assert d.method == "text" and d.page_count is None
    assert [p["text"] for p in d.paragraphs] == ["First paragraph here.", "Second one.", "Third, indented."]
    for p in d.paragraphs:
        assert d.text[p["start"]:p["end"]] == p["text"]


def test_plaintext_bad_utf8_is_tolerated():
    d = parse_document("a.txt", b"caf\xe9 au lait\n\nmore")
    assert len(d.paragraphs) == 2


# ── PDF ───────────────────────────────────────────────────────────────────────

def test_pdf_keeps_short_paragraphs_and_maps_pages():
    d = parse_document("p.pdf", _pdf(pages=3))
    assert d.method == "pdf" and d.page_count == 3
    texts = [p["text"] for p in d.paragraphs]
    assert any("Figure 1 shows the pipeline" in t for t in texts), "short paragraphs must be kept"
    assert {p["page"] for p in d.paragraphs} == {1, 2, 3}
    for p in d.paragraphs:
        assert d.text[p["start"]:p["end"]] == p["text"]


def test_pdf_drops_running_headers_and_page_numbers():
    d = parse_document("p.pdf", _pdf(pages=4))
    texts = [p["text"] for p in d.paragraphs]
    assert not any("Running Title" in t for t in texts)
    assert not any(t.strip().isdigit() for t in texts)


def test_pdf_excludes_reference_list_and_reports_it():
    d = parse_document("p.pdf", _pdf(pages=3, references=True))
    texts = " ".join(p["text"] for p in d.paragraphs)
    assert "[1] Author 1" not in texts
    assert d.excluded_reference_paragraphs == 3
    assert any("reference list" in w.lower() for w in d.warnings)


def test_pdf_without_reference_list_is_untouched():
    d = parse_document("p.pdf", _pdf(pages=2, references=False))
    assert d.excluded_reference_paragraphs == 0
    assert d.warnings == []


def test_pdf_rejoins_hyphenated_line_breaks():
    d = parse_document("p.pdf", _pdf(pages=1, hyphen=True, references=False))
    assert any("A transformer reads the whole pair jointly." in p["text"] for p in d.paragraphs)


def test_pdf_page_cap_is_enforced():
    with pytest.raises(ParseLimitExceeded) as exc:
        parse_document("p.pdf", _pdf(pages=4), max_pdf_pages=3)
    assert "4 pages" in str(exc.value)


def test_char_cap_is_enforced():
    with pytest.raises(ParseLimitExceeded):
        parse_document("a.txt", b"word " * 1000, max_chars=100)


def test_corrupt_pdf_yields_empty_document_with_warning():
    d = parse_document("broken.pdf", b"%PDF-1.7 garbage garbage")
    assert d.text == "" and d.paragraphs == []
    assert d.warnings and ("could not be opened" in d.warnings[0] or "No text" in d.warnings[0])


def test_pdf_magic_beats_extension():
    d = parse_document("mislabelled.txt", _pdf(pages=1, references=False))
    assert d.method == "pdf"
