# W1 platform data-quality summary

This summary evaluates the **seven accepted W1 runs** using retained collection records, source logs, association products and export coverage. It measures platform evidence directly; **no model score is used as a data-quality measure**. Counts describe the preserved artifacts, rather than a new experiment or an independent ground-truth accuracy evaluation.

## Main results

| Quality question | Measured result | Denominator and interpretation |
| --- | --- | --- |
| What do the remote clock probes show? | Absolute SSH midpoint offset: median **183 ms**, p95 **204.5 ms**, maximum **301.5 ms**. Half-interval uncertainty: **163 / 177 / 277.5 ms**. | **38,480 remote probes** from **19,240 health records**, all seven runs and both remote physical hosts; core reference zeros excluded. These are probe statistics, not measured same-event alignment errors. |
| How large is the probe-compatible offset interval? | Largest absolute interval endpoint, `abs(raw offset) + uncertainty`: median **345 ms**, p95 **380 ms**, maximum **579 ms**. | Conditional on a forward local interval and clocks stable during the individual probe. This bounds the compatible offset for that probe under those assumptions; it is not a general timestamp-accuracy guarantee. |
| Are probe records structurally usable? | **38,480/38,480** available, forward-interval and formula-consistent; **0** missing/unavailable/invalid. Health intervals median/p95/max **32/32/34 s**; **0** observed gaps >60 s. | Intervals are within each run's observed health-record span. No completeness is assumed before the first or after the last record. Full finite distributions are retained without outlier trimming. |
| Are retained session values supported by original logs? | **9,100/9,140 records (99.56%)** have an exact source-log context; **81,900/81,900** judged non-key body-field comparisons agree. | Exact source basename + UTC timestamp + SUPI + PDU matching in 14 SMF logs. All **9,100/9,100** rows within this inspected source scope match. **40** aggregate-log rows and **360** body-field comparisons remain outside this audit's source scope. This is source consistency, not independent identity accuracy. |
| What is directly observed versus inferred? | **9,140/9,140** session rows have the producer route `control-plane-log`; **0** use its separate RAN/N3 fallback route. The actual per-field direct/fallback fraction is **unrecorded**. | A row-route label includes temporal, path and configuration inference. Nine non-key fields have body corroboration; `selected_smf` is separately a producer-path binding. SUPI/PDU are matching keys, not independent validation targets. |
| How complete is the retained export? | **611,777 rows**, **81 columns/run**; **64** columns ever nonempty and **17** entirely empty in every run. All **5** source-age columns are entirely empty. | **567 run×field coverage records**. Nonempty columns include identifiers, labels and context; this is not a numerical-feature count or proof of fresh observations. |

[Machine-readable headline metrics](PLATFORM_QUALITY_METRICS.csv) include explicit units, denominators, evidence scope and limits. Per-run and per-host results are linked below.

## Association routes and fallback evidence

The [association results](association/README.md) separate three different populations: all retained session-map rows, all producer-reported capture-summary totals, and a deterministic sample of flow records for route inspection. The [per-run/family route table](association/flow_route_summary.csv) reports the literal `authoritative:session-map`, `inferred:interface`, `inferred:subnet` and empty routes with their own sample denominators. The parser's word `authoritative` identifies its lookup route; it does not supply ground truth.

The sample selects every twelfth file within each run and capture family, starts with the first, includes the last, and reads every selected CSV row. Sample proportions apply to those records only. All-capture total/labeled counts are retained producer summaries; a “labeled” flow has a DNN or UPF value, which does not establish a correct UE identity. Logical N6, an N3-derived view, is excluded from capture denominators. Different capture points can observe the same communication and are not added into unique end-to-end connections.

