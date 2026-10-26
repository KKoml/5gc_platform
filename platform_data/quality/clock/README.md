# W1 SSH-clock probe quality evidence

This evidence covers all health-monitor records from the seven accepted W1
runs, identified publicly as W1-D01 through W1-D07. It measures the quality and
limitations of the recorded SSH clock probes. It does **not** measure the
timestamp difference of matched events observed on different hosts.

## Recompute

From the repository root, using Python 3 and the standard library:

```bash
python3 tools/summarize_w1_clock_quality.py --check
```

This reads the seven `clock_evidence_W1-Dxx.csv` files and the small
`clock_core_reference_counts.json`, then deterministically regenerates
`clock_summary.csv`, `clock_summary.json`, and `clock_flagged_probes.csv` (all
flagged or invalid/unavailable probe rows, without truncation). To write the regenerated summaries
elsewhere, add `--output-dir /your/output/directory`. There are no network calls,
model evaluations, or changes to the original dataset.

An owner with the original run directories can reproduce the sanitized evidence:

```bash
python3 tools/summarize_w1_clock_quality.py \
  --run-root /your/local/run/root \
  --registry /your/local/accepted-W1-registry.json \
  --output-dir /your/separate/output/directory --check
```

The registry must contain exactly seven unique accepted runs, mapping uniquely
to D01–D07. Extraction reads every original `metrics/run-health.jsonl` record.
Malformed JSON and duplicate role entries cause an explicit error; missing
roles, unavailable probes and invalid numeric intervals are counted separately.
The published evidence removes host addresses, original run identifiers, source
paths, and absolute raw probe endpoints. Finite derived probe values, including
extreme values and values classified as invalid, remain unchanged.

## Observed results

All 19,240 health records were read, yielding 38,480 remote probes. All remote
probes were declared available and had finite, forward, producer-consistent
intervals. Missing, unavailable, invalid and formula-mismatch counts are each
**zero** in this accepted-W1 scope. Therefore the all-finite and valid-interval
distributions coincide; no sample was removed or repaired. The core contributes
19,240 explicit zero-reference rows, counted separately. The flagged-probe CSV
contains only its header for this scope.

Values below are **median/p95/max in milliseconds**. `abs(raw)` is the absolute
SSH-midpoint offset; `u` is the half-interval width. The last column describes
the absolute endpoint of a probe-compatible interval under the measurement
assumptions stated below. It is **not measured cross-host event alignment error**.

| Run | Host role | Remote probes | abs(raw) | u | abs(raw)+u |
|---|---|---:|---:|---:|---:|
| W1-D01 | ran | 2747 | 159.5/172.5/203.5 | 158.5/167/188.5 | 318/338/392 |
| W1-D01 | traffic | 2747 | 173.5/186/250 | 169/180.5/243 | 343/365.7/493 |
| W1-D02 | ran | 2749 | 183.5/199.5/230.5 | 155.5/170/200.5 | 339/368/431 |
| W1-D02 | traffic | 2749 | 194/220.5/261 | 167.5/179/227.5 | 361/397/480 |
| W1-D03 | ran | 2751 | 163.5/197.5/227 | 153/164/198 | 317/355/418 |
| W1-D03 | traffic | 2751 | 176.5/221.5/283 | 165/175.5/239.5 | 341/391/504 |
| W1-D04 | ran | 2751 | 162.5/194.5/224.5 | 157/173.5/204 | 320/360/418 |
| W1-D04 | traffic | 2751 | 170.5/183/240.5 | 166/179/235.5 | 337/361/476 |
| W1-D05 | ran | 2747 | 185.5/199.5/251.5 | 158/170/221.5 | 343/368/473 |
| W1-D05 | traffic | 2747 | 196.5/209/250.5 | 169.5/181.5/226.5 | 366/390.7/477 |
| W1-D06 | ran | 2748 | 183/201.325/270.5 | 158/169.5/185 | 341/372/455 |
| W1-D06 | traffic | 2748 | 195.5/207.5/251 | 169.5/181/225.5 | 365/388/475 |
| W1-D07 | ran | 2747 | 186/203/235.5 | 158/170/202.5 | 344/370/438 |
| W1-D07 | traffic | 2747 | 195.5/206.85/301.5 | 169.5/179.5/277.5 | 365/386/579 |
| ALL_W1 | ran | 19240 | 178.5/199/270.5 | 157/169/221.5 | 333/366/473 |
| ALL_W1 | traffic | 19240 | 191/208/301.5 | 168/179.5/277.5 | 357/387/579 |
| ALL_W1 | remote_combined | 38480 | 183/204.5/301.5 | 163/177/277.5 | 345/380/579 |

The pooled remote residual `abs(offset_ms)` is **25/34/100 ms**. The recorded
per-health-record `clock_skew_ms` is **26/41/100 ms** (19,240 records). These
are interval-exterior residual statistics and must not be substituted for the
midpoint-offset statistics or called actual alignment accuracy.

