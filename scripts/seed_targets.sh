#!/usr/bin/env bash
# Convenience helper: print / validate the target seed list.
#
# The seed (data/seeds/target_seed.csv) is the single source of ingestion scope.
# This script just echoes it and sanity-checks the row count so a demo viewer
# can see exactly which targets the pipeline covers.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SEED="${REPO_ROOT}/data/seeds/target_seed.csv"

echo "AssayLens target seed: ${SEED}"
echo "------------------------------------------------------------"
column -t -s, "${SEED}"
echo "------------------------------------------------------------"
ROWS=$(( $(wc -l < "${SEED}") - 1 ))
echo "${ROWS} targets in scope."
