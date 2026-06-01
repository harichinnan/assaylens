package com.assaylens.ingestion

/**
 * Unit normalization for bioactivity values.
 *
 * ChEMBL `standard_units` vary (nM, uM, M, mM, pM, ...). The warehouse needs a
 * single comparable scale, so we normalize concentration-like measurements to
 * **nanomolar (nM)** and expose it as `standard_value_nm`.
 *
 * Anything we cannot confidently convert (e.g. %, unitless, ug.mL-1 without a
 * molecular weight) is left as null nM and flagged, so downstream data-quality
 * checks and the curated mart can exclude it rather than silently mis-compare.
 *
 * This is intentionally conservative — correctness over coverage. We do NOT
 * attempt mass/volume → molar conversions that require molecular weight here.
 */
object NormalizeUnits {

  /** Multiplicative factor to convert a value in `unit` to nM, if known. */
  private val toNanomolar: Map[String, Double] = Map(
    "M"  -> 1e9,
    "mM" -> 1e6,
    "uM" -> 1e3,
    "µM" -> 1e3,
    "nM" -> 1.0,
    "pM" -> 1e-3,
    "fM" -> 1e-6
  )

  final case class Normalized(valueNm: Option[Double], unitsClean: Option[String], note: Option[String])

  def normalize(value: Option[Double], units: Option[String]): Normalized = {
    val cleanUnit = units.map(_.trim)
    (value, cleanUnit) match {
      case (Some(v), Some(u)) if toNanomolar.contains(u) =>
        Normalized(Some(v * toNanomolar(u)), Some("nM"), None)
      case (None, _) =>
        Normalized(None, cleanUnit, Some("missing_standard_value"))
      case (_, None) | (_, Some("")) =>
        Normalized(None, None, Some("missing_standard_units"))
      case (_, Some(u)) =>
        // Known-but-unconvertible (%, ug.mL-1, unitless, ...). Keep flagged.
        Normalized(None, Some(u), Some(s"unconvertible_units:$u"))
    }
  }
}
