"""Unit tests for the metric-definition tool."""
import pytest

from app.tools.get_metric_definition import DEFINITIONS, run


REQUIRED_TERMS = {
    "IC50", "Ki", "Kd", "EC50", "pChEMBL value",
    "Assay confidence score", "Standard relation", "Data validity comment",
}


def test_all_required_metrics_defined():
    defined = {d["term"] for d in DEFINITIONS.values()}
    assert REQUIRED_TERMS <= defined


@pytest.mark.parametrize(
    "query,expected_term",
    [
        ("IC50", "IC50"),
        ("ic50", "IC50"),
        ("pChEMBL", "pChEMBL value"),
        ("pchembl_value", "pChEMBL value"),
        ("confidence score", "Assay confidence score"),
        ("standard relation", "Standard relation"),
        ("data validity comment", "Data validity comment"),
        ("Ki", "Ki"),
    ],
)
def test_lookup_resolves_aliases(query, expected_term):
    result = run(query)
    assert "error" not in result
    assert result["metric"]["term"] == expected_term
    assert result["metric"]["definition"]


def test_unknown_metric_returns_error_with_options():
    result = run("logp")
    assert "error" in result
    assert "available" in result and result["available"]


def test_definitions_have_direction_field():
    # Each definition should state which way "better" goes (no scientific claim,
    # just measurement semantics).
    for d in DEFINITIONS.values():
        assert d.get("direction")
