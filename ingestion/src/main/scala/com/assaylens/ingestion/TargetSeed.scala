package com.assaylens.ingestion

import scala.io.Source

/** One seeded target of interest (the analysis is scoped to these). */
final case class SeedTarget(
    targetChemblId: String,
    geneSymbol: String,
    targetName: String,
    organism: String,
    targetType: String
)

/**
 * Reads `data/seeds/target_seed.csv`. This list is the entire ingestion scope:
 * every molecule / assay / activity / document pulled traces back to one of
 * these targets, keeping the local dataset small and reproducible.
 */
object TargetSeed {

  def fromCsv(path: String): Seq[SeedTarget] = {
    val src = Source.fromFile(path)
    try {
      val lines = src.getLines().toVector
      require(lines.nonEmpty, s"Seed file is empty: $path")
      // Skip header; CSV is simple (no embedded commas in our seed).
      lines.tail.filter(_.trim.nonEmpty).map { line =>
        val c = line.split(",", -1).map(_.trim)
        require(c.length >= 5, s"Malformed seed row: $line")
        SeedTarget(c(0), c(1), c(2), c(3), c(4))
      }
    } finally src.close()
  }

  /** Fallback used in --offline mode if no seed path is supplied. */
  val default: Seq[SeedTarget] = Seq(
    SeedTarget("CHEMBL203", "EGFR", "Epidermal growth factor receptor erbB1", "Homo sapiens", "SINGLE PROTEIN"),
    SeedTarget("CHEMBL1824", "ERBB2", "Receptor protein-tyrosine kinase erbB-2 (HER2)", "Homo sapiens", "SINGLE PROTEIN"),
    SeedTarget("CHEMBL5145", "BRAF", "Serine/threonine-protein kinase B-raf", "Homo sapiens", "SINGLE PROTEIN"),
    SeedTarget("CHEMBL2971", "JAK2", "Tyrosine-protein kinase JAK2", "Homo sapiens", "SINGLE PROTEIN"),
    SeedTarget("CHEMBL279", "KDR", "Vascular endothelial growth factor receptor 2 (VEGFR2)", "Homo sapiens", "SINGLE PROTEIN")
  )
}
