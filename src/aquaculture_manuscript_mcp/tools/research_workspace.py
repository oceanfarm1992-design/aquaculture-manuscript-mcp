"""Research project workspace: the system's memory, data repository,
reference library, approval-gate record and audit trail, kept as plain files
in one folder per project so it can be versioned with git.

Layout of a project folder:

    project.json            name, description, workflow, created date
    data/raw/               original datasets, copied in unchanged (+ sha256)
    data/processed/         cleaned or derived datasets
    analysis/               saved tool outputs (JSON)
    references/library.json verified references (CrossRef-resolved only)
    documents/              proposals, design documents, manuscripts
    decisions.json          approval gates: proposed -> approved / rejected
    audit.jsonl             one line per important claim and where it came from

Approval gates: agents may *propose* a gate decision. Only the human user may
approve or reject it; the agents are instructed to call ``record_gate_decision``
with status "approved"/"rejected" only after the user has said so explicitly
in the conversation, and to quote that confirmation.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from aquaculture_manuscript_mcp.tools import citations

GATES: dict[str, str] = {
    "G1_research_question": "Which research question(s) to pursue (after data intelligence, opportunity discovery and literature review)",
    "G2_study_design": "Final experimental or observational design, sample size and statistical plan (the Research Design Document)",
    "G3_proposal": "Proposal ready for scientific/management review, after feasibility and ethics checks",
    "G4_publication": "Results and manuscript cleared for submission or release",
}
WORKFLOWS = ("A_question_first", "B_data_first")
SOURCE_TYPES = ("dataset", "analysis", "reference", "calculation", "user_statement")
_SUBDIRS = ("data/raw", "data/processed", "analysis", "references", "documents")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _project(project_dir: str) -> Path:
    p = Path(project_dir)
    if not (p / "project.json").exists():
        raise ValueError(f"{project_dir} is not a research project (no project.json). Create one with create_research_project.")
    return p


def _read_json(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def _write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")


def create_research_project(project_dir: str, name: str, description: str, workflow: str) -> dict:
    """Create the project folder structure. workflow: "A_question_first"
    (research idea -> design -> proposal) or "B_data_first" (existing farm
    data -> opportunities -> proposal)."""
    if workflow not in WORKFLOWS:
        raise ValueError(f"workflow must be one of {WORKFLOWS}")
    p = Path(project_dir)
    if (p / "project.json").exists():
        raise ValueError(f"a project already exists at {project_dir}")
    for sub in _SUBDIRS:
        (p / sub).mkdir(parents=True, exist_ok=True)
    meta = {"name": name, "description": description, "workflow": workflow, "created": _now()}
    _write_json(p / "project.json", meta)
    _write_json(p / "decisions.json", [])
    _write_json(p / "references" / "library.json", [])
    (p / "audit.jsonl").touch()
    return {"project_dir": str(p), **meta, "gates": GATES}


def register_dataset(project_dir: str, source_path: str, description: str) -> dict:
    """Copy an original dataset into data/raw unchanged and record its
    SHA-256, so later analysis can prove which exact file it used."""
    p = _project(project_dir)
    src = Path(source_path)
    if not src.is_file():
        raise ValueError(f"file not found: {source_path}")
    dest = p / "data" / "raw" / src.name
    if dest.exists():
        raise ValueError(f"{dest.name} is already registered; rename the file to register a new version")
    shutil.copy2(src, dest)
    digest = hashlib.sha256(dest.read_bytes()).hexdigest()
    manifest_path = p / "data" / "raw" / "manifest.json"
    manifest = _read_json(manifest_path, [])
    entry = {"file": dest.name, "sha256": digest, "description": description, "source_path": str(src), "registered": _now()}
    manifest.append(entry)
    _write_json(manifest_path, manifest)
    return {"registered": str(dest), **entry}


def save_analysis(project_dir: str, name: str, result: dict, inputs: dict | None = None) -> dict:
    """Save a tool result as analysis/<timestamp>_<name>.json with its inputs."""
    p = _project(project_dir)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)[:60]
    path = p / "analysis" / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{safe}.json"
    _write_json(path, {"name": name, "saved": _now(), "inputs": inputs or {}, "result": result})
    return {"saved_to": str(path)}


def add_verified_reference(project_dir: str, doi: str, relevance_note: str) -> dict:
    """Resolve a DOI in CrossRef and add it to the project's reference
    library. Unresolvable DOIs are refused, never stored as 'unverified'."""
    p = _project(project_dir)
    meta = citations.resolve_doi_metadata(doi)
    lib_path = p / "references" / "library.json"
    lib = _read_json(lib_path, [])
    if any(r["doi"].lower() == meta["doi"].lower() for r in lib):
        return {"status": "already_in_library", "doi": meta["doi"]}
    lib.append({**meta, "relevance_note": relevance_note, "verified_via": "CrossRef", "added": _now()})
    _write_json(lib_path, lib)
    return {"status": "added", "library_size": len(lib), **meta}


def list_references(project_dir: str) -> list[dict]:
    """The project's verified reference library."""
    return _read_json(_project(project_dir) / "references" / "library.json", [])


