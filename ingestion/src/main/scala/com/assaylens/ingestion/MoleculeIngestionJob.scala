package com.assaylens.ingestion

import io.circe.Json
import org.apache.spark.sql.{DataFrame, SparkSession}

import com.assaylens.ingestion.JsonOps._

/** One molecule → raw.raw_chembl_molecule. */
final case class RawMolecule(
    molecule_chembl_id: Option[String],
    pref_name: Option[String],
    canonical_smiles: Option[String],
    molecular_weight: Option[Double],
    alogp: Option[Double],
    hba: Option[Int],
    hbd: Option[Int],
    ro5_violations: Option[Int]
)

/**
 * Ingests molecules for the compounds observed in the activity extract.
 * Molecule properties live under `molecule_properties` /
 * `molecule_structures` in the ChEMBL payload.
 *
 * `moleculeIds` is normally the distinct set of molecule_chembl_id values from
 * ActivityIngestionJob, so we only pull compounds we actually have data for.
 */
object MoleculeIngestionJob {

  def run(
      spark: SparkSession,
      client: ChemblClient,
      moleculeIds: Seq[String]
  ): DataFrame = {
    import spark.implicits._

    val raw: Vector[Json] =
      if (client == null) Vector.empty
      else if (moleculeIds.isEmpty) client.fetch("molecule", ChemblClient.MoleculeKey, Map.empty)
      else
        // ChEMBL supports filtering by a set: molecule_chembl_id__in=ID1,ID2,...
        moleculeIds.grouped(20).flatMap { batch =>
          client.fetch(
            "molecule",
            ChemblClient.MoleculeKey,
            Map("molecule_chembl_id__in" -> batch.mkString(","))
          )
        }.toVector

    val rows = raw.map { j =>
      val props = j.hcursor.downField("molecule_properties").focus.getOrElse(Json.Null)
      val struct = j.hcursor.downField("molecule_structures").focus.getOrElse(Json.Null)
      RawMolecule(
        molecule_chembl_id = j.str("molecule_chembl_id"),
        pref_name = j.str("pref_name"),
        canonical_smiles = struct.str("canonical_smiles"),
        molecular_weight = props.dbl("full_mwt").orElse(props.dbl("mw_freebase")),
        alogp = props.dbl("alogp"),
        hba = props.int("hba"),
        hbd = props.int("hbd"),
        ro5_violations = props.int("num_ro5_violations")
      )
    }

    rows.toDF()
  }
}
