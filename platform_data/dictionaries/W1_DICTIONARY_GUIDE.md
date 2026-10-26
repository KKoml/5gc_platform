# W1-specific field dictionary

Updated 2026-10-26. Scope: the seven accepted W1-D01–W1-D07 runs and their retained raw/derived/context artifacts. Later per-UE collectors, UE-ownership extensions and business prevalidation do not establish historical W1 support.

## Counts and entry points

The main dictionary has **277 retained definitions**. This is a cross-product field catalog, including identifiers, configuration, state, events, labels and quality, not 277 independent numerical features or a fixed training tensor.

| File | Purpose |
| --- | --- |
| [W1_FIELD_DICTIONARY.csv](W1_FIELD_DICTIONARY.csv) | Current retained definitions; identical to the [appendix CSV](../../manuscript_supplement/data/field_dictionary.csv) |
| [W1_FIELD_SCREENING_400.csv](W1_FIELD_SCREENING_400.csv) | A decision for every original canonical ID, including exclusions, aliases and unresolved evidence |
| [W1_DICTIONARY_SUMMARY.json](W1_DICTIONARY_SUMMARY.json) | Machine-readable counts and evidence scope |
| [BASE_TABLE_81.csv](BASE_TABLE_81.csv) | All 81 legacy export columns, including unsupported placeholders, with support decisions |
| [Legacy source catalog](../evidence/PLATFORM_DICTIONARY_SOURCE.csv) | The unchanged 400-entry platform capability inventory; retained for provenance and earlier verification |

| Retained role | Definitions |
| --- | ---: |
| configuration | 38 |
| dimension | 16 |
| event | 4 |
| evidence | 1 |
| identifier | 22 |
| label | 13 |
| metric | 141 |
| quality | 29 |
| state | 13 |

| Legacy decision | Definitions |
| --- | ---: |
| exclude | 118 |
| merge_alias | 5 |
| retain | 277 |

## Screening rules

1. Retain an entry only when an actual W1 artifact supports the stated field and its corrected meaning. File presence or source-code capability alone is insufficient. Preserve the verification level: full counts, sampled records, or an explicitly limited check are different evidence.
2. Exclude later-only capabilities, bare-metal-only producers in the K8s W1 deployment, all-empty fields, unsupported constants, field-family templates and unresolved definitions from the main count. Keep every original ID in the crosswalk. Exclusion from one product does not imply absence of a different meaningful producer; K8s NF CPU exists even when bare-metal process columns are empty.
3. Merge only verified same-source, same-entity aliases. Aggregate, per-instance, packet and host-interface observations are different scopes. A retained count is not a claim that all entries are independent.
4. Keep useful configuration, labels and quality evidence with their proper role. They are not performance measurements and must not silently become predictive inputs.
5. Retain interpretable offline flow summaries with explicit whole-flow/lifecycle limits. Legacy RTT/loss heuristics do not establish actual end-to-end RTT or packet loss and are identified in compatibility/screening records rather than counted as validated physical measurements.

## Corrections and limits

- N3 `OT` includes both directions in W1 and is also written into the legacy `n3_uplink_bitrate_bps` column. Preserve stored names for compatibility, use the corrected meaning, and do not sum the supposed uplink and downlink as independent totals.
- Control-plane success rates are 0–100 percentages over cumulative collector counters. Request/failure counters are cumulative. `business_completion_rate` is a separate 0–1, 60-second terminal-outcome ratio with minimum sample rules.
- Host-interface `rx_bps`/`tx_bps` are Byte/s; applicable K8s Pod network rates are bit/s. `tun_up_time` is an ISO timestamp, not elapsed seconds.
- UPF CPU/memory are observed and summed into V3, although historical coverage metadata failed to recognize the fallback and marked them capability_missing. Original coverage reports remain intact.
- The V3 `ready_gnb_count` and `observed_ue_count` are overwritten by periodic K3s workload ready counts and then held between samples; `observed_ue_count` is therefore not a registered-UE count. `ran_pdu_active_count` is derived from partial UE logs. Original snapshot_only coverage labels are preserved. Ready replicas, registered UEs, active sessions and business-active UEs are different quantities. UE logs cover fragments of each run; the maps do not establish complete current NF or gNB ownership.
- Application statistics describe representative traffic UEs, one per DNN, and segmented sender outcomes. Live and final rotated records can overlap and require deduplication. They do not provide independent throughput/RTT for all 40 configured UEs.
- A 1-second export grid does not improve native polling frequency. Full-flow bytes, rate and jitter summaries can use later flow information and are not automatically available to an online model at the first-seen bucket.
- The seven original base tables remain 611,777 rows with 81 columns. Each has 64 columns ever nonempty and 17 entirely empty; this is not a 64-feature validity claim. The separate 24-variable and prediction products retain their own construction and limits.

## Reproduce and check

From the repository root:

```bash
python tools/build_w1_dictionary.py --check
```

The builder uses the bundled [sanitized evidence inputs](../evidence/w1_dictionary_inputs/). Those inputs preserve field names, relative artifact paths, counts and verification methods without publishing original identity/site values. This maintenance tool rebuilds dictionary metadata only; it does not collect traffic, decode packets, regenerate the 81-column data or rerun models. Historical data and earlier validation receipts retain their recorded scope.
