"""Research document generators: Research Design Document (.docx),
research proposal (.docx, 22 sections, Gantt chart, budget table), statistical
analysis plan (.xlsx) and presentation (.pptx).

Like docx_export, these render what they are given and never fill gaps:
a missing section is printed as "NOT YET PROVIDED" and listed in the return
value, so an incomplete document is visibly incomplete.
"""

from __future__ import annotations

from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

MISSING = "NOT YET PROVIDED"
ACCENT = "2E8B57"  # sea green

DESIGN_SECTIONS: list[tuple[str, str]] = [
    ("research_question", "Research question"),
    ("hypotheses", "Hypotheses"),
    ("study_type", "Study type and rationale"),
    ("experimental_unit", "Experimental unit"),
    ("treatments_and_control", "Treatments and control"),
    ("replication_and_sample_size", "Replication and sample-size justification"),
    ("randomisation_and_blocking", "Randomisation and blocking"),
    ("sampling_schedule", "Sampling schedule"),
    ("response_variables", "Response variables and measurement methods"),
    ("statistical_analysis_plan", "Statistical analysis plan"),
    ("threats_to_validity", "Threats to validity and how the design controls them"),
    ("data_management", "Data management and quality control"),
    ("ethics_and_permits", "Animal welfare, ethics and permits"),
    ("resources_and_feasibility", "Resources and feasibility"),
]

PROPOSAL_SECTIONS: list[tuple[str, str]] = [
    ("abstract", "Abstract"),
    ("introduction", "Introduction and background"),
    ("problem_statement", "Research problem statement"),
    ("justification", "Research justification and significance"),
    ("literature_review", "Literature review"),
    ("research_gap", "Identified research gap"),
    ("research_questions", "Research questions"),
    ("objectives", "General and specific objectives"),
    ("hypotheses", "Hypotheses"),
    ("conceptual_framework", "Conceptual framework"),
    ("materials_methods", "Materials and methods"),
    ("study_design", "Experimental or observational study design"),
    ("sampling_and_sample_size", "Sampling strategy and sample size justification"),
    ("data_collection", "Data collection procedures"),
    ("statistical_analysis_plan", "Statistical analysis plan"),
    ("ethics", "Ethical considerations"),
    ("expected_results", "Expected results and scientific contribution"),
    ("limitations", "Limitations"),
    ("work_plan", "Work plan and Gantt chart"),
    ("budget", "Budget and resource requirements"),
    ("references_appendices", "References and appendices"),
]


def _doc(landscape: bool = False) -> Document:
    d = Document()
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)
    if landscape:
        s = d.sections[0]
        s.orientation = WD_ORIENT.LANDSCAPE
        s.page_width, s.page_height = s.page_height, s.page_width
    return d


def _shade(cell, hex_fill: str) -> None:
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_fill)
    cell._tc.get_or_add_tcPr().append(shd)


def _title(d: Document, title: str, subtitle: str | None = None) -> None:
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(title)
    r.bold = True
    r.font.size = Pt(16)
    if subtitle:
        s = d.add_paragraph()
        s.alignment = WD_ALIGN_PARAGRAPH.CENTER
        s.add_run(subtitle).italic = True


def _body(d: Document, text: str | None) -> bool:
    """Write text (paragraphs split on blank lines; lines starting '- ' as
    bullets). Returns False and writes a visible marker when missing."""
    if not text or not str(text).strip():
        p = d.add_paragraph()
        r = p.add_run(MISSING)
        r.bold = True
        r.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
        return False
    for block in str(text).split("\n\n"):
        lines = [ln for ln in block.strip().splitlines() if ln.strip()]
        if lines and all(ln.lstrip().startswith("- ") for ln in lines):
            for ln in lines:
                d.add_paragraph(ln.lstrip()[2:], style="List Bullet")
        elif lines:
            d.add_paragraph(" ".join(ln.strip() for ln in lines))
    return True


def _table(d: Document, headers: list[str], rows: list[list], caption: str | None = None):
    if caption:
        c = d.add_paragraph()
        c.add_run(caption).bold = True
    t = d.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    for i, h in enumerate(headers):
        cell = t.rows[0].cells[i]
        cell.text = str(h)
        cell.paragraphs[0].runs[0].bold = True
        _shade(cell, "D9EAD3")
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = "" if v is None else str(v)
    d.add_paragraph()
    return t


