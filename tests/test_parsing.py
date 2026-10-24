"""Parser tests on real file formats, generated on the fly (no binary fixtures in git)."""
import io
from pathlib import Path

import pytest
from docx import Document
from fpdf import FPDF

from backend.parsing import ParseError, extract_text, split_clauses

SAMPLES = Path(__file__).resolve().parents[1] / "data" / "samples"
ARIAL = r"C:\Windows\Fonts\arial.ttf"
CLAUSES = [
    "Ev sahibi mənzili Kirayəçiyə yaşayış məqsədilə istifadəyə verir.",
    "Aylıq kirayə haqqı 500 manatdır və hər ayın 5-dək ödənilir.",
    "Depozit heç bir halda Kirayəçiyə qaytarılmır.",
    "Ev sahibi istənilən vaxt xəbərsiz mənzilə daxil ola bilər.",
]


def _docx_bytes(build) -> bytes:
    doc = Document()
    build(doc)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _pdf_bytes(lines: list[str], footer: str | None = None) -> bytes:
    class P(FPDF):
        def footer(self):
            if footer:
                self.set_y(-15)
                self.set_font("Arial", size=9)
                self.cell(0, 10, footer.format(n=self.page_no()), align="C")

    pdf = P()
    pdf.add_font("Arial", fname=ARIAL)
    pdf.set_font("Arial", size=11)
    for i, line in enumerate(lines):
        if i % 2 == 0:
            pdf.add_page()
        pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


# ---------- DOCX ----------
def test_docx_word_auto_numbering():
    def build(doc):
        doc.add_paragraph("KİRAYƏ MÜQAVİLƏSİ")
        for c in CLAUSES:
            doc.add_paragraph(c, style="List Number")  # numbers are NOT in paragraph text
        doc.add_paragraph("Tərəflərin imzaları: ________  ________")

    pre, clauses = split_clauses(extract_text("x.docx", _docx_bytes(build)))
    assert [c.text for c in clauses] == CLAUSES
    assert pre == "KİRAYƏ MÜQAVİLƏSİ"


def test_docx_sub_items_stay_inside_their_clause():
    def build(doc):
        doc.add_paragraph("Müqavilə")
        doc.add_paragraph(CLAUSES[0], style="List Number")
        doc.add_paragraph("Kirayəçi aşağıdakıları ödəyir:", style="List Number")
        doc.add_paragraph("işıq və qaz;", style="List Number 2")
        doc.add_paragraph("internet.", style="List Number 2")
        doc.add_paragraph(CLAUSES[2], style="List Number")

    _, clauses = split_clauses(extract_text("x.docx", _docx_bytes(build)))
    assert len(clauses) == 3
    assert "işıq və qaz" in clauses[1].text and "internet" in clauses[1].text


def test_docx_bullets_are_not_clauses():
    def build(doc):
        doc.add_paragraph(CLAUSES[0], style="List Number")
        doc.add_paragraph("Kirayəçinin öhdəlikləri:", style="List Number")
        doc.add_paragraph("mənzili təmiz saxlamaq;", style="List Bullet")
        doc.add_paragraph("qonşuları narahat etməmək.", style="List Bullet")
        doc.add_paragraph(CLAUSES[2], style="List Number")

    _, clauses = split_clauses(extract_text("x.docx", _docx_bytes(build)))
    assert len(clauses) == 3
    assert "qonşuları" in clauses[1].text


def test_docx_manual_numbering():
    def build(doc):
        for i, c in enumerate(CLAUSES, 1):
            doc.add_paragraph(f"{i}. {c}")

    _, clauses = split_clauses(extract_text("x.docx", _docx_bytes(build)))
    assert [c.text for c in clauses] == CLAUSES


# ---------- PDF ----------
def test_pdf_page_footers_are_removed():
    lines = [f"{i}. {c}" for i, c in enumerate(CLAUSES, 1)]
    data = _pdf_bytes(lines, footer="Səhifə {n} / 2")
    _, clauses = split_clauses(extract_text("x.pdf", data))
    assert [c.text for c in clauses] == CLAUSES  # no "Səhifə 1 / 2" glued to clause text


def test_pdf_keeps_azerbaijani_letters():
    letters = "Ə ə Ğ ğ I ı İ i Ö ö Ü ü Ç ç Ş ş"
    text = extract_text("x.pdf", _pdf_bytes([f"1. Əlifba yoxlaması: {letters}", *[f"{i}. {c}" for i, c in enumerate(CLAUSES, 2)]]))
    assert letters in text


def test_scanned_pdf_without_text_layer():
    pdf = FPDF()
    pdf.add_page()  # empty page = what a scan looks like to a text extractor
    with pytest.raises(ParseError, match="Skan"):
        extract_text("scan.pdf", bytes(pdf.output()))


def test_corrupt_file_gives_friendly_error():
    with pytest.raises(ParseError, match="zədələnmiş"):
        extract_text("broken.pdf", b"%PDF-1.4 this is not really a pdf")
    with pytest.raises(ParseError, match="zədələnmiş"):
        extract_text("broken.docx", b"PK not a zip")


# ---------- shipped samples ----------
@pytest.mark.parametrize(("name", "expected"), [
    ("kiraye_synthetic_01.txt", 13),
    ("kiraye_synthetic_02.docx", 10),
    ("kiraye_synthetic_03.pdf", 13),
])
def test_shipped_samples(name, expected):
    _, clauses = split_clauses(extract_text(name, (SAMPLES / name).read_bytes()))
    assert len(clauses) == expected
    assert not any("Səhifə" in c.text or "____" in c.text for c in clauses)
