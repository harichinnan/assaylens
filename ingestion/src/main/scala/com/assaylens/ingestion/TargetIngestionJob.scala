package com.assaylens.ingestion

import org.apache.spark.sql.{DataFrame, SparkSession}

import com.assaylens.ingestion.JsonOps._

/** One target → raw.raw_chembl_target. */
final case class RawTarget(
    target_chembl_id: Option[String],
    target_name: Option[String],
    organism: Option[String],
    target_type: Option[String]
)

/**
 * Ingests the seeded targets. We could call ChEMBL here, but since the scope IS
 * the seed list, in offline mode we project directly from it; in live mode we
 * enrich each from the /target endpoint (pref_name/organism may differ from the
 * seed). Both paths produce the same shape.
 */
object TargetIngestionJob {

  def run(spark: SparkSession, client: ChemblClient, targets: Seq[SeedTarget]): DataFrame = {
    import spark.implicits._

    val rows: Seq[RawTarget] =
      if (client == null)
        targets.map(t => RawTarget(Some(t.targetChemblId), Some(t.targetName), Some(t.organism), Some(t.targetType)))
      else
        targets.flatMap { t =>
          val fetched = client.fetch("target", ChemblClient.TargetKey,
            Map("target_chembl_id" -> t.targetChemblId))
          fetched.headOption match {
            case Some(j) =>
              Some(RawTarget(
                target_chembl_id = j.str("target_chembl_id").orElse(Some(t.targetChemblId)),
                target_name = j.str("pref_name").orElse(Some(t.targetName)),
                organism = j.str("organism").orElse(Some(t.organism)),
                target_type = j.str("target_type").orElse(Some(t.targetType))
              ))
            // Fall back to the seed if the endpoint returned nothing.
            case None =>
              Some(RawTarget(Some(t.targetChemblId), Some(t.targetName), Some(t.organism), Some(t.targetType)))
          }
        }

    rows.toDF()
  }
}
