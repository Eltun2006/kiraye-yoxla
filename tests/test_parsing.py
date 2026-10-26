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


# ---------- Multi-level numbering (1. heading → 1.1. points), common in real contracts ----------
MULTILEVEL = """YAŞAYIŞ SAHƏSİNİN KİRAYƏSİ MÜQAVİLƏSİ
Bakı şəhəri                                   01.09.2026

1. MÜQAVİLƏNİN PREDMETİ
1.1. Ev sahibi mənzili Kirayəçiyə yaşayış məqsədilə istifadəyə verir.
1.2 Mənzilin ünvanı: Bakı şəhəri, Nəsimi rayonu.
2. ÖDƏNİŞ ŞƏRTLƏRİ
2.1. Aylıq kirayə haqqı 500 manatdır.
2.2. Kirayəçi aşağıdakıları ödəyir:
2.2.1. elektrik enerjisi;
2.2.2. internet.
2.3. Depozit heç bir halda qaytarılmır.
3. Müqavilə iki nüsxədə tərtib edilir.
Tərəflərin imzaları: ________  ________
"""


def test_multilevel_points_are_clauses_and_headings_are_dropped():
    pre, clauses = split_clauses(MULTILEVEL)
    assert [c.label for c in clauses] == ["1.1", "1.2", "2.1", "2.2", "2.3", "3"]
    assert [c.idx for c in clauses] == [1, 2, 3, 4, 5, 6]  # positions stay 1..n for the LLM and the database
    by = {c.label: c.text for c in clauses}
    assert by["1.2"] == "Mənzilin ünvanı: Bakı şəhəri, Nəsimi rayonu."  # heading "2. ÖDƏNİŞ" not glued on
    assert by["2.2"] == "Kirayəçi aşağıdakıları ödəyir: 2.2.1. elektrik enerjisi; 2.2.2. internet."
    assert by["3"] == "Müqavilə iki nüsxədə tərtib edilir."  # numbered clause without sub-points; no signatures
    assert pre.startswith("YAŞAYIŞ SAHƏSİNİN")


def test_flat_contracts_keep_their_numbers_as_labels():
    _, clauses = split_clauses("\n".join(f"{i}. {c}" for i, c in enumerate(CLAUSES, start=1)))
    assert [c.label for c in clauses] == ["1", "2", "3", "4"]


def _multilevel_numbering(doc) -> int:
    """Add a Word multi-level list ("1." / "1.1.") to the document's numbering part; returns its numId."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    numbering = doc.part.numbering_part.element
    lvls = "".join(
        f'<w:lvl w:ilvl="{i}"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="{t}"/></w:lvl>'
        for i, t in enumerate(["%1.", "%1.%2."])
    )
    numbering.append(parse_xml(f'<w:abstractNum {nsdecls("w")} w:abstractNumId="90">{lvls}</w:abstractNum>'))
    numbering.append(parse_xml(f'<w:num {nsdecls("w")} w:numId="90"><w:abstractNumId w:val="90"/></w:num>'))
    return 90


def test_docx_multilevel_list_becomes_points():
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    def build(doc):
        doc.add_paragraph("x", style="List Number")  # makes sure the numbering part exists
        doc.paragraphs[0]._p.getparent().remove(doc.paragraphs[0]._p)
        num_id = _multilevel_numbering(doc)
        for level, text in [(0, "PREDMET"), (1, CLAUSES[0]), (1, CLAUSES[1]), (0, "ÖHDƏLİKLƏR"),
                            (1, CLAUSES[2]), (1, CLAUSES[3])]:
            p = doc.add_paragraph(text)
            p._p.get_or_add_pPr().append(parse_xml(
                f'<w:numPr {nsdecls("w")}><w:ilvl w:val="{level}"/><w:numId w:val="{num_id}"/></w:numPr>'))

    _, clauses = split_clauses(extract_text("x.docx", _docx_bytes(build)))
    assert [(c.label, c.text) for c in clauses] == [
        ("1.1", CLAUSES[0]), ("1.2", CLAUSES[1]), ("2.1", CLAUSES[2]), ("2.2", CLAUSES[3])]
