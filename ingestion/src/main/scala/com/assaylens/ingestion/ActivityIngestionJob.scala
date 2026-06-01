package com.assaylens.ingestion

import io.circe.Json
import org.apache.spark.sql.{DataFrame, SparkSession}

import com.assaylens.ingestion.JsonOps._

/** One raw activity (bioactivity measurement) row → raw.raw_chembl_activity. */
final case class RawActivity(
    activity_id: Option[Long],
    molecule_chembl_id: Option[String],
    target_chembl_id: Option[String],
    assay_chembl_id: Option[String],
    document_chembl_id: Option[String],
    standard_type: Option[String],
    standard_relation: Option[String],
    standard_value: Option[Double],
    standard_units: Option[String],
    standard_value_nm: Option[Double],
    units_note: Option[String],
    pchembl_value: Option[Double],
    activity_comment: Option[String],
    data_validity_comment: Option[String]
)

/**
 * Ingests activities for the seeded targets. This is the fact-grain extract:
 * one row per measurement. Unit normalization (→ nM) happens here so the lake
 * already carries a comparable value; dbt staging then only types/renames.
 */
object ActivityIngestionJob {

  def run(spark: SparkSession, client: ChemblClient, targets: Seq[SeedTarget]): DataFrame = {
    import spark.implicits._

    val raw: Vector[Json] =
      if (client == null) Vector.empty
      else
        targets.flatMap { t =>
          client.fetch(
            endpoint = "activity",
            collectionKey = ChemblClient.ActivityKey,
            params = Map("target_chembl_id" -> t.targetChemblId)
          )
        }.toVector

    val rows = raw.map { j =>
      val value = j.dbl("standard_value")
      val units = j.str("standard_units")
      val norm = NormalizeUnits.normalize(value, units)
      RawActivity(
        activity_id = j.hcursor.downField("activity_id").as[Long].toOption,
        molecule_chembl_id = j.str("molecule_chembl_id"),
        target_chembl_id = j.str("target_chembl_id"),
        assay_chembl_id = j.str("assay_chembl_id"),
        document_chembl_id = j.str("document_chembl_id"),
        standard_type = j.str("standard_type"),
        standard_relation = j.str("standard_relation"),
        standard_value = value,
        standard_units = units,
        standard_value_nm = norm.valueNm,
        units_note = norm.note,
        pchembl_value = j.dbl("pchembl_value"),
        activity_comment = j.str("activity_comment"),
        data_validity_comment = j.str("data_validity_comment")
      )
    }

    rows.toDF()
  }
}
