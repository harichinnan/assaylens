"""Unit tests for the SQL guardrails.

Run from the repo root:  pytest -q tests/
(The agent package is importable because conftest.py adds agent/ to sys.path.)
"""
import pytest

from app.guardrails.sql_guardrails import SqlGuardrailError, validate_sql


# ---- queries that must be REJECTED -----------------------------------------

@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE marts.mart_compound_target_potency",
        "DELETE FROM marts.mart_compound_target_potency",
        "UPDATE marts.mart_compound_target_potency SET pchembl_value = 0",
        "INSERT INTO marts.mart_compound_target_potency VALUES (1)",
        "CREATE TABLE foo AS SELECT 1",
        "ALTER TABLE marts.dim_target ADD COLUMN x int",
        "TRUNCATE marts.mart_assay_quality",
        "GRANT SELECT ON marts.dim_target TO public",
        "SELECT 1; DROP TABLE marts.dim_target",          # stacked
        "COPY marts.dim_target TO '/tmp/x.csv'",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT * FROM pg_catalog.pg_tables",
        "SELECT * FROM information_schema.tables",
        "SELECT * FROM raw.raw_chembl_activity",          # raw not allow-listed
        "SELECT * FROM staging.stg_activity",             # staging not allow-listed
        "SELECT * FROM marts.fact_bioactivity_result",    # fact reachable only via lineage tool
        "CREATE EXTENSION dblink",
        "",
        "   ",
    ],
)
def test_rejected(sql):
    with pytest.raises(SqlGuardrailError):
        validate_sql(sql)


# ---- queries that must be ACCEPTED -----------------------------------------

def test_simple_select_gets_limit_injected():
    v = validate_sql("SELECT * FROM mart_compound_target_potency")
    assert "limit" in v.sql.lower()
    assert v.limit > 0
    assert "mart_compound_target_potency" in v.referenced_tables


def test_schema_qualified_mart_allowed():
    v = validate_sql("SELECT target_chembl_id FROM marts.mart_target_activity_summary")
    assert "mart_target_activity_summary" in v.referenced_tables


def test_cte_alias_not_treated_as_table():
    sql = """
        WITH t AS (SELECT * FROM mart_compound_target_potency)
        SELECT molecule_chembl_id FROM t
    """
    v = validate_sql(sql)
    # 't' is a CTE alias and must not be rejected as an unknown table.
    assert v.limit > 0


def test_existing_limit_capped_to_max():
    v = validate_sql("SELECT * FROM mart_compound_profile LIMIT 100000")
    # capped to configured SQL_MAX_ROWS (default 200)
    assert v.limit <= 200
    assert f"LIMIT {v.limit}".lower() in v.sql.lower()


def test_join_of_two_allowed_marts():
    sql = (
        "SELECT a.target_chembl_id FROM mart_target_activity_summary a "
        "JOIN dim_target d ON a.target_chembl_id = d.target_chembl_id"
    )
    v = validate_sql(sql)
    assert set(v.referenced_tables) >= {"mart_target_activity_summary", "dim_target"}


def test_comment_smuggled_ddl_is_caught():
    # Comments are stripped before validation, so this is a plain SELECT.
    v = validate_sql("SELECT 1 AS x FROM dim_target -- DROP TABLE dim_target")
    assert "drop" not in v.sql.lower()