| Capture family | Sample files / all files | Sample flow records | Session-map route | Interface / subnet route | Empty route |
| --- | --- | --- | --- | --- | --- |
| `gtp-gold` | 182 / 2,044 | 280,731 | 280,731/280,731 (100.0000%) | 0 / 0 | 0/280,731 |
| `gtp-silver` | 182 / 2,041 | 292,338 | 292,338/292,338 (100.0000%) | 0 / 0 | 0/292,338 |
| `n3-gtpu` | 182 / 2,037 | 579,217 | 579,213/579,217 (99.9993%) | 0 / 0 | 4/579,217 |
| `n4-pfcp` | 182 / 2,038 | 737 | 0/737 (0.0000%) | 0 / 0 | 737/737 |
| `n6-uplink` | 182 / 2,037 | 289,467 | 0/289,467 (0.0000%) | 0 / 0 | 289,467/289,467 |
| `sbi-http` | 58 / 570 | 53,988 | 0/53,988 (0.0000%) | 0 / 0 | 53,988/53,988 |

The sample contains **1,496,478 artifact rows from 968/10,767 capture files** across the six separate families. The table intentionally has no pooled association-rate total. Interface and subnet routes are **0 observed sample rows**, not proof that all enriched fields were direct. Empty routes on N4, physical N6 and SBI are not a UE-association failure rate. Run-wide session maps contain **752/1,900 (39.58%) run-qualified UE-IP keys** linked to multiple SUPI/PDU identities over time; this is address-reuse exposure, not an error rate.

The frozen flow matcher uses whole-run IP/TEID indices, keeps the last entry for a reused key and does not enforce a lifecycle interval or expose competing candidates. Run-wide IP reuse is therefore reported as **potential identity/lifecycle ambiguity**, not simultaneous address conflict or an observed labeling error. Changing UE identity within the same DNN/UPF does not necessarily change those two flow labels. Historical per-field decisions, rejected candidates and independent truth labels were not recorded, so **precision, recall, actual misassociation rate and the field-level direct/fallback fraction remain unmeasured**.

## Evidence and reproduction

| Evidence | Published inputs and results | Reproduction scope |
| --- | --- | --- |
| [Clock probes](clock/README.md) | All sanitized remote-probe rows; per-run/host and pooled quantiles, invalid/missing counters and cadence | Offline recomputation from every published probe; optional extraction from all original run-health records |
| [Raw-log field corroboration](direct_fields/README.md) | Anonymous run/field comparison counts; matching, outside-scope and path-binding denominators | Offline count checks; optional source-log re-extraction from locally restored run directories |
| [Association provenance](association/README.md) | Anonymous session projections, all-capture summary counts, systematic flow-sample counts and retained NF-link totals | Offline recomputation; optional extraction from the retained original artifacts |
| [Coverage and observation envelopes](coverage/README.md) | Existing run×field coverage and sanitized observed UE-event envelopes | Offline availability summary, preserving unknown freshness and partial event evidence |

From the repository root, with Python 3 and the standard library:

```bash
python3 tools/summarize_w1_clock_quality.py --check
python3 tools/summarize_w1_direct_field_quality.py --check
python3 tools/summarize_w1_association_quality.py --check
python3 tools/summarize_w1_export_quality.py --check
python3 tools/summarize_w1_platform_quality.py --check
```

These checks recompute summaries from bundled evidence and compare the outputs. They do not run collection or model evaluation, modify W1 records, recalibrate timestamps or reassign session labels. Re-extraction needs separately restored original records; see [data access](../../DATA_ACCESS.md) and each method's input requirements. The quality tools are offline audit programs, separate from the unpublished collection/control implementation.

## Remaining measurement limits

W1 retains physical-host SSH probes, but no independently matched cross-host same-event timing reference. Probe interval uncertainty, sequential remote reads, clock behavior between probes, VM/container/decoder timing and end-to-end ingest delay prevent converting these numbers into a measured event-alignment error. The producer's `clock_skew_ms` has median/p95/max **26/41/100 ms** and is based on residuals outside SSH intervals, rather than midpoint offsets. Neither that statistic nor the **15 s association window** is an alignment-error measurement.

The empty source-age columns prevent bucket-level freshness reconstruction from the exported table. The retained UE-event timestamps span only **984.074–4,604.590 s per run**; those envelopes are observed event times, not proof of continuous log completeness or all-day per-UE state. K3s Ready workload counts describe workload readiness, distinct from registration, active PDU sessions and business activity. These limits remain visible even when downstream models perform well.
