#!/usr/bin/env bash
# Run dbt from the repo root with the project's profiles directory.
#
#   scripts/run_dbt.sh build     # run models + tests (default)
#   scripts/run_dbt.sh test      # tests only
#   scripts/run_dbt.sh run       # models only
set -euo pipefail

CMD="${1:-build}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DBT_DIR="${REPO_ROOT}/dbt"

# dbt reads connection settings from dbt/profiles.yml (copy from the example).
if [[ ! -f "${DBT_DIR}/profiles.yml" ]]; then
  echo "Missing ${DBT_DIR}/profiles.yml — copy profiles.yml.example and set credentials." >&2
  exit 1
fi

cd "${DBT_DIR}"
export DBT_PROFILES_DIR="${DBT_DIR}"

# Install package deps (dbt_utils) if not already present.
if [[ ! -d "dbt_packages" ]]; then
  dbt deps
fi

exec dbt "${CMD}"
