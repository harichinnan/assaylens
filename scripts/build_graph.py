"""Spark graph job: derive GOLD relationship tables from the curated potency mart.

Reads lake.gold.mart_compound_target_potency (the comparable evidence surface)
and writes two Iceberg relationship marts back into GOLD:

  lake.gold.graph_compound_target_edge
      One edge per (compound, target): best pChEMBL / strongest nM potency and
      the supporting measurement count. The bipartite compound<->target graph.

  lake.gold.graph_target_similarity
      One undirected edge per target pair that shares >=1 curated compound,
      weighted by the number of shared compounds (+ Jaccard over their curated
      compound sets). The target-target "tested-together" similarity graph.

These feed the future relationship dashboard / ES relationship index, and are
published to native Postgres marts.* alongside the other gold tables.
"""
from pyspark.sql import SparkSession, functions as F


def main() -> None:
    spark = SparkSession.builder.appName("assaylens-graph").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    curated = spark.table("lake.gold.mart_compound_target_potency")

    # ---- compound <-> target edges -----------------------------------------
    edges = (
        curated.groupBy(
            "molecule_chembl_id", "compound_name",
            "target_chembl_id", "target_name",
        )
        .agg(
            F.max("pchembl_value").alias("best_pchembl"),
            F.min("standard_value_nm").alias("best_potency_nm"),
            F.count(F.lit(1)).alias("n_measurements"),
        )
    )
    edges.writeTo("lake.gold.graph_compound_target_edge").using("iceberg").createOrReplace()
    print(f"[graph] graph_compound_target_edge: {edges.count()} edges")

    # ---- target <-> target similarity (shared curated compounds) -----------
    # Per-target curated compound set + size, for the Jaccard denominator.
    ct = curated.select("molecule_chembl_id", "target_chembl_id", "target_name").distinct()
    tsize = ct.groupBy("target_chembl_id").agg(
        F.countDistinct("molecule_chembl_id").alias("n_compounds")
    )

    a = ct.alias("a")
    b = ct.alias("b")
    pairs = (
        a.join(
            b,
            (F.col("a.molecule_chembl_id") == F.col("b.molecule_chembl_id"))
            & (F.col("a.target_chembl_id") < F.col("b.target_chembl_id")),
        )
        .groupBy(
            F.col("a.target_chembl_id").alias("target_a"),
            F.col("a.target_name").alias("target_a_name"),
            F.col("b.target_chembl_id").alias("target_b"),
            F.col("b.target_name").alias("target_b_name"),
        )
        .agg(F.countDistinct("a.molecule_chembl_id").alias("shared_compounds"))
    )

    sa = tsize.alias("sa")
    sb = tsize.alias("sb")
    similarity = (
        pairs.join(sa, F.col("target_a") == F.col("sa.target_chembl_id"))
        .join(sb, F.col("target_b") == F.col("sb.target_chembl_id"))
        .withColumn(
            "jaccard",
            F.col("shared_compounds")
            / (F.col("sa.n_compounds") + F.col("sb.n_compounds") - F.col("shared_compounds")),
        )
        .select(
            "target_a", "target_a_name", "target_b", "target_b_name",
            "shared_compounds",
            F.round("jaccard", 4).alias("jaccard"),
        )
    )
    similarity.writeTo("lake.gold.graph_target_similarity").using("iceberg").createOrReplace()
    print(f"[graph] graph_target_similarity: {similarity.count()} target-pair edges")

    spark.stop()


if __name__ == "__main__":
    main()
