"""Tool: plain-English definitions of the key metrics / terms.

Static, curated definitions — deterministic and citable. Written to inform, not
to make scientific claims. Keys are matched loosely (case/punctuation-insensitive).
"""
from __future__ import annotations

import re

TOOL_SPEC = {
    "name": "get_metric_definition",
    "description": "Define IC50/Ki/Kd/EC50/pChEMBL/confidence score/standard relation/data validity comment.",
    "arguments": {"metric_name": "one of the supported metric names/aliases"},
}

DEFINITIONS: dict[str, dict] = {
    "ic50": {
        "term": "IC50",
        "definition": "The concentration of a compound that inhibits a biological "
                      "activity (e.g. an enzyme or cell process) by 50%. Lower IC50 "
                      "means more potent inhibition. Reported here normalized to nM.",
        "direction": "lower is more potent",
    },
    "ki": {
        "term": "Ki",
        "definition": "The inhibition constant — the binding affinity of an inhibitor "
                      "for its target, derived from binding/kinetics. Lower Ki means "
                      "tighter binding. Normalized to nM.",
        "direction": "lower is tighter binding",
    },
    "kd": {
        "term": "Kd",
        "definition": "The dissociation constant — the concentration at which half of "
                      "the target is bound at equilibrium. Lower Kd means higher "
                      "binding affinity. Normalized to nM.",
        "direction": "lower is higher affinity",
    },
    "ec50": {
        "term": "EC50",
        "definition": "The concentration producing 50% of a compound's maximal effect "
                      "(often in functional/cell assays). Lower EC50 means more potent "
                      "effect. Normalized to nM.",
        "direction": "lower is more potent",
    },
    "pchembl": {
        "term": "pChEMBL value",
        "definition": "A ChEMBL-derived comparability metric: -log10 of a molar "
                      "activity value (IC50/Ki/Kd/EC50/etc.) in M. pChEMBL = 7 ~ 100 nM; "
                      "pChEMBL = 9 ~ 1 nM. Higher pChEMBL means more potent, and unlike "
                      "raw values it is directly comparable across measurement types.",
        "direction": "higher is more potent",
    },
    "confidence_score": {
        "term": "Assay confidence score",
        "definition": "A ChEMBL 0–9 score describing how confidently an assay is "
                      "mapped to its molecular target. Higher is more reliable; AssayLens "
                      "curates to >= 7 for the comparable potency mart.",
        "direction": "higher is more reliable target assignment",
    },
    "standard_relation": {
        "term": "Standard relation",
        "definition": "The operator qualifying a measured value: '=' is an exact value, "
                      "while '>', '<', '~' indicate the true value is bounded/approximate "
                      "(e.g. inactive at the highest tested dose). Only '=' (or unspecified) "
                      "rows enter the curated potency mart.",
        "direction": "non-'=' relations are excluded from curation",
    },
    "data_validity_comment": {
        "term": "Data validity comment",
        "definition": "A ChEMBL annotation flagging a measurement as potentially "
                      "problematic (e.g. outside typical range, author-flagged). Rows with "
                      "such a comment are excluded from the curated potency mart.",
        "direction": "presence excludes a row from curation",
    },
}

_ALIASES = {
    "pchembl_value": "pchembl", "pchembl value": "pchembl",
    "confidence": "confidence_score", "confidence score": "confidence_score",
    "relation": "standard_relation", "standard relation": "standard_relation",
    "validity": "data_validity_comment", "data validity comment": "data_validity_comment",
}


def _key(metric_name: str) -> str | None:
    # Keep word chars + spaces, then try the value as-is and with space/underscore
    # swapped, against both the canonical keys and the alias table.
    s = re.sub(r"[^a-z0-9 _]", "", (metric_name or "").lower()).strip()
    candidates = {s, s.replace("_", " "), s.replace(" ", "_")}
    for c in candidates:
        if c in DEFINITIONS:
            return c
        if c in _ALIASES:
            return _ALIASES[c]
    return None


def run(metric_name: str) -> dict:
    key = _key(metric_name)
    if not key:
        return {
            "error": f"Unknown metric '{metric_name}'.",
            "available": sorted({d["term"] for d in DEFINITIONS.values()}),
        }
    return {"result_count": 1, "metric": DEFINITIONS[key]}
