"""Pure indicator maths for the CSH paper case study.

No database access here on purpose: everything below is a plain transformation
of already-extracted rows, so it can be tested without a Postgres instance.

Metric names in core.statistics are NOT unique — 56 of 300 Ortsteil-level names
occur in more than one dataset, and 'Ausländer' alone exists in six with six
different base populations. Every value is therefore keyed by the pair
(dataset_id, metric_name), never by the metric name alone.

build_counts expects rows pre-filtered to a single period; it rejects
conflicting duplicates rather than silently keeping the last one.
"""

from __future__ import annotations

ARBEITSLOSE = "30943d88-4ac9-4968-84bc-35e9b337a85d:Arbeitslose insgesamt"
EINWOHNER = "dcc45e1a-11d1-4922-80c3-f49ba12863fb:Einwohner insgesamt"
AUSLAENDER = "dcc45e1a-11d1-4922-80c3-f49ba12863fb:Ausländer"
FAMILIEN = "aa01ad81-1060-48e9-84f2-8908287ecf5e:Familien insgesamt"
ALLEINERZ = "aa01ad81-1060-48e9-84f2-8908287ecf5e:Alleinerziehende insgesamt"

SHARE_DEFINITIONS = {
    "unemployment": (ARBEITSLOSE, EINWOHNER),
    "foreign": (AUSLAENDER, EINWOHNER),
    "single_parent": (ALLEINERZ, FAMILIEN),
}


def metric_key(dataset_id: str, metric_name: str) -> str:
    return f"{dataset_id}:{metric_name}"


def build_counts(rows) -> dict[str, dict[str, float]]:
    """Group extracted statistics rows into {spatial_code: {metric_key: value}}."""
    counts: dict[str, dict[str, float]] = {}
    for row in rows:
        code = row["spatial_code"]
        key = metric_key(row["dataset_id"], row["metric_name"])
        value = float(row["metric_value"])
        bucket = counts.setdefault(code, {})
        if key in bucket and bucket[key] != value:
            raise ValueError(
                f"Conflicting values for spatial_code {code}, metric_key {key}: "
                f"{bucket[key]} vs {value}"
            )
        bucket[key] = value
    return counts


def compute_shares(counts: dict[str, dict[str, float]]) -> dict[str, dict[str, float]]:
    """Derive the three ratios from summable counts, per spatial unit."""
    shares: dict[str, dict[str, float]] = {}
    for code, metrics in counts.items():
        out: dict[str, float] = {}
        for name, (numerator, denominator) in SHARE_DEFINITIONS.items():
            num = metrics.get(numerator)
            den = metrics.get(denominator)
            if num is None or den in (None, 0):
                continue
            out[name] = num / den
        if out:
            shares[code] = out
    return shares


def aggregate_to_parent(
    counts: dict[str, dict[str, float]], parent_of: dict[str, str]
) -> dict[str, dict[str, float]]:
    """Sum counts up to the parent unit (Ortsteil -> Stadtbezirk).

    Counts are summed; ratios are recomputed afterwards via compute_shares().
    Averaging the child ratios instead would silently weight a 500-resident
    Ortsteil the same as a 30000-resident one.
    """
    agg: dict[str, dict[str, float]] = {}
    for code, metrics in counts.items():
        parent = parent_of.get(code)
        if parent is None:
            continue
        bucket = agg.setdefault(parent, {})
        for key, value in metrics.items():
            bucket[key] = bucket.get(key, 0.0) + value
    return agg
