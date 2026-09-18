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
    assert len(prompts) == 7
    assert len(tools) == 27
    assert len(resources) == 3


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
