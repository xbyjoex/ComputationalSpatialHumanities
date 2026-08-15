#!/usr/bin/env bash
# Pull every input the case study needs into paper/analysis/data/ as CSV.
#
# All SQL runs on the VPS: there is no local Postgres. Each query writes one
# CSV with a header row. Re-running is safe and overwrites.
#
# Transport note: the SQL is piped over SSH stdin into `psql -f -` inside the
# container (via `docker exec -i`), instead of being embedded as a `psql -c`
# shell argument. Passing SQL as a `-c` argument requires three nested levels
# of quoting (local shell -> ssh remote command -> docker exec command) which
# is fragile for SQL containing single quotes. Piping via stdin avoids that
# entirely. Filenames, SQL semantics, and CSV-with-header output are unchanged.
set -euo pipefail

SSH_TARGET="deploy@auerbachs-auge.tech"
SSH_KEY="${HOME}/.ssh/leipzig_deploy"
DATA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/data"
mkdir -p "$DATA_DIR"

YEAR=2024
ELECTION=ew2024

# The three curated datasets. Metric names alone are ambiguous, so every pair is
# pinned explicitly.
PAIRS="
     (s.dataset_id = '30943d88-4ac9-4968-84bc-35e9b337a85d' AND s.metric_name = 'Arbeitslose insgesamt')
  OR (s.dataset_id = 'dcc45e1a-11d1-4922-80c3-f49ba12863fb' AND s.metric_name IN ('Einwohner insgesamt','Ausländer'))
  OR (s.dataset_id = 'aa01ad81-1060-48e9-84f2-8908287ecf5e' AND s.metric_name IN ('Familien insgesamt','Alleinerziehende insgesamt'))
"

# Rows whose spatial_key is exactly the name of a different administrative level
# belong to that level, not to this one. Belt and braces alongside migration 018.
FOREIGN_LEVEL_GUARD="
  NOT EXISTS (
    SELECT 1 FROM core.admin_boundaries other
     WHERE other.boundary_type <> s.spatial_unit
       AND core.norm_name(other.name) = core.norm_name(s.spatial_key)
  )
"

run_query() {
  local outfile="$1"
  local sql="$2"
  echo "  -> ${outfile}"
  ssh -i "$SSH_KEY" -o BatchMode=yes "$SSH_TARGET" \
    "docker exec -i leipzig-data-db-1 psql -U leipzig -d leipzig_data -v ON_ERROR_STOP=1 -f -" \
    <<EOF > "${DATA_DIR}/${outfile}"
COPY (${sql}) TO STDOUT WITH CSV HEADER
EOF
}

echo "Extracting case-study inputs (year ${YEAR}, election ${ELECTION})"

run_query indicators_ortsteil.csv "
  SELECT DISTINCT s.spatial_code, b.name AS ortsteil, s.dataset_id, s.metric_name, s.metric_value
  FROM core.statistics s
  JOIN core.admin_boundaries b
    ON b.boundary_type = 'ortsteil' AND b.code = s.spatial_code
  WHERE s.spatial_unit = 'ortsteil'
    AND s.period_year = ${YEAR}
    AND s.spatial_code IS NOT NULL
    AND ${FOREIGN_LEVEL_GUARD}
    AND (${PAIRS})
  ORDER BY s.spatial_code, s.dataset_id, s.metric_name
"

run_query election_ortsteil.csv "
  SELECT spatial_code, gebiet_name, party, zweitstimmen, gueltige_zweit,
         wahlberechtigte, waehler
  FROM core.election_results
  WHERE election_id = '${ELECTION}' AND level = 'ortsteil' AND spatial_code IS NOT NULL
  ORDER BY spatial_code, party
"

run_query election_stadtbezirk.csv "
  SELECT spatial_code, gebiet_name, party, zweitstimmen, gueltige_zweit,
         wahlberechtigte, waehler
  FROM core.election_results
  WHERE election_id = '${ELECTION}' AND level = 'stadtbezirk' AND spatial_code IS NOT NULL
  ORDER BY spatial_code, party
"

run_query boundaries.csv "
  SELECT boundary_type, code, name, parent_code
  FROM core.admin_boundaries
  WHERE boundary_type IN ('ortsteil','stadtbezirk')
  ORDER BY boundary_type, code
"

# Validation input only: the Stadtbezirk rows that migration 018 unlinked. Our
# own Ortsteil -> Stadtbezirk sums must reproduce these official values.
run_query indicators_stadtbezirk_raw.csv "
  SELECT sb.code AS stadtbezirk_code, sb.name AS stadtbezirk,
         s.dataset_id, s.metric_name, s.metric_value
  FROM core.statistics s
  JOIN core.admin_boundaries sb
    ON sb.boundary_type = 'stadtbezirk'
   AND core.norm_name(sb.name) = core.norm_name(s.spatial_key)
  WHERE s.spatial_unit = 'ortsteil'
    AND s.period_year = ${YEAR}
    AND (${PAIRS})
  ORDER BY sb.code, s.dataset_id, s.metric_name
"

echo "Done. Files in ${DATA_DIR}:"
wc -l "${DATA_DIR}"/*.csv