def export_research_design_document(
    output_path: str,
    title: str,
    sections: dict[str, str],
    gate_history: list[dict] | None = None,
    version_note: str | None = None,
) -> dict:
    """Research Design Document (.docx) — reviewed at gate G2 before any
    proposal is written. ``sections`` keys: see DESIGN_SECTIONS (unknown
    keys are rejected). Missing sections are printed as NOT YET PROVIDED."""
    known = dict(DESIGN_SECTIONS)
    unknown = sorted(set(sections) - set(known))
    if unknown:
        raise ValueError(f"unknown section key(s) {unknown}. Valid: {list(known)}")
    d = _doc()
    _title(d, title, "Research Design Document" + (f" — {version_note}" if version_note else ""))
    missing = []
    for n, (key, heading) in enumerate(DESIGN_SECTIONS, 1):
        d.add_heading(f"{n}. {heading}", level=1)
        if not _body(d, sections.get(key)):
            missing.append(key)
    if gate_history:
        d.add_heading("Decision record", level=1)
        _table(d, ["Gate", "Status", "Summary", "User confirmation", "Recorded"],
               [[g.get("gate"), g.get("status"), g.get("summary"), g.get("user_confirmation") or "", g.get("recorded")] for g in gate_history])
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    d.save(output_path)
    return {"file_path": output_path, "sections_written": len(DESIGN_SECTIONS) - len(missing), "missing_sections": missing,
            "complete": not missing}


def export_research_proposal(
    output_path: str,
    title: str,
    sections: dict[str, str],
    authors: list[str] | None = None,
    gantt: list[dict] | None = None,
    total_months: int | None = None,
    budget: list[dict] | None = None,
    currency: str | None = None,
    references: list[str] | None = None,
) -> dict:
    """Full research proposal (.docx) in the 22-part structure (title + 21
    sections, see PROPOSAL_SECTIONS).

    gantt: [{"task": str, "start_month": int, "end_month": int}] — drawn as a
        shaded month grid under "Work plan and Gantt chart".
    budget: [{"item": str, "quantity": number, "unit": str,
        "unit_cost": number|None, "source": str}] — line totals and the grand
        total are computed here. A line without unit_cost shows "unit cost
        needed" and the total is marked incomplete.
    references: formatted reference strings (from the verified library).
    """
    known = dict(PROPOSAL_SECTIONS)
    unknown = sorted(set(sections) - set(known))
    if unknown:
        raise ValueError(f"unknown section key(s) {unknown}. Valid: {list(known)}")
    d = _doc()
    _title(d, title, ", ".join(authors) if authors else None)
    missing = []
    budget_info = None
    for n, (key, heading) in enumerate(PROPOSAL_SECTIONS, 2):  # 1 = title
        d.add_heading(f"{n}. {heading}", level=1)
        has_extra = (key == "work_plan" and gantt) or (key == "budget" and budget) or (key == "references_appendices" and references)
        if not sections.get(key) and has_extra:
            pass
        elif not _body(d, sections.get(key)):
            missing.append(key)
        if key == "work_plan" and gantt:
            _gantt(d, gantt, total_months)
        if key == "budget" and budget:
            budget_info = _budget(d, budget, currency)
        if key == "references_appendices" and references:
            for ref in references:
                p = d.add_paragraph(ref)
                p.paragraph_format.left_indent = Pt(18)
                p.paragraph_format.first_line_indent = Pt(-18)
    for key, needs in (("work_plan", gantt), ("budget", budget)):
        if not needs and key not in missing:
            missing.append(f"{key} (no {'gantt tasks' if key == 'work_plan' else 'budget lines'})")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    d.save(output_path)
    words = sum(len(str(v).split()) for v in sections.values() if v)
    return {"file_path": output_path, "missing_sections": missing, "complete": not missing, "word_count": words, "budget": budget_info}


def _gantt(d: Document, tasks: list[dict], total_months: int | None) -> None:
    for t in tasks:
        if not {"task", "start_month", "end_month"} <= set(t):
            raise ValueError(f"gantt task needs task, start_month, end_month: {t}")
        if not 1 <= int(t["start_month"]) <= int(t["end_month"]):
            raise ValueError(f"gantt task months must satisfy 1 <= start <= end: {t}")
    months = total_months or max(int(t["end_month"]) for t in tasks)
    if any(int(t["end_month"]) > months for t in tasks):
        raise ValueError("a gantt task ends after total_months")
    c = d.add_paragraph()
    c.add_run("Gantt chart (months)").bold = True
    table = d.add_table(rows=1, cols=months + 1)
    table.style = "Table Grid"
    table.rows[0].cells[0].text = "Activity"
    for m in range(1, months + 1):
        table.rows[0].cells[m].text = str(m)
    for cell in table.rows[0].cells:
        cell.paragraphs[0].runs[0].bold = True
    for t in tasks:
        cells = table.add_row().cells
        cells[0].text = str(t["task"])
        for m in range(int(t["start_month"]), int(t["end_month"]) + 1):
            _shade(cells[m], ACCENT)
    d.add_paragraph()


