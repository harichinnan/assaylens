package com.assaylens.ingestion

import org.apache.spark.sql.DataFrame

/**
 * Writes a DataFrame as an Iceberg Bronze table at `<namespace>.<entity>`
 * (e.g. `lake.bronze.activity`) in the MinIO-backed lakehouse.
 *
 * `createOrReplace` keeps Bronze a clean, reproducible snapshot of the latest
 * ingestion run — the same overwrite semantics the old Parquet lake had, but now
 * the table is a first-class Iceberg table registered in the `lake` JdbcCatalog,
 * so dbt-spark can read it as `source('bronze', ...)` downstream.
 *
 * The `lake` catalog must already be configured on the SparkSession (see Main)
 * and the namespace created (Main issues CREATE NAMESPACE IF NOT EXISTS).
 */
object WriteIceberg {

  def write(df: DataFrame, namespace: String, entity: String): Unit = {
    val table = s"$namespace.$entity"
    // Snapshot semantics: replace the table contents+schema each run. The 5-target
    // subset is tiny, so a full rewrite is cheap and avoids schema-drift surprises.
    df.writeTo(table).using("iceberg").createOrReplace()
    println(s"[WriteIceberg] wrote ${df.count()} rows -> $table")
  }
}
