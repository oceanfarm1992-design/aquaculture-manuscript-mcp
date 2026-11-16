"""Smoke tests through the real MCP tool-call layer, not the bare Python
functions. Catches serialization issues (e.g. a numpy dtype the JSON
encoder chokes on) that direct-function tests with pytest.approx would miss,
since pytest.approx accepts numpy floats without ever serializing them."""

import pytest

from aquaculture_manuscript_mcp.server import mcp


@pytest.mark.asyncio
async def test_prompts_tools_resources_all_register():
    prompts = await mcp.list_prompts()
    tools = await mcp.list_tools()
    resources = await mcp.list_resources()
    assert len(prompts) == 7 + 12
    assert len(tools) == 30 + 15
    assert len(resources) == 4


@pytest.mark.asyncio
async def test_research_prompt_renders_with_project_context():
    result = await mcp.get_prompt("research-director", {"task_input": "Find research topics", "project_dir": "/p"})
    text = result.messages[0].content.text
    assert "Research Director" in text and "/p" in text and "Find research topics" in text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name",
    ["profile_dataset", "suggest_column_roles", "check_data_quality", "compute_performance_metrics", "discover_research_opportunities"],
)
async def test_farm_data_tools_round_trip(tool_name, farm_csv, column_roles, tmp_path):
    """Farm-data outputs contain dates and numpy values; they must survive
    real MCP serialization, and saving to a project must work."""
    from aquaculture_manuscript_mcp.tools import research_workspace

    args = {"path": farm_csv}
    if tool_name not in ("profile_dataset", "suggest_column_roles"):
        proj = tmp_path / "proj"
        research_workspace.create_research_project(str(proj), "t", "d", "B_data_first")
        args.update({"column_roles": column_roles, "project_dir": str(proj)})
    result = await mcp.call_tool(tool_name, args)
    assert result is not None


@pytest.mark.asyncio
async def test_sample_size_round_trip():
    result = await mcp.call_tool(
        "calculate_sample_size", {"test": "two_sample_t", "effect_size": 0.8, "effect_size_source": "pilot"}
    )
    assert result is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_name,args",
    [
        ("descriptive_stats", {"values": [10.1, 10.5, 9.8, 10.2, 10.0]}),
        ("check_normality", {"values": [10.1, 10.5, 9.8, 10.2, 10.0, 9.9]}),
        (
            "check_variance_homogeneity",
            {"groups": [[10.1, 10.5, 9.8], [12.3, 12.1, 12.6]]},
        ),
        ("analyze_ttest", {"group_a": [10.1, 10.5, 9.8], "group_b": [12.3, 12.1, 12.6]}),
        (
            "analyze_anova",
            {"groups": [[10.1, 10.5, 9.8], [12.3, 12.1, 12.6], [8.5, 8.7, 8.4]]},
        ),
        (
            "analyze_posthoc_tukey",
            {"groups": [[10.1, 10.5, 9.8], [12.3, 12.1, 12.6], [8.5, 8.7, 8.4]]},
        ),
        ("calculate_effect_size_cohens_d", {"group_a": [10.1, 10.5, 9.8], "group_b": [12.3, 12.1, 12.6]}),
        ("calculate_eta_squared", {"groups": [[10.1, 10.5, 9.8], [12.3, 12.1, 12.6]]}),
        ("calculate_confidence_interval", {"values": [10.1, 10.5, 9.8, 10.2, 10.0]}),
        ("calculate_fcr", {"feed_given_g": 100, "initial_weight_g": 50, "final_weight_g": 100}),
        ("calculate_sgr", {"initial_weight_g": 10, "final_weight_g": 50, "days": 30}),
        (
            "calculate_unionized_ammonia",
            {"total_ammonia_nitrogen_mg_l": 1.0, "ph": 8.0, "temperature_c": 25.0},
        ),
        ("check_water_parameter", {"species": "nile_tilapia", "parameter": "dissolved_oxygen_mg_l", "measured_value": 6.0}),
    ],
)
async def test_tool_call_round_trips_through_mcp_serialization(tool_name, args):
    """Every result must survive the real MCP call_tool path (which JSON-
    serializes structured content), not just a direct Python call."""
    result = await mcp.call_tool(tool_name, args)
    assert result is not None
