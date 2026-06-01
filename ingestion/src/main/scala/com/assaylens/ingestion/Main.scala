package com.assaylens.ingestion

import org.apache.spark.sql.SparkSession

/**
 * AssayLens Bronze ingestion entrypoint (lakehouse build).
 *
 * Reads the 5-target ChEMBL slice from the restored Postgres ChEMBL database
 * over JDBC ([[ChemblJdbcSource]], scope + nM normalization pushed down as SQL)
 * and writes Iceberg Bronze tables to the MinIO lakehouse via the `lake`
 * JdbcCatalog ([[WriteIceberg]]).
 *
 * All connection details have container-friendly defaults
 * (`host.docker.internal`) and are overridable by env var, so the job runs
 * unchanged in the JDK17 sbt container (see Makefile: `make bronze`).
 *
 * Usage:
 *   sbt "runMain com.assaylens.ingestion.Main"
 *   sbt "runMain com.assaylens.ingestion.Main --targets data/seeds/target_seed.csv"
 */
object Main {

  private final case class Args(seedPath: Option[String] = None)

  /** Resolve an env var with a default. */
  private def env(key: String, default: String): String = sys.env.getOrElse(key, default)

  def main(argv: Array[String]): Unit = {
    val args = parse(argv.toList, Args())

    // ---- Iceberg `lake` catalog (JdbcCatalog on iceberg_catalog + S3FileIO/MinIO) ----
    val spark = SparkSession.builder()
      .appName("assaylens-bronze-ingestion")
      .master(env("SPARK_MASTER", "local[*]"))
      .config("spark.sql.extensions", "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions")
      .config("spark.sql.catalog.lake", "org.apache.iceberg.spark.SparkCatalog")
      .config("spark.sql.catalog.lake.catalog-impl", "org.apache.iceberg.jdbc.JdbcCatalog")
      .config("spark.sql.catalog.lake.uri", env("LAKE_CATALOG_URI", "jdbc:postgresql://host.docker.internal:5432/iceberg_catalog"))
      .config("spark.sql.catalog.lake.jdbc.user", env("LAKE_CATALOG_USER", "assaylens"))
      .config("spark.sql.catalog.lake.jdbc.password", env("LAKE_CATALOG_PASSWORD", "assaylens"))
      .config("spark.sql.catalog.lake.warehouse", env("LAKE_WAREHOUSE", "s3://assaylens/lakehouse"))
      .config("spark.sql.catalog.lake.io-impl", "org.apache.iceberg.aws.s3.S3FileIO")
      .config("spark.sql.catalog.lake.s3.endpoint", env("S3_ENDPOINT", "http://host.docker.internal:9000"))
      .config("spark.sql.catalog.lake.s3.path-style-access", "true")
      .config("spark.sql.catalog.lake.s3.access-key-id", env("S3_ACCESS_KEY", "minioadmin"))
      .config("spark.sql.catalog.lake.s3.secret-access-key", env("S3_SECRET_KEY", "minioadmin"))
      .getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    val jdbc = JdbcConfig(
      url      = env("CHEMBL_JDBC_URL", "jdbc:postgresql://host.docker.internal:5432/assaylens"),
      user     = env("CHEMBL_JDBC_USER", "assaylens"),
      password = env("CHEMBL_JDBC_PASSWORD", "assaylens")
    )
    val namespace = env("LAKE_BRONZE_NAMESPACE", "lake.bronze")

    val targets = args.seedPath.map(TargetSeed.fromCsv).getOrElse(TargetSeed.default)
    val ids     = targets.map(_.targetChemblId)

    try {
      println(s"[Main] Bronze ingest: ${ids.size} targets -> $namespace (source: ${jdbc.url})")
      spark.sql(s"CREATE NAMESPACE IF NOT EXISTS $namespace")
      // The Spark Thrift Server opens sessions against the `default` namespace;
      // create it so dbt-spark can connect to the `lake` catalog from scratch.
      spark.sql("CREATE NAMESPACE IF NOT EXISTS lake.default")

      // Entity dir names map 1:1 to the raw.raw_chembl_<entity> contract that the
      // dbt-spark silver models read as source('bronze', '<entity>').
      WriteIceberg.write(ChemblJdbcSource.activity(spark, jdbc, ids), namespace, "activity")
      WriteIceberg.write(ChemblJdbcSource.molecule(spark, jdbc, ids), namespace, "molecule")
      WriteIceberg.write(ChemblJdbcSource.target(spark, jdbc, ids),   namespace, "target")
      WriteIceberg.write(ChemblJdbcSource.assay(spark, jdbc, ids),    namespace, "assay")
      WriteIceberg.write(ChemblJdbcSource.document(spark, jdbc, ids), namespace, "document")

      println("[Main] Bronze ingestion complete.")
    } finally {
      spark.stop()
    }
  }

  @annotation.tailrec
  private def parse(rest: List[String], acc: Args): Args = rest match {
    case Nil                      => acc
    case "--targets" :: p :: tail => parse(tail, acc.copy(seedPath = Some(p)))
    case other :: tail            =>
      System.err.println(s"[Main] ignoring unknown arg: $other"); parse(tail, acc)
  }
}
