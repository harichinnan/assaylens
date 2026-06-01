package com.assaylens.ingestion

import org.apache.spark.sql.{DataFrame, SparkSession}

/**
 * Bronze source: reads the 5-target ChEMBL slice directly from the restored
 * Postgres ChEMBL database over Spark JDBC.
 *
 * The scope (5 seeded kinase targets), the join graph, and the nanomolar (nM)
 * unit normalization are all pushed DOWN into Postgres as SQL subqueries — this
 * is a SQL port of `scripts/extract_raw_from_chembl.sql`, so the DataFrames
 * carry exactly the `raw.raw_chembl_*` contract the dbt staging models expect.
 * Pushing the heavy joins to Postgres (which has ChEMBL's indexes) keeps Spark's
 * job to a thin extract over a few-thousand-row result set per entity.
 *
 * Replaces the REST-based *IngestionJob path for the lakehouse build.
 */
final case class JdbcConfig(url: String, user: String, password: String)

object ChemblJdbcSource {

  /** Reads one entity via a pushdown subquery (no Spark-side partitioning needed
    * — each scoped result is small). */
  private def read(spark: SparkSession, jdbc: JdbcConfig, sql: String): DataFrame =
    spark.read
      .format("jdbc")
      .option("driver", "org.postgresql.Driver")
      .option("url", jdbc.url)
      .option("user", jdbc.user)
      .option("password", jdbc.password)
      // Wrap the query as a derived table; Postgres plans + executes it.
      .option("dbtable", s"($sql) AS extract")
      .load()

  /** SQL IN-list of single-quoted target ChEMBL ids. The ids are fixed seed
    * constants (no user input), so simple quoting is safe. */
  private def inList(targetChemblIds: Seq[String]): String =
    targetChemblIds.map(id => s"'$id'").mkString(", ")

  def target(spark: SparkSession, jdbc: JdbcConfig, ids: Seq[String]): DataFrame =
    read(spark, jdbc, s"""
      SELECT chembl_id AS target_chembl_id, pref_name AS target_name, organism, target_type
      FROM public.target_dictionary
      WHERE chembl_id IN (${inList(ids)})
    """)

  def assay(spark: SparkSession, jdbc: JdbcConfig, ids: Seq[String]): DataFrame =
    read(spark, jdbc, s"""
      SELECT a.chembl_id AS assay_chembl_id, a.assay_type,
             a.description AS assay_description,
             a.confidence_score::int AS confidence_score,
             t.chembl_id AS target_chembl_id
      FROM public.assays a
      JOIN public.target_dictionary t ON a.tid = t.tid
      WHERE t.chembl_id IN (${inList(ids)})
    """)

  /** Fact grain: one row per activity, with concentration units normalized to nM
    * (verbatim port of NormalizeUnits / extract_raw_from_chembl.sql). */
  def activity(spark: SparkSession, jdbc: JdbcConfig, ids: Seq[String]): DataFrame =
    read(spark, jdbc, s"""
      WITH scope_assay AS (
        SELECT a.assay_id, a.chembl_id AS assay_chembl_id,
               t.chembl_id AS target_chembl_id
        FROM public.assays a
        JOIN public.target_dictionary t ON a.tid = t.tid
        WHERE t.chembl_id IN (${inList(ids)})
      )
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
      JOIN scope_assay sa                ON act.assay_id = sa.assay_id
      JOIN public.molecule_dictionary md ON act.molregno = md.molregno
      LEFT JOIN public.docs d            ON act.doc_id   = d.doc_id
    """)

  def molecule(spark: SparkSession, jdbc: JdbcConfig, ids: Seq[String]): DataFrame =
    read(spark, jdbc, s"""
      WITH scope_molregno AS (
        SELECT DISTINCT act.molregno
        FROM public.activities act
        JOIN public.assays a            ON act.assay_id = a.assay_id
        JOIN public.target_dictionary t ON a.tid = t.tid
        WHERE t.chembl_id IN (${inList(ids)})
      )
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
      WHERE md.molregno IN (SELECT molregno FROM scope_molregno)
    """)

  def document(spark: SparkSession, jdbc: JdbcConfig, ids: Seq[String]): DataFrame =
    read(spark, jdbc, s"""
      WITH scope_docid AS (
        SELECT DISTINCT doc_id FROM (
          SELECT a.doc_id
          FROM public.assays a
          JOIN public.target_dictionary t ON a.tid = t.tid
          WHERE t.chembl_id IN (${inList(ids)}) AND a.doc_id IS NOT NULL
          UNION
          SELECT act.doc_id
          FROM public.activities act
          JOIN public.assays a            ON act.assay_id = a.assay_id
          JOIN public.target_dictionary t ON a.tid = t.tid
          WHERE t.chembl_id IN (${inList(ids)}) AND act.doc_id IS NOT NULL
        ) z
      )
      SELECT DISTINCT
        d.chembl_id AS document_chembl_id,
        d.pubmed_id::int AS pubmed_id,
        d.journal,
        d.year::int AS year
      FROM public.docs d
      WHERE d.doc_id IN (SELECT doc_id FROM scope_docid)
    """)
}
