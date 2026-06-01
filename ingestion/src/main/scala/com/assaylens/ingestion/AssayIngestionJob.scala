package com.assaylens.ingestion

import io.circe.Json
import org.apache.spark.sql.{DataFrame, SparkSession}

import com.assaylens.ingestion.JsonOps._

/** One assay → raw.raw_chembl_assay. */
final case class RawAssay(
    assay_chembl_id: Option[String],
    assay_type: Option[String],
    assay_description: Option[String],
    confidence_score: Option[Int],
    target_chembl_id: Option[String]
)

/**
 * Ingests assays referenced by the activity extract. `assayIds` is normally the
 * distinct set of assay_chembl_id values from ActivityIngestionJob.
 */
object AssayIngestionJob {

  def run(spark: SparkSession, client: ChemblClient, assayIds: Seq[String]): DataFrame = {
    import spark.implicits._

    val raw: Vector[Json] =
      if (client == null) Vector.empty
      else if (assayIds.isEmpty) client.fetch("assay", ChemblClient.AssayKey, Map.empty)
      else
        assayIds.grouped(20).flatMap { batch =>
          client.fetch("assay", ChemblClient.AssayKey, Map("assay_chembl_id__in" -> batch.mkString(",")))
        }.toVector

    val rows = raw.map { j =>
      RawAssay(
        assay_chembl_id = j.str("assay_chembl_id"),
        assay_type = j.str("assay_type"),
        assay_description = j.str("description"),
        confidence_score = j.int("confidence_score"),
        target_chembl_id = j.str("target_chembl_id")
      )
    }

    rows.toDF()
  }
}
