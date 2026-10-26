"""File -> plain text -> numbered clauses. No AI here: deterministic is cheaper and testable."""
import io
import re
from dataclasses import dataclass

from docx import Document
from docx.text.paragraph import Paragraph
from pypdf import PdfReader


class ParseError(ValueError):
    """Raised with a user-facing (Azerbaijani) message."""


# Page headers/footers that PDF extraction glues into the text: "Səhifə 1 / 2", "Page 3 of 5", "- 4 -", "7".
_PAGE_MARK = re.compile(
    r"^\s*(?:(?:Səhifə|Səh\.?|Page|Стр\.?|Страница)\s*\d{1,3}(?:\s*(?:/|of|из)\s*\d{1,3})?|[-–]?\s*\d{1,3}\s*[-–]?)\s*$",
    re.IGNORECASE,
)


def _strip_page_marks(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not _PAGE_MARK.match(line))


_STYLE_LEVEL = re.compile(r"^List (?:Number|Bullet|Paragraph)\s+(\d)$")


def _list_info(p: Paragraph, numbering) -> tuple[int, str, bool] | None:
    """(level, number format, multi-level) if Word renders this paragraph as a list item, else None.
    Format is "decimal", "bullet", "lowerLetter"...; multi-level means Word shows the parent's number too ("2.1.").

    Numbering lives on the paragraph or on its style (e.g. "List Number"), and the number itself
    is never part of paragraph.text — so we read numPr and resolve it in numbering.xml.
    """
    num_pr, sources, style = None, [p._p.pPr], p.style
    while style is not None:  # walk the style inheritance chain
        sources.append(style.element.pPr)
        style = style.base_style
    for pPr in sources:
        if pPr is not None and pPr.numPr is not None:
            num_pr = pPr.numPr
            break
    if num_pr is None or num_pr.numId is None or num_pr.numId.val == 0:  # numId 0 = "numbering removed"
        return None

    level = int(num_pr.ilvl.val) if num_pr.ilvl is not None else None
    num_fmt, multi = "decimal", False
    if numbering is not None:
        abs_ids = numbering.xpath(f'./w:num[@w:numId="{num_pr.numId.val}"]/w:abstractNumId/@w:val')
        if abs_ids:
            abstract = f'./w:abstractNum[@w:abstractNumId="{abs_ids[0]}"]'
            if level is None and p.style is not None:  # level linked through the style
                linked = numbering.xpath(f'{abstract}/w:lvl[w:pStyle/@w:val="{p.style.style_id}"]/@w:ilvl')
                level = int(linked[0]) if linked else None
            fmt = numbering.xpath(f'{abstract}/w:lvl[@w:ilvl="{level or 0}"]/w:numFmt/@w:val')
            num_fmt = fmt[0] if fmt else num_fmt
            text = numbering.xpath(f'{abstract}/w:lvl[@w:ilvl="{level or 0}"]/w:lvlText/@w:val')
            multi = bool(level) and bool(text) and "%1" in text[0] and f"%{level + 1}" in text[0]
    # Built-in "List Number 2" etc. are often separate level-0 lists; their name tells the real depth.
    m = _STYLE_LEVEL.match(p.style.name if p.style is not None else "")
    if m:
        level = max(level or 0, int(m.group(1)) - 1)
    return (level or 0), num_fmt, multi


def _docx_text(data: bytes) -> str:
    """Rebuild visible numbering: top-level numbered items become '1. ...'; second-level items that Word itself
    shows as '1.1.' (multi-level list) become '1.1. ...'; bullets, '1)'-style sub-lists and deeper items stay
    inside their clause."""
    doc = Document(io.BytesIO(data))
    try:
        numbering = doc.part.numbering_part.element
    except (KeyError, NotImplementedError):
        numbering = None
    lines, n, sub = [], 0, 0
    for p in doc.paragraphs:
        text = p.text.strip()
        if not text:
            continue
        info = _list_info(p, numbering)
        if info is None:
            lines.append(text)
        elif info[1] in ("bullet", "none"):
            lines.append(f"  - {text}")
        elif info[0] == 0:
            n, sub = n + 1, 0
            lines.append(f"{n}. {text}")
        elif info == (1, "decimal", True) and n:
            sub += 1
            lines.append(f"{n}.{sub}. {text}")
        else:
            lines.append(f"  - {text}")
    # Tables are common in contracts (parties, signatures); keep their text after the body.
    for table in doc.tables:
        for row in table.rows:
            cells = [c.text.strip() for c in row.cells if c.text.strip()]
            if cells:
                lines.append(" | ".join(dict.fromkeys(cells)))
    return "\n".join(lines)


