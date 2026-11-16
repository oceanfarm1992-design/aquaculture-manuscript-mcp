import hashlib
import json

import pytest

from aquaculture_manuscript_mcp import research_agents
from aquaculture_manuscript_mcp.tools import citations, research_workspace as ws


@pytest.fixture
def project(tmp_path):
    d = tmp_path / "proj"
    ws.create_research_project(str(d), "Heat stress", "test project", "B_data_first")
    return str(d)


def test_create_rejects_bad_workflow_and_duplicates(tmp_path, project):
    with pytest.raises(ValueError, match="workflow"):
        ws.create_research_project(str(tmp_path / "x"), "n", "d", "C")
    with pytest.raises(ValueError, match="already exists"):
        ws.create_research_project(project, "n", "d", "A_question_first")


def test_register_dataset_copies_unchanged_with_checksum(tmp_path, project, farm_csv):
    entry = ws.register_dataset(project, farm_csv, "daily records")
    with open(farm_csv, "rb") as fh:
        assert entry["sha256"] == hashlib.sha256(fh.read()).hexdigest()
    with pytest.raises(ValueError, match="already registered"):
        ws.register_dataset(project, farm_csv, "again")


def test_gate_approval_requires_quoted_user_confirmation(project):
    ws.record_gate_decision(project, "G1_research_question", "proposed", "thermal mortality", "strongest signal")
    with pytest.raises(ValueError, match="user_confirmation"):
        ws.record_gate_decision(project, "G1_research_question", "approved", "thermal mortality", "ok")
    ws.record_gate_decision(project, "G1_research_question", "approved", "thermal mortality", "ok", "User: 'go with thermal'")
    status = ws.get_project_status(project)
    assert status["gates"]["G1_research_question"] == "approved"
    assert status["next_gate_awaiting_approval"] == "G2_study_design"
    with pytest.raises(ValueError, match="gate must be"):
        ws.record_gate_decision(project, "G9", "proposed", "s", "r")


def test_log_claim_requires_source(project):
    ws.log_claim(project, "Mortality doubled above 32 C", "analysis", "analysis/x.json")
    with pytest.raises(ValueError, match="source_ref is required"):
        ws.log_claim(project, "unsupported", "analysis", " ")
    assert ws.get_project_status(project)["audit_entries"] == 1


def test_save_analysis_writes_json(project):
    out = ws.save_analysis(project, "quality report", {"ok": True}, {"path": "f.csv"})
    with open(out["saved_to"]) as fh:
        assert json.load(fh)["result"] == {"ok": True}


def test_reference_library_stores_only_resolved_dois(project, monkeypatch):
    fake = {"doi": "10.1/abc", "title": "T", "authors": ["X, Y"], "container_title": "J", "year": 2020,
            "volume": "1", "issue": "1", "page": "1-2", "publisher": "P", "type": "journal-article", "url": "u"}
    monkeypatch.setattr(citations, "resolve_doi_metadata", lambda doi: fake)
    assert ws.add_verified_reference(project, "10.1/abc", "background")["status"] == "added"
    assert ws.add_verified_reference(project, "10.1/ABC", "again")["status"] == "already_in_library"

    def missing(doi):
        raise ValueError("not registered")

    monkeypatch.setattr(citations, "resolve_doi_metadata", missing)
    with pytest.raises(ValueError):
        ws.add_verified_reference(project, "10.9/none", "x")
    assert len(ws.list_references(project)) == 1


def test_all_twelve_research_agents_share_the_rules_and_output_block():
    assert len(research_agents.RESEARCH_AGENTS) == 12
    for name, spec in research_agents.RESEARCH_AGENTS.items():
        assert "Never invent experimental results" in spec["prompt"], name
        assert "### Agent output" in spec["prompt"], name
        assert "G2_study_design" in spec["prompt"], name
    with pytest.raises(ValueError):
        research_agents.get_research_prompt("nope")
