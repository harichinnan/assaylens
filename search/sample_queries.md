# Sample Elasticsearch queries

Index: `assaylens_activity_evidence` (one doc per curated compound-target-assay result).
These mirror the patterns the agent's `search_assay_evidence` tool builds from
structured arguments. Run against `http://localhost:9200`.

> All documents are already curated (comparable rows only), so search is about
> ranking + filtering evidence, not quality control — that happened in dbt.

---

### 1. "EGFR kinase inhibitor assays with IC50 under 100 nM"

```json
GET assaylens_activity_evidence/_search
{
  "query": {
    "bool": {
      "must":   [{ "match": { "assay_description": "kinase inhibitor" } }],
      "filter": [
        { "term":  { "target_name.raw":  "EGFR" }},
        { "term":  { "standard_type":     "IC50" }},
        { "range": { "standard_value_nm": { "lt": 100 }}}
      ]
    }
  },
  "sort": [{ "standard_value_nm": "asc" }]
}
```

> In practice the agent filters by `target_chembl_id` (CHEMBL203) resolved from
> "EGFR" via the seed, which is more precise than a name match.

---

### 2. "BRAF compounds with high-confidence assay evidence"

```json
GET assaylens_activity_evidence/_search
{
  "query": {
    "bool": {
      "filter": [
        { "match":  { "target_name": "BRAF" }},
        { "range":  { "confidence_score": { "gte": 8 }}}
      ]
    }
  },
  "sort": [{ "confidence_score": "desc" }, { "pchembl_value": "desc" }]
}
```

---

### 3. "HER2 cell proliferation assays"

```json
GET assaylens_activity_evidence/_search
{
  "query": {
    "bool": {
      "must":   [{ "match": { "assay_description": "proliferation cell" }}],
      "should": [{ "match": { "target_name": "erbB-2 HER2" }}],
      "minimum_should_match": 1
    }
  }
}
```

---

### 4. "JAK2 potent compounds with pChEMBL greater than 7"

```json
GET assaylens_activity_evidence/_search
{
  "query": {
    "bool": {
      "filter": [
        { "match": { "target_name": "JAK2" }},
        { "range": { "pchembl_value": { "gt": 7 }}}
      ]
    }
  },
  "sort": [{ "pchembl_value": "desc" }]
}
```

---

### Aggregation: evidence count per target

```json
GET assaylens_activity_evidence/_search
{
  "size": 0,
  "aggs": {
    "by_target": { "terms": { "field": "target_chembl_id" } }
  }
}
```
