package com.assaylens.ingestion

import io.circe.Json

/** Small null-safe accessors for projecting ChEMBL JSON records into typed rows. */
object JsonOps {
  implicit final class RichJson(val j: Json) extends AnyVal {
    def str(field: String): Option[String] =
      j.hcursor.downField(field).as[String].toOption.filter(_.nonEmpty)

    def dbl(field: String): Option[Double] =
      (j.hcursor.downField(field).as[Double].toOption
        .orElse(j.hcursor.downField(field).as[String].toOption.flatMap(s => scala.util.Try(s.toDouble).toOption)))
        // Drop NaN/Infinity so JSON null/garbage becomes a true null in the lake,
        // not a NaN that would slip past `is null` checks downstream.
        .filter(d => !d.isNaN && !d.isInfinite)

    def int(field: String): Option[Int] =
      j.hcursor.downField(field).as[Int].toOption
        .orElse(j.hcursor.downField(field).as[String].toOption.flatMap(s => scala.util.Try(s.toInt).toOption))
  }
}
