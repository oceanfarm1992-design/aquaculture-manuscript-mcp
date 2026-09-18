from unittest.mock import patch

from aquaculture_manuscript_mcp import pipeline


def test_pipeline_revises_once_then_clean():
    responses = [
        "Growth improved significantly under a modified feeding regime as reported here.",  # overlaps
        "Fish grew markedly faster once we adjusted the feeding schedule in this trial.",  # clean revision
        "Fish grew markedly faster once we adjusted the feeding schedule in this trial.",  # copyedit
    ]
    calls = []

    def fake_call(system_prompt, user_input, model=None, base_url=None):
        calls.append(user_input)
        return responses[len(calls) - 1]

    with patch.object(pipeline.llm_client, "call", side_effect=fake_call):
        result = pipeline.run_pipeline(
            task_input="Write the results sentence about the feeding trial.",
            source_texts=["Growth improved significantly under a modified feeding regime in prior trials."],
            max_revisions=2,
        )

    assert result["revisions_used"] == 1
    assert result["clean"] is True
    assert len(calls) == 3
    steps = [s["step"] for s in result["log"]]
    assert steps == [
        "drafting-agent",
        "check_citation_integrity",
        "drafting-agent",
        "check_citation_integrity",
        "copyedit-agent",
    ]


def test_pipeline_stops_at_max_revisions_and_reports_unresolved():
    def always_overlapping(system_prompt, user_input, model=None, base_url=None):
        return "Growth improved significantly under a modified feeding regime as reported here."

    with patch.object(pipeline.llm_client, "call", side_effect=always_overlapping):
        result = pipeline.run_pipeline(
            task_input="Write the results sentence.",
            source_texts=["Growth improved significantly under a modified feeding regime in prior trials."],
            max_revisions=2,
        )

    assert result["revisions_used"] == 2
    assert result["clean"] is False


def test_pipeline_skips_check_when_no_source_texts():
    def fake_call(system_prompt, user_input, model=None, base_url=None):
        return "Any drafted text."

    with patch.object(pipeline.llm_client, "call", side_effect=fake_call):
        result = pipeline.run_pipeline(task_input="Write something.")

    assert result["revisions_used"] == 0
    assert result["clean"] is None
