// =============================================================================
// AssayLens ingestion — Scala Spark project
//
// Reads the 5-target ChEMBL slice from the restored Postgres ChEMBL DB over JDBC
// (scope + nM normalization pushed down as SQL) and writes Iceberg Bronze tables
// to the MinIO lakehouse via the `lake` JdbcCatalog.
//
//   # run inside the JDK17 sbt container (see Makefile: make bronze)
//   sbt "runMain com.assaylens.ingestion.Main"
//
// The legacy ChEMBL REST client (ChemblClient + *IngestionJob) is retained for
// reference but no longer on the Main path.
// =============================================================================

ThisBuild / scalaVersion := "2.12.18" // matches Spark 3.5 Scala line
ThisBuild / organization := "com.assaylens"
ThisBuild / version      := "0.1.0"

lazy val sparkVersion   = "3.5.1"
lazy val icebergVersion = "1.6.1"
lazy val circeVersion   = "0.14.6"
lazy val sttpVersion    = "3.9.5"

lazy val root = (project in file("."))
  .settings(
    name := "assaylens-ingestion",
    libraryDependencies ++= Seq(
      // Spark — "provided" on a real cluster; kept compile-scope for local sbt run.
      "org.apache.spark" %% "spark-core" % sparkVersion,
      "org.apache.spark" %% "spark-sql"  % sparkVersion,

      // Iceberg medallion lakehouse: Spark runtime + AWS bundle (S3FileIO for MinIO).
      "org.apache.iceberg" % "iceberg-spark-runtime-3.5_2.12" % icebergVersion,
      "org.apache.iceberg" % "iceberg-aws-bundle"             % icebergVersion,

      // Postgres JDBC: ChEMBL-restore reads, Iceberg JdbcCatalog, publisher writes.
      "org.postgresql" % "postgresql" % "42.7.3",

      // HTTP client for the ChEMBL REST API.
      "com.softwaremill.sttp.client3" %% "core"  % sttpVersion,

      // JSON parsing for ChEMBL responses + sample fixtures.
      "io.circe" %% "circe-core"    % circeVersion,
      "io.circe" %% "circe-generic" % circeVersion,
      "io.circe" %% "circe-parser"  % circeVersion,

      // Tests
      "org.scalatest" %% "scalatest" % "3.2.18" % Test
    ),
    // Spark needs these JVM flags on JDK 17.
    Compile / run / fork := true,
    Compile / run / javaOptions ++= Seq(
      "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED",
      "--add-opens=java.base/java.nio=ALL-UNNAMED",
      "--add-opens=java.base/java.lang=ALL-UNNAMED",
      "--add-opens=java.base/java.util=ALL-UNNAMED"
    ),
    // Avoid assembly-merge headaches if you later add sbt-assembly.
    Compile / mainClass := Some("com.assaylens.ingestion.Main")
  )
