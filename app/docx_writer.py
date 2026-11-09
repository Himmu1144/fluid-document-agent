"""Step 4 of the agent: turn the sections into a polished Word document (python-docx, no LLM).

Layout: a title block, the sections (prose with **bold** and "- " bullets, styled tables), an
"Assumptions and open questions" section, and an appendix showing how the agent produced the document.
"""
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor, Cm

from app.models import Plan, Section, SelfCheck, Table, TaskReport

INK = RGBColor(0x1F, 0x29, 0x37)
ACCENT = RGBColor(0x1E, 0x3A, 0x8A)
MUTED = RGBColor(0x6B, 0x72, 0x80)
HEADER_FILL = "1E3A8A"
STRIPE_FILL = "F3F4F6"
FONT = "Arial"  # installed on every Mac and Windows machine, so the document looks the same everywhere


def write_docx(path: Path, plan: Plan, sections: list[Section], reports: list[TaskReport], check: SelfCheck) -> Path:
    doc = Document()
    _base_styles(doc)
    _title_block(doc, plan)

    for section in sections:
        doc.add_heading(section.heading, level=1)
        _rich_text(doc, section.text)
        if section.table:
            _table(doc, section.table)

    if plan.assumptions or plan.conflicts:
        doc.add_heading("Assumptions and open questions", level=1)
        if plan.assumptions:
            _note(doc, "The request didn't specify these, so the document assumes:")
            for a in plan.assumptions:
                doc.add_paragraph(a, style="List Bullet")
        if plan.conflicts:
            _note(doc, "Conflicting requirements, and how this document handles them:")
            for c in plan.conflicts:
                doc.add_paragraph(c, style="List Bullet")

    _appendix(doc, reports, check)
    _footer(doc)
    doc.save(path)
    return path


def _base_styles(doc: Document) -> None:
    for s in doc.sections:
        s.left_margin = s.right_margin = Cm(2.2)
        s.top_margin = s.bottom_margin = Cm(2)
    normal = doc.styles["Normal"]
    normal.font.name, normal.font.size, normal.font.color.rgb = FONT, Pt(11), INK
    normal.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    for level, size in ((1, 15), (2, 12)):
        h = doc.styles[f"Heading {level}"]
        h.font.name, h.font.size, h.font.bold, h.font.color.rgb = FONT, Pt(size), True, ACCENT
        h.element.rPr.rFonts.set(qn("w:asciiTheme"), "")  # use our font, not the theme's
        h.paragraph_format.space_before, h.paragraph_format.space_after = Pt(16 if level == 1 else 10), Pt(6)


def _title_block(doc: Document, plan: Plan) -> None:
    kind = doc.add_paragraph()
    run = kind.add_run(plan.document_type.upper())
    run.font.size, run.font.bold, run.font.color.rgb = Pt(10), True, ACCENT
    title = doc.add_paragraph()
    run = title.add_run(plan.title)
    run.font.size, run.font.bold = Pt(24), True
    title.paragraph_format.space_after = Pt(4)
    meta = doc.add_paragraph()
    run = meta.add_run(f"Prepared for {plan.audience}  ·  {date.today():%d %B %Y}  ·  Meridian Bank & Insurance")
    run.font.size, run.font.color.rgb = Pt(10), MUTED
    _rule(meta)


def _rich_text(doc: Document, text: str) -> None:
    """Paragraphs, "- " bullets, "1. " numbered items, and **bold** inside lines; a line that is only bold is a sub-heading."""
    for line in text.splitlines():
        line = line.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if re.fullmatch(r"\*\*[^*]+\*\*:?", stripped):
            doc.add_heading(stripped.strip("*:").strip(), level=2)
        elif re.match(r"^[-*•]\s+", stripped):
            _runs(doc.add_paragraph(style="List Bullet"), re.sub(r"^[-*•]\s+", "", stripped))
        elif re.match(r"^\d+[.)]\s+", stripped):
            _runs(doc.add_paragraph(style="List Number"), re.sub(r"^\d+[.)]\s+", "", stripped))
        else:
            _runs(doc.add_paragraph(), stripped.lstrip("# "))


def _runs(paragraph, text: str) -> None:
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            paragraph.add_run(part).bold = i % 2 == 1


