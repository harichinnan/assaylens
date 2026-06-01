package com.assaylens.ingestion

import io.circe.{Json, parser}
import sttp.client3._

import java.net.http.HttpClient
import java.time.Duration
import scala.annotation.tailrec
import scala.io.Source

/**
 * Thin client over the ChEMBL REST API (https://www.ebi.ac.uk/chembl/api/data).
 *
 * Two modes:
 *  - live    : paginated HTTP GETs against ChEMBL, scoped to the seeded targets.
 *  - offline : reads bundled JSON fixtures from src/main/resources/sample/,
 *              so the whole pipeline runs with no network (CI / demo).
 *
 * Returns raw JSON objects (one per ChEMBL record). The per-entity ingestion
 * jobs are responsible for projecting these into typed Spark DataFrames — this
 * client deliberately does NOT model the schema, keeping extraction and
 * transformation cleanly separated.
 */
final class ChemblClient(
    baseUrl: String = "https://www.ebi.ac.uk/chembl/api/data",
    offline: Boolean = false,
    pageLimit: Int = 1000,
    maxRecords: Int = 0          // 0 = unlimited; otherwise cap rows per fetch() call
) {

  // Force HTTP/1.1: ChEMBL's server sends an HTTP/2 GOAWAY to the JVM's default
  // HttpClient, aborting requests. HTTP/1.1 is reliable here.
  private val javaClient = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_1_1)
    .connectTimeout(Duration.ofSeconds(30))
    .build()
  private val backend = HttpClientSyncBackend.usingClient(javaClient)

  /** ChEMBL paginates list endpoints under a top-level key (e.g. "activities"). */
  def fetch(endpoint: String, collectionKey: String, params: Map[String, String]): Vector[Json] =
    if (offline) applyFilters(readFixture(collectionKey), params)
    else fetchPaged(endpoint, collectionKey, params)

  // --- live mode -------------------------------------------------------------

  @tailrec
  private def fetchPaged(
      endpoint: String,
      collectionKey: String,
      params: Map[String, String],
      offset: Int = 0,
      acc: Vector[Json] = Vector.empty
  ): Vector[Json] = {
    val query = params + ("format" -> "json", "limit" -> pageLimit.toString, "offset" -> offset.toString)
    val uri = uri"$baseUrl/$endpoint".addParams(query)
    val body = sendWithRetry(uri.toString)
    val json = parser.parse(body).getOrElse(sys.error(s"Invalid JSON from $uri"))
    val records = json.hcursor.downField(collectionKey).as[Vector[Json]].getOrElse(Vector.empty)
    val total = json.hcursor.downField("page_meta").downField("total_count").as[Int].getOrElse(0)

    val next = acc ++ records
    if (maxRecords > 0 && next.size >= maxRecords) next.take(maxRecords)
    else if (next.size >= total || records.isEmpty) next
    else fetchPaged(endpoint, collectionKey, params, offset + pageLimit, next)
  }

  /** GET with retry + linear backoff. ChEMBL's public API intermittently
    * returns 5xx (e.g. server-side OOM); transient failures are retried. */
  private def sendWithRetry(url: String, attempts: Int = 4): String = {
    var lastErr = ""
    var i = 1
    while (i <= attempts) {
      basicRequest.get(uri"$url").send(backend).body match {
        case Right(b) => return b
        case Left(err) =>
          lastErr = err
          System.err.println(s"[ChemblClient] attempt $i/$attempts failed: ${err.take(120)}")
          if (i < attempts) Thread.sleep(2000L * i)
      }
      i += 1
    }
    sys.error(s"ChEMBL request failed after $attempts attempts: $url -> ${lastErr.take(300)}")
  }

  // --- offline mode ----------------------------------------------------------

  /**
   * Applies the same exact/`__in` equality filters the REST API would, so that
   * looping per-target (or batching ids) over the fixtures yields the correct,
   * non-duplicated subset rather than the whole file each call.
   */
  private val PaginationKeys = Set("format", "limit", "offset")

  private def applyFilters(records: Vector[Json], params: Map[String, String]): Vector[Json] =
    params.foldLeft(records) { case (recs, (key, value)) =>
      if (PaginationKeys.contains(key)) recs
      else if (key.endsWith("__in")) {
        val field = key.dropRight(4)
        val allowed = value.split(",").map(_.trim).toSet
        recs.filter(r => r.hcursor.downField(field).as[String].toOption.exists(allowed.contains))
      } else
        recs.filter(r => r.hcursor.downField(key).as[String].toOption.contains(value))
    }

  /** Reads /sample/<collectionKey>.json from the classpath. */
  private def readFixture(collectionKey: String): Vector[Json] = {
    val resource = s"/sample/$collectionKey.json"
    val stream = Option(getClass.getResourceAsStream(resource))
      .getOrElse(sys.error(s"Missing offline fixture: $resource"))
    val src = Source.fromInputStream(stream)
    val text = try src.mkString finally src.close()
    parser.parse(text).getOrElse(sys.error(s"Invalid JSON fixture: $resource"))
      .hcursor.downField(collectionKey).as[Vector[Json]].getOrElse(Vector.empty)
  }

  def close(): Unit = backend.close()
}

object ChemblClient {
  // Collection keys ChEMBL uses for each list endpoint.
  val ActivityKey = "activities"
  val MoleculeKey = "molecules"
  val TargetKey   = "targets"
  val AssayKey    = "assays"
  val DocumentKey = "documents"
}
