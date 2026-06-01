-- =============================================================================
-- Extract raw.raw_chembl_* from a locally-restored full ChEMBL database.
--
-- This is the alternative to the Scala/REST ingestion: when the official ChEMBL
-- Postgres release has been restored into this database's `public` schema, this
-- script builds the same raw contract the dbt project expects, scoped to the
-- five seeded kinase targets. It replicates the nM unit-normalization from
-- ingestion/.../NormalizeUnits.scala so downstream staging/marts are unchanged.
--
-- Usage: psql -d assaylens -f scripts/extract_raw_from_chembl.sql
-- =============================================================================

\set ON_ERROR_STOP on
SET statement_timeout = 0;

CREATE SCHEMA IF NOT EXISTS raw;

-- The analysis scope: the five seeded kinase targets
-- (EGFR, HER2/ERBB2, BRAF, JAK2, VEGFR2/KDR). Temp tables live for the
-- transaction below so the heavy joins are computed once.
BEGIN;
CREATE TEMP TABLE _scope_tid ON COMMIT DROP AS
SELECT tid, chembl_id AS target_chembl_id, pref_name, organism, target_type
FROM public.target_dictionary
WHERE chembl_id IN ('CHEMBL203','CHEMBL1824','CHEMBL5145','CHEMBL2971','CHEMBL279');

CREATE TEMP TABLE _scope_assay ON COMMIT DROP AS
SELECT a.assay_id, a.chembl_id AS assay_chembl_id, a.assay_type,
       a.description AS assay_description, a.confidence_score,
       t.target_chembl_id, a.doc_id
FROM public.assays a
JOIN _scope_tid t ON a.tid = t.tid;
CREATE INDEX ON _scope_assay(assay_id);
ANALYZE _scope_assay;

-- Materialize the in-scope molecule + document id sets ONCE (with stats), so the
-- molecule/document joins below are index-driven rather than mis-planned
-- seq scans over the 2.9M-row compound tables.
CREATE TEMP TABLE _scope_molregno ON COMMIT DROP AS
SELECT DISTINCT act.molregno
FROM public.activities act
JOIN _scope_assay sa ON act.assay_id = sa.assay_id;
CREATE INDEX ON _scope_molregno(molregno);
ANALYZE _scope_molregno;

CREATE TEMP TABLE _scope_docid ON COMMIT DROP AS
SELECT DISTINCT doc_id FROM (
    SELECT doc_id FROM _scope_assay WHERE doc_id IS NOT NULL
    UNION
    SELECT act.doc_id FROM public.activities act
    JOIN _scope_assay sa ON act.assay_id = sa.assay_id
    WHERE act.doc_id IS NOT NULL
) z;
CREATE INDEX ON _scope_docid(doc_id);
ANALYZE _scope_docid;

-- ---- dim source: targets -----------------------------------------------------
DROP TABLE IF EXISTS raw.raw_chembl_target CASCADE;
CREATE TABLE raw.raw_chembl_target AS
SELECT target_chembl_id, pref_name AS target_name, organism, target_type
FROM _scope_tid;

-- ---- dim source: assays ------------------------------------------------------
DROP TABLE IF EXISTS raw.raw_chembl_assay CASCADE;
CREATE TABLE raw.raw_chembl_assay AS
SELECT assay_chembl_id, assay_type, assay_description,
       confidence_score::int AS confidence_score, target_chembl_id
FROM _scope_assay;

-- ---- fact source: activities (with nM normalization) -------------------------
DROP TABLE IF EXISTS raw.raw_chembl_activity CASCADE;
CREATE TABLE raw.raw_chembl_activity AS
SELECT
    act.activity_id,
    md.chembl_id            AS molecule_chembl_id,
    sa.target_chembl_id,
    sa.assay_chembl_id,
    d.chembl_id             AS document_chembl_id,
    act.standard_type,
    act.standard_relation,
    act.standard_value::double precision AS standard_value,
    act.standard_units,
    -- normalize concentration-like units to nanomolar (nM); else NULL
    (CASE act.standard_units
        WHEN 'M'  THEN act.standard_value * 1e9
        WHEN 'mM' THEN act.standard_value * 1e6
        WHEN 'uM' THEN act.standard_value * 1e3
        WHEN 'µM' THEN act.standard_value * 1e3
        WHEN 'nM' THEN act.standard_value * 1.0
        WHEN 'pM' THEN act.standard_value * 1e-3
        WHEN 'fM' THEN act.standard_value * 1e-6
        ELSE NULL
     END)::double precision AS standard_value_nm,
    (CASE
        WHEN act.standard_value IS NULL THEN 'missing_standard_value'
        WHEN act.standard_units IS NULL OR act.standard_units = '' THEN 'missing_standard_units'
        WHEN act.standard_units IN ('M','mM','uM','µM','nM','pM','fM') THEN NULL
        ELSE 'unconvertible_units:' || act.standard_units
     END) AS units_note,
    act.pchembl_value::double precision AS pchembl_value,
    act.activity_comment,
    act.data_validity_comment
FROM public.activities act
JOIN _scope_assay sa            ON act.assay_id = sa.assay_id
JOIN public.molecule_dictionary md ON act.molregno = md.molregno
LEFT JOIN public.docs d         ON act.doc_id = d.doc_id;

-- ---- dim source: molecules (only compounds in scope) -------------------------
DROP TABLE IF EXISTS raw.raw_chembl_molecule CASCADE;
CREATE TABLE raw.raw_chembl_molecule AS
SELECT DISTINCT
    md.chembl_id AS molecule_chembl_id,
    md.pref_name,
    cs.canonical_smiles,
    COALESCE(cp.full_mwt, cp.mw_freebase)::double precision AS molecular_weight,
    cp.alogp::double precision AS alogp,
    cp.hba::int  AS hba,
    cp.hbd::int  AS hbd,
    cp.num_ro5_violations::int AS ro5_violations
FROM public.molecule_dictionary md
LEFT JOIN public.compound_structures cs ON md.molregno = cs.molregno
LEFT JOIN public.compound_properties cp ON md.molregno = cp.molregno
WHERE md.molregno IN (SELECT molregno FROM _scope_molregno);

-- ---- dim source: documents (only docs in scope) -----------------------------
DROP TABLE IF EXISTS raw.raw_chembl_document CASCADE;
CREATE TABLE raw.raw_chembl_document AS
SELECT DISTINCT
    d.chembl_id AS document_chembl_id,
    d.pubmed_id::int AS pubmed_id,
    d.journal,
    d.year::int AS year
FROM public.docs d
WHERE d.doc_id IN (SELECT doc_id FROM _scope_docid);

COMMIT;

-- ---- report ------------------------------------------------------------------
SELECT 'raw_chembl_activity' AS t, count(*) FROM raw.raw_chembl_activity
UNION ALL SELECT 'raw_chembl_molecule', count(*) FROM raw.raw_chembl_molecule
UNION ALL SELECT 'raw_chembl_target',   count(*) FROM raw.raw_chembl_target
UNION ALL SELECT 'raw_chembl_assay',    count(*) FROM raw.raw_chembl_assay
UNION ALL SELECT 'raw_chembl_document', count(*) FROM raw.raw_chembl_document
ORDER BY 1;
