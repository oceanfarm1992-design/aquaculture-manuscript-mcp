import pandas as pd
import pytest
from docx import Document
from openpyxl import load_workbook
from pptx import Presentation

from aquaculture_manuscript_mcp.tools import figures, planning, research_documents as rd


def _plan(**kw):
    args = dict(treatments=3, units_per_treatment=4, fish_per_unit=100, initial_weight_g=50, expected_final_weight_g=150,
                duration_days=90, expected_fcr=1.5, expected_fcr_source="farm records 2024", expected_survival_pct=90,
                expected_survival_source="farm records 2024")
    args.update(kw)
    return planning.plan_trial_resources(**args)


def test_resource_plan_arithmetic():
    r = _plan(fish_sampled_per_unit_per_event=5, sampling_events=2, unit_volume_m3=2.0)
    assert r["design"]["total_units"] == 12
    assert r["fish"]["stocked"] == 1200 and r["fish"]["to_procure"] == 1320
    # per unit: 10 deaths, 10 sampled, 80 at end; b0 = 5 kg, b1 = 12 kg, removed = 20 x 100 g = 2 kg
    assert r["biomass_kg"]["final_per_unit"] == pytest.approx(12.0)
    assert r["feed_kg"]["per_unit"] == pytest.approx(1.5 * (12 + 2 - 5))
    assert r["density_kg_m3"]["final"] == pytest.approx(6.0)
    assert r["costs"]["feed"] == "unit cost needed"


def test_resource_plan_requires_sources():
    with pytest.raises(ValueError, match="feed_cost_source"):
        _plan(feed_cost_per_kg=1.2, currency="KWD")
    with pytest.raises(ValueError, match="currency"):
        _plan(feed_cost_per_kg=1.2, feed_cost_source="supplier quote")
    r = _plan(feed_cost_per_kg=2.0, feed_cost_source="supplier quote", currency="KWD")
    assert r["costs"]["feed"]["amount"] == pytest.approx(2.0 * r["feed_kg"]["total"])


def _text(path):
    return "\n".join(p.text for p in Document(path).paragraphs)


def test_design_document_marks_missing_sections(tmp_path):
    out = tmp_path / "design.docx"
    r = rd.export_research_design_document(str(out), "Heat trial", {"research_question": "Does X?", "hypotheses": "- H0\n- H1"},
                                           gate_history=[{"gate": "G1_research_question", "status": "approved", "summary": "s",
                                                          "user_confirmation": "yes", "recorded": "t"}])
    assert not r["complete"] and "study_type" in r["missing_sections"] and len(r["missing_sections"]) == 12
    text = _text(out)
    assert "Does X?" in text and rd.MISSING in text
    with pytest.raises(ValueError, match="unknown section"):
        rd.export_research_design_document(str(out), "t", {"intro": "x"})


def test_proposal_gantt_budget_and_totals(tmp_path):
    out = tmp_path / "proposal.docx"
    sections = {k: f"Text for {k}." for k, _ in rd.PROPOSAL_SECTIONS}
    budget = [{"item": "Feed", "quantity": 100, "unit": "kg", "unit_cost": 1.5, "source": "quote"},
              {"item": "Lab", "quantity": 10, "unit": "samples", "unit_cost": None}]
    r = rd.export_research_proposal(str(out), "P", sections, gantt=[{"task": "Trial", "start_month": 2, "end_month": 4}],
                                    total_months=6, budget=budget, currency="KWD", references=["Ref A."])
    assert r["budget"]["total_of_costed_lines"] == pytest.approx(150.0)
    assert r["budget"]["lines_missing_unit_cost"] == ["Lab"] and not r["budget"]["complete"]
    d = Document(str(out))
    gantt = d.tables[0]
    assert len(gantt.columns) == 7 and gantt.rows[1].cells[0].text == "Trial"
    shaded = [i for i, c in enumerate(gantt.rows[1].cells) if "w:shd" in c._tc.xml]
    assert shaded == [2, 3, 4]
    assert "TOTAL (INCOMPLETE)" in d.tables[1].rows[-1].cells[0].text
    headings = [p.text for p in d.paragraphs if p.style.name.startswith("Heading")]
    assert len(headings) == 21 and headings[0] == "2. Abstract"


def test_proposal_budget_needs_source_for_costed_lines(tmp_path):
    with pytest.raises(ValueError, match="no source"):
        rd.export_research_proposal(str(tmp_path / "p.docx"), "P", {}, budget=[{"item": "x", "quantity": 1, "unit": "u", "unit_cost": 5}], currency="KWD")


def test_analysis_plan_xlsx(tmp_path):
    out = tmp_path / "plan.xlsx"
    r = rd.export_analysis_plan_xlsx(str(out), "Plan", [{"hypothesis_id": "H1", "hypothesis": "h", "response": "mortality",
                                                         "predictors": "temp", "experimental_unit": "cage", "model": "GEE",
                                                         "assumption_checks": "dispersion", "alpha": 0.05,
                                                         "multiple_comparisons": "none", "missing_data": None}])
    assert r["missing_fields"] == ["H1: Missing data"]
    ws = load_workbook(out).active
    assert ws["A3"].value == "H1" and ws["J3"].value == rd.MISSING


def test_figure_and_presentation(tmp_path):
    t = tmp_path / "t.csv"
    pd.DataFrame({"species": ["A", "A", "B", "B", "B"], "sgr": [1.0, 1.2, 0.8, 0.9, 1.0],
                  "date": pd.date_range("2024-01-01", periods=5), "temp": [20, 22, 24, 26, 28]}).to_csv(t, index=False)
    bar = figures.make_figure(str(t), "mean_bar", "species", "sgr", str(tmp_path / "bar.png"))
    assert bar["n_by_group"] == {"A": 2, "B": 3}
    for kind, x in (("line", "date"), ("scatter", "temp"), ("box", "species")):
        figures.make_figure(str(t), kind, x, "sgr", str(tmp_path / f"{kind}.png"), group="species" if kind != "box" else None)
    assert (tmp_path / "line.png").stat().st_size > 1000
    deck = rd.export_presentation_pptx(str(tmp_path / "d.pptx"), "Title", "Sub",
                                       [{"title": "Result", "bullets": ["a", "b"], "image_path": str(tmp_path / "bar.png"), "notes": "n"},
                                        {"title": "Missing image", "image_path": str(tmp_path / "nope.png")}])
    assert deck["slides"] == 3 and deck["missing_images"] == [str(tmp_path / "nope.png")]
    assert len(Presentation(str(tmp_path / "d.pptx")).slides) == 3
