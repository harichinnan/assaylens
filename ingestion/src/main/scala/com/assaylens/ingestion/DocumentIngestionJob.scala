package com.assaylens.ingestion

import io.circe.Json
import org.apache.spark.sql.{DataFrame, SparkSession}

import com.assaylens.ingestion.JsonOps._

/** One document/publication → raw.raw_chembl_document. */
final case class RawDocument(
    document_chembl_id: Option[String],
    pubmed_id: Option[Int],
    journal: Option[String],
    year: Option[Int]
)

/**
 * Ingests documents referenced by the activity extract — the publication
 * lineage for each measurement. `documentIds` is normally the distinct set of
 * document_chembl_id values from ActivityIngestionJob.
 */
object DocumentIngestionJob {

  def run(spark: SparkSession, client: ChemblClient, documentIds: Seq[String]): DataFrame = {
    import spark.implicits._

    val raw: Vector[Json] =
      if (client == null) Vector.empty
      else if (documentIds.isEmpty) client.fetch("document", ChemblClient.DocumentKey, Map.empty)
      else
        documentIds.grouped(20).flatMap { batch =>
          client.fetch("document", ChemblClient.DocumentKey, Map("document_chembl_id__in" -> batch.mkString(",")))
        }.toVector

    val rows = raw.map { j =>
      RawDocument(
        document_chembl_id = j.str("document_chembl_id"),
        pubmed_id = j.int("pubmed_id"),
        journal = j.str("journal"),
        year = j.int("year")
      )
    }

    rows.toDF()
  }
}