| Run | Health records (= core-reference count) | Health-record span, seconds | Consecutive interval median/p95/max, seconds | Intervals >60 seconds |
|---|---:|---:|---:|---:|
| W1-D01 | 2747 | 87259 | 32/32/33 | 0 |
| W1-D02 | 2749 | 87179 | 32/32/34 | 0 |
| W1-D03 | 2751 | 87255 | 32/32/33 | 0 |
| W1-D04 | 2751 | 87242 | 32/32/33 | 0 |
| W1-D05 | 2747 | 87231 | 32/32/33 | 0 |
| W1-D06 | 2748 | 87253 | 32/32/33 | 0 |
| W1-D07 | 2747 | 87235 | 32/32/33 | 0 |
| ALL_W1 | 19240 | 610654 | 32/32/34 | 0 |

Across the seven runs, consecutive observed health timestamps have intervals
**32/32/34 seconds** (median/p95/max; 19,233 intervals). There are no duplicate
or reversed health timestamps and no intervals above 60 seconds. The sum of
within-run observed spans is **610,654 seconds**. These spans exclude unobserved
experiment boundaries and the time between separate runs; they do not establish
continuous event-level monitoring.

## Measurement definition

The frozen W1 producer records a coordinator timestamp before SSH (`b`), a
remote `date` timestamp (`r`), and a coordinator timestamp after SSH (`a`), in
milliseconds. Its definitions are:

```text
raw_offset_ms          = r - (b+a)/2
probe_latency_ms       = max(0, a-b)
offset_uncertainty_ms  = max(0, a-b)/2
offset_ms              = r-b  if r < b
                         r-a  if r > a
                         0    otherwise
clock_skew_ms          = max(0, offset_ran, offset_traffic)
                         - min(0, offset_ran, offset_traffic)
```

For a forward local interval and clocks stable during that probe, the clock
offset compatible with the SSH measurement lies in
`[raw_offset_ms - offset_uncertainty_ms,
raw_offset_ms + offset_uncertainty_ms]`. Thus `abs(raw_offset_ms) +
offset_uncertainty_ms` is the largest absolute endpoint of this **probe-derived
interval**, subject to those assumptions. It is not an unconditional guarantee
of event alignment, collector latency, or timestamp accuracy. Wider SSH
intervals weaken this bound without establishing whether the host clock was
incorrect.

The `probe_latency_ms` label is a difference between two coordinator wall-clock
reads around SSH. It is not independently measured network latency: a wall-clock
step during the probe or malformed numeric observations can also affect the
recorded interval. The historical evidence cannot resolve those causes.

`offset_ms` is the signed portion outside the measurement interval: it is the
point in that interval closest to zero, rather than the midpoint estimate.
Consequently zero `offset_ms` does not establish zero true clock error, and the
recorded `clock_skew_ms` must not be described as measured cross-host event
alignment error. The core row is an explicit zero reference, not a measured
independent clock, and is excluded from all pooled remote-offset distributions.

The RAN and traffic probes are sequential SSH operations. The health-record
timestamp precedes those operations; it is not an exact timestamp of the remote
clock read. Only local interval differences are retained in the public evidence.
Those differences, midpoint offsets and uncertainty values allow independent
recalculation of the residual formula and all reported distributions. During
extraction, producer formulas are additionally verified against the three
original timestamps, with the outcome retained as `formula_checked` and
`formula_consistent`.

## Denominators, finite anomalies and cadence

`probe_rows` is the denominator for availability and validity counts. There is
one row per health record per remote host, including an explicit missing row
when that role was absent. `available_n` reports the producer's availability
flag, while `valid_interval_n` additionally requires finite required fields,
producer-formula agreement and a nonnegative local interval. It is a validity
check on the recorded measurement structure, not proof of a good clock.

Every `*_all_finite` distribution includes all finite recorded values,
regardless of interval validity or magnitude. Separate validity counts and
counts above 1,000 ms expose anomalies; that magnitude is a descriptive flag,
not an exclusion rule or a newly introduced acceptance gate. Distributions
ending in `*_valid_intervals` restrict the input to structurally valid forward
intervals, each with its own explicit sample count. Both the full and
restricted distributions must be considered together.

Medians and the 95th percentile are computed per probe; the 95th percentile uses
linear interpolation at `(n-1)*0.95`. No trimming, sample imputation, outlier repair,
or healthy-window selection is performed. Pooling gives each remote probe equal
weight and excludes the core reference. `record_clock_skew_ms` is deduplicated
once per health record, rather than counted twice for the two remote hosts.

Cadence statistics use consecutive health-record timestamps in original record
order within each run. They report sample span, median/p95/maximum interval,
reversed or duplicate timestamps, intervals longer than 60 seconds, and the sum
of their excess over 60 seconds. The 60-second threshold is descriptive. The
span is between first and last observed health records, not a demonstrated
fraction of the entire experiment with continuous monitoring. No intervals are
created across different runs, and no coverage is assumed before the first or
after the last observed health record.

Cross-host same-event alignment error, clock behavior between probes, host
clock steps during a probe, asymmetric SSH timing, and end-to-end collector
delay cannot be recovered from these records alone. These evidence limits are
separate from downstream model performance and from any association rule's
matching window.