def _table(doc: Document, table: Table) -> None:
    width = len(table.columns)
    t = doc.add_table(rows=1, cols=width)
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, name in zip(t.rows[0].cells, table.columns):
        _cell(cell, name, bold=True, color=RGBColor(0xFF, 0xFF, 0xFF), fill=HEADER_FILL)
    for n, row in enumerate(table.rows):
        cells = t.add_row().cells
        values = (row + [""] * width)[:width]
        is_total = str(values[0]).strip().lower().startswith("total")
        for cell, value in zip(cells, values):
            _cell(cell, str(value), bold=is_total, fill=STRIPE_FILL if n % 2 else None,
                  right=bool(re.match(r"^[₹$]?\s?[\d,.]+(\s?%| \w+)?$", str(value).strip())))
    _borders(t)
    _full_width(t, table)
    doc.add_paragraph()


def _cell(cell, text: str, bold=False, color=None, fill=None, right=False) -> None:
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    if right:
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    run = p.add_run(text)
    run.font.size, run.bold = Pt(10), bold
    if color:
        run.font.color.rgb = color
    if fill:
        shade = OxmlElement("w:shd")
        shade.set(qn("w:val"), "clear"), shade.set(qn("w:color"), "auto"), shade.set(qn("w:fill"), fill)
        cell._tc.get_or_add_tcPr().append(shade)


def _full_width(table, data: Table) -> None:
    """Span the text width; each column gets room in proportion to its longest entry (within limits)."""
    text_width = Cm(21.0 - 4.4)  # A4 width minus the two 2.2 cm margins
    lengths = [max([len(str(data.columns[i]))] + [len(str(r[i])) for r in data.rows if i < len(r)])
               for i in range(len(data.columns))]
    weights = [min(max(n, 6), 45) for n in lengths]
    widths = [int(text_width * w / sum(weights)) for w in weights]
    table.autofit = False
    for column, width in zip(table.columns, widths):  # the grid, which most renderers read
        column.width = width
    for row in table.rows:                             # and each cell, which Word reads
        for cell, width in zip(row.cells, widths):
            cell.width = width
    tbl_w = table._tbl.tblPr.find(qn("w:tblW"))        # the table's own width: fixed, not "auto"
    tbl_w.set(qn("w:type"), "dxa"), tbl_w.set(qn("w:w"), str(sum(widths) // 635))  # EMU → twentieths of a point
    margins = OxmlElement("w:tblCellMar")
    for edge, size in (("top", "60"), ("bottom", "60"), ("left", "100"), ("right", "100")):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:w"), size), el.set(qn("w:type"), "dxa")
        margins.append(el)
    table._tbl.tblPr.append(margins)


def _borders(table) -> None:
    """Thin light-grey lines instead of Word's heavy black grid."""
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single"), el.set(qn("w:sz"), "4"), el.set(qn("w:color"), "D1D5DB")
        borders.append(el)
    table._tbl.tblPr.append(borders)


def _appendix(doc: Document, reports: list[TaskReport], check: SelfCheck) -> None:
    doc.add_heading("Appendix: how this document was produced", level=1)
    _note(doc, "An autonomous agent planned these steps from the request, ran each with a tool, then reviewed its own draft.")
    _table(doc, Table(columns=["Step", "Tool", "Status", "Result"],
                      rows=[[f"{r.id}. {r.title}", r.tool, r.status, r.note] for r in reports]))
    verdict = "Passed" if check.passed else f"{len(check.issues)} issue(s) found, {len(check.fixes)} fixed"
    _note(doc, f"Self-check: {verdict}.")
    for f in check.fixes:
        doc.add_paragraph(f, style="List Bullet")


def _note(doc: Document, text: str) -> None:
    run = doc.add_paragraph().add_run(text)
    run.italic, run.font.color.rgb = True, MUTED


def _rule(paragraph) -> None:
    """A thin line under the title block."""
    border = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"), bottom.set(qn("w:sz"), "6"), bottom.set(qn("w:color"), "1E3A8A"), bottom.set(qn("w:space"), "8")
    border.append(bottom)
    paragraph._p.get_or_add_pPr().append(border)


def _footer(doc: Document) -> None:
    p = doc.sections[0].footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = p.add_run("Generated by the Document Agent  ·  Page ")
    run.font.size, run.font.color.rgb = Pt(8), MUTED
    for kind, text in (("begin", None), (None, "PAGE"), ("end", None)):
        r = p.add_run()
        r.font.size, r.font.color.rgb = Pt(8), MUTED
        if kind:
            fld = OxmlElement("w:fldChar")
            fld.set(qn("w:fldCharType"), kind)
            r._r.append(fld)
        else:
            instr = OxmlElement("w:instrText")
            instr.text = text
            r._r.append(instr)