MAX_PDF_PAGES = 30


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    try:
        if name.endswith(".txt"):
            text = data.decode("utf-8", errors="replace")
        elif name.endswith(".pdf"):
            reader = PdfReader(io.BytesIO(data))
            if len(reader.pages) > MAX_PDF_PAGES:  # a few-MB PDF can hold thousands of pages
                raise ParseError(f"PDF-də {len(reader.pages)} səhifə var; maksimum {MAX_PDF_PAGES} dəstəklənir.")
            text = _strip_page_marks("\n".join(page.extract_text() or "" for page in reader.pages))
        elif name.endswith(".docx"):
            text = _docx_text(data)
        else:
            raise ParseError("Yalnız .pdf, .docx və .txt faylları qəbul olunur.")
    except ParseError:
        raise
    except Exception as e:  # corrupt / password-protected / mislabeled files
        raise ParseError("Faylı açmaq olmadı. Fayl zədələnmiş və ya şifrəli ola bilər.") from e

    text = text.strip()
    if len(text) < 50:
        raise ParseError(
            "Faylda oxunacaq mətn tapılmadı. Skan edilmiş PDF ola bilər — mətni əl ilə yapışdırın."
        )
    return text


@dataclass
class Clause:
    idx: int         # 1, 2, 3... — position; what the LLM and the database key on
    text: str
    label: str = ""  # the number printed in the contract: "5" or "2.1"


# "1." / "1)" / "12." at line start, optionally preceded by "Maddə"/"Bənd"
_CLAUSE_START = re.compile(r"^\s*(?:(?:Maddə|Bənd)\s+)?(\d{1,3})[.)]\s+", re.MULTILINE | re.IGNORECASE)
# Multi-level numbering, common in real contracts: "1. PREDMET" heading, then "1.1. ...", "1.2 ...", "2.1.1. ..."
_POINT_START = re.compile(
    r"^\s*(?:(?:Maddə|Bənd)\s+)?(?:(?P<sub>\d{1,3}(?:\.\d{1,3}){1,3})\.?|(?P<top>\d{1,3})[.)])\s+",
    re.MULTILINE | re.IGNORECASE,
)

# Signature / requisites block after the last clause — must not be glued onto it.
_EPILOGUE = re.compile(
    r"^\s*(?:Tərəflərin\s+(?:imza|rekvizit)|İmzalar|Imzalar|Rekvizitlər|(?:Ev sahibi|Kirayəçi|Kirayəyə verən)\s*:)|_{4,}",
    re.MULTILINE | re.IGNORECASE,
)


def _cut(text: str, starts: list[tuple[re.Match, str | None]]) -> list[Clause]:
    """Clause = text from one split point to the next; the last one stops before the signature block.
    A split point labelled None (a section heading) ends the previous clause but is not a clause itself."""
    clauses = []
    for i, (m, label) in enumerate(starts):
        if label is None:
            continue
        if i + 1 < len(starts):
            end = starts[i + 1][0].start()
        else:
            tail = _EPILOGUE.search(text, m.end())
            end = tail.start() if tail else len(text)
        body = " ".join(text[m.end():end].split())
        if body:
            clauses.append(Clause(idx=len(clauses) + 1, text=body, label=label))
    return clauses


def _split_points(text: str, points: list[re.Match]) -> list[tuple[re.Match, str]]:
    """Split points of a multi-level contract: every "N.M" point is a clause, deeper points ("N.M.K") stay inside
    their parent, and a top-level "N." is a section heading when its own "N.1" points follow (otherwise a clause)."""
    starts = []
    for i, m in enumerate(points):
        if m["sub"]:
            if m["sub"].count(".") == 1:
                starts.append((m, m["sub"]))
            continue
        nxt = next((p for p in points[i + 1:] if p["sub"] is None or p["sub"].count(".") == 1), None)
        heading = nxt is not None and nxt["sub"] is not None and nxt["sub"].split(".")[0] == m["top"]
        starts.append((m, None if heading else m["top"]))
    return starts


def split_clauses(text: str) -> tuple[str, list[Clause]]:
    """Return (preamble, clauses). Falls back to paragraphs if no numbering is found."""
    points = list(_POINT_START.finditer(text))
    if sum(1 for p in points if p["sub"] and p["sub"].count(".") == 1) >= 3:
        # Section headings ("1. MÜQAVİLƏNİN PREDMETİ") carry no obligations: they are dropped, not analysed.
        return text[: points[0].start()].strip(), _cut(text, _split_points(text, points))

    matches = list(_CLAUSE_START.finditer(text))
    if len(matches) >= 3:
        return text[: matches[0].start()].strip(), _cut(text, [(m, m.group(1)) for m in matches])

    paragraphs = [" ".join(p.split()) for p in re.split(r"\n\s*\n", text) if len(p.strip()) > 20]
    return "", [Clause(idx=i + 1, text=p, label=str(i + 1)) for i, p in enumerate(paragraphs)]
