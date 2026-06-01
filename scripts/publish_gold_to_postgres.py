"""Publisher: copy every lake.gold.* Iceberg table into native Postgres marts.*.

This is the serving step of the medallion: the gold Iceberg marts become plain
Postgres tables that Metabase, Elasticsearch indexing, and the LangGraph agent
(read-only role agent_ro) query. Tables are discovered dynamically, so newly
added gold models (e.g. the graph_* relationship marts) publish automatically.

Overwrite semantics: each marts.<table> is replaced each run, keeping the
serving store a faithful snapshot of the latest gold build.
"""
import os
from pyspark.sql import SparkSession

PG_URL = os.environ.get("PG_URL", "jdbc:postgresql://host.docker.internal:5432/assaylens")
PG_PROPS = {
    "user": os.environ.get("PG_USER", "assaylens"),
    "password": os.environ.get("PG_PASSWORD", "assaylens"),
    "driver": "org.postgresql.Driver",
    # Let Spark create marts.<t> in the existing (assaylens-owned) marts schema.
    "stringtype": "unspecified",
}


def main() -> None:
    spark = SparkSession.builder.appName("assaylens-publisher").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    tables = [r.tableName for r in spark.sql("SHOW TABLES IN lake.gold").collect()]
    print(f"[publish] {len(tables)} gold tables -> marts.*: {sorted(tables)}")

    for t in sorted(tables):
        df = spark.table(f"lake.gold.{t}")
        n = df.count()
        df.write.mode("overwrite").jdbc(PG_URL, f"marts.{t}", properties=PG_PROPS)
        print(f"[publish] marts.{t} <- lake.gold.{t} ({n} rows)")

    spark.stop()


if __name__ == "__main__":
    main()