def record_gate_decision(
    project_dir: str,
    gate: str,
    status: str,
    summary: str,
    rationale: str,
    user_confirmation: str = "",
) -> dict:
    """Record a decision at an approval gate.

    status "proposed": an agent's recommendation awaiting the user.
    status "approved"/"rejected": ONLY after the user explicitly decided in
        the conversation; ``user_confirmation`` must quote what they said.
    """
    if gate not in GATES:
        raise ValueError(f"gate must be one of {sorted(GATES)}")
    if status not in ("proposed", "approved", "rejected"):
        raise ValueError("status must be 'proposed', 'approved' or 'rejected'")
    if status != "proposed" and not user_confirmation.strip():
        raise ValueError(
            "approving or rejecting a gate needs user_confirmation: quote the user's "
            "explicit decision. Agents may only record status='proposed' on their own."
        )
    p = _project(project_dir)
    decisions = _read_json(p / "decisions.json", [])
    entry = {
        "gate": gate,
        "gate_description": GATES[gate],
        "status": status,
        "summary": summary,
        "rationale": rationale,
        "user_confirmation": user_confirmation or None,
        "recorded": _now(),
    }
    decisions.append(entry)
    _write_json(p / "decisions.json", decisions)
    return entry


def log_claim(project_dir: str, claim: str, source_type: str, source_ref: str) -> dict:
    """Append an important claim and its origin to the audit trail.
    source_type: dataset | analysis | reference | calculation | user_statement.
    source_ref: file name + row/field, analysis file, DOI, or the user's words."""
    if source_type not in SOURCE_TYPES:
        raise ValueError(f"source_type must be one of {SOURCE_TYPES}")
    if not source_ref.strip():
        raise ValueError("source_ref is required — a claim without a traceable source must not be logged as supported")
    p = _project(project_dir)
    entry = {"claim": claim, "source_type": source_type, "source_ref": source_ref, "logged": _now()}
    with (p / "audit.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    return entry


def get_project_status(project_dir: str) -> dict:
    """Where the project stands: datasets, analyses, references, documents,
    latest status of each gate, and audit-trail size."""
    p = _project(project_dir)
    decisions = _read_json(p / "decisions.json", [])
    gate_state = {g: "not_started" for g in GATES}
    for d in decisions:
        gate_state[d["gate"]] = d["status"]
    next_gate = next((g for g in GATES if gate_state[g] != "approved"), None)
    audit_lines = (p / "audit.jsonl").read_text(encoding="utf-8").splitlines() if (p / "audit.jsonl").exists() else []
    return {
        "project": _read_json(p / "project.json", {}),
        "datasets": _read_json(p / "data" / "raw" / "manifest.json", []),
        "processed_files": sorted(f.name for f in (p / "data" / "processed").iterdir()),
        "analyses": sorted(f.name for f in (p / "analysis").iterdir()),
        "reference_count": len(_read_json(p / "references" / "library.json", [])),
        "documents": sorted(f.name for f in (p / "documents").iterdir()),
        "gates": gate_state,
        "next_gate_awaiting_approval": next_gate,
        "audit_entries": len(audit_lines),
    }