def _budget(d: Document, lines: list[dict], currency: str | None) -> dict:
    if not currency:
        raise ValueError("currency is required with a budget")
    rows, total, incomplete = [], 0.0, []
    for ln in lines:
        if not {"item", "quantity", "unit"} <= set(ln):
            raise ValueError(f"budget line needs item, quantity, unit: {ln}")
        uc = ln.get("unit_cost")
        if uc is None:
            incomplete.append(ln["item"])
            rows.append([ln["item"], ln["quantity"], ln["unit"], "unit cost needed", "—", ln.get("source", "")])
            continue
        if not str(ln.get("source", "")).strip():
            raise ValueError(f"budget line '{ln['item']}' has a unit_cost but no source")
        amount = float(ln["quantity"]) * float(uc)
        total += amount
        rows.append([ln["item"], ln["quantity"], ln["unit"], f"{float(uc):,.2f}", f"{amount:,.2f}", ln["source"]])
    rows.append(["TOTAL" + (" (INCOMPLETE)" if incomplete else ""), "", "", "", f"{total:,.2f}", ""])
    _table(d, ["Item", "Quantity", "Unit", f"Unit cost ({currency})", f"Amount ({currency})", "Source"], rows, f"Budget ({currency})")
    return {"currency": currency, "total_of_costed_lines": total, "lines_missing_unit_cost": incomplete, "complete": not incomplete}


def export_analysis_plan_xlsx(output_path: str, title: str, rows: list[dict]) -> dict:
    """Statistical analysis plan as an Excel sheet, one row per hypothesis.
    Row keys: hypothesis_id, hypothesis, response, predictors, experimental_unit,
    model, assumption_checks, alpha, multiple_comparisons, missing_data, notes."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill

    cols = [
        ("hypothesis_id", "ID", 8), ("hypothesis", "Hypothesis", 45), ("response", "Response variable", 22),
        ("predictors", "Predictors / treatments", 28), ("experimental_unit", "Experimental unit", 16),
        ("model", "Model / test", 34), ("assumption_checks", "Assumption checks", 28), ("alpha", "Alpha", 8),
        ("multiple_comparisons", "Multiple comparisons", 22), ("missing_data", "Missing data", 22), ("notes", "Notes", 30),
    ]
    if not rows:
        raise ValueError("rows must contain at least one hypothesis")
    wb = Workbook()
    ws = wb.active
    ws.title = "Analysis plan"
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([label for _, label, _ in cols])
    for i, (_, _, width) in enumerate(cols, 1):
        cell = ws.cell(row=2, column=i)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=ACCENT)
        ws.column_dimensions[cell.column_letter].width = width
    missing = []
    for r in rows:
        values = []
        for key, label, _ in cols:
            v = r.get(key)
            if v in (None, "") and key not in ("notes",):
                missing.append(f"{r.get('hypothesis_id', '?')}: {label}")
                v = MISSING
            values.append(v)
        ws.append(values)
    for row in ws.iter_rows(min_row=3):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "B3"
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(output_path)
    return {"file_path": output_path, "hypotheses": len(rows), "missing_fields": missing, "complete": not missing}


def export_presentation_pptx(output_path: str, title: str, subtitle: str, slides: list[dict]) -> dict:
    """Slide deck (.pptx, 16:9). slides: [{"title": str, "bullets": [str],
    "image_path": optional PNG (e.g. from make_figure), "notes": optional
    speaker notes}]."""
    from pptx import Presentation
    from pptx.util import Inches, Pt as PPt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = title
    s.placeholders[1].text = subtitle
    missing_images = []
    for spec in slides:
        if not spec.get("title"):
            raise ValueError(f"every slide needs a title: {spec}")
        slide = prs.slides.add_slide(prs.slide_layouts[5])  # title only
        slide.shapes.title.text = spec["title"]
        img = spec.get("image_path")
        has_img = bool(img) and Path(img).is_file()
        if img and not has_img:
            missing_images.append(img)
        text_width = Inches(5.8) if has_img else Inches(12.3)
        box = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), text_width, Inches(5.5))
        tf = box.text_frame
        tf.word_wrap = True
        for i, b in enumerate(spec.get("bullets", [])):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.text = f"• {b}"
            p.font.size = PPt(20)
        if has_img:
            slide.shapes.add_picture(img, Inches(6.6), Inches(1.5), width=Inches(6.3))
        if spec.get("notes"):
            slide.notes_slide.notes_text_frame.text = spec["notes"]
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    prs.save(output_path)
    return {"file_path": output_path, "slides": len(slides) + 1, "missing_images": missing_images}
