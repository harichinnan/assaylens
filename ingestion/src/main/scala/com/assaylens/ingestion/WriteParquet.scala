package com.assaylens.ingestion

import org.apache.spark.sql.{DataFrame, SaveMode}

/**
 * Writes a DataFrame to the Parquet lake at <out>/<entity>/.
 *
 * Overwrite semantics keep the lake a clean, reproducible snapshot of the
 * latest ingestion run — the raw schema in Postgres is rebuilt from it via
 * scripts/load_parquet_to_postgres.py.
 */
object WriteParquet {

  def write(df: DataFrame, outDir: String, entity: String): Unit = {
    val path = s"$outDir/$entity"
    // coalesce(1): the local subset is tiny; one file per entity is convenient
    // for the Python loader. Drop this on a real cluster.
    df.coalesce(1)
      .write
      .mode(SaveMode.Overwrite)
      .parquet(path)
    println(s"[WriteParquet] wrote ${df.count()} rows -> $path")
  }
}
