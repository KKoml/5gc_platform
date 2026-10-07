# Appendix C. Data organization, formats and coverage

## C.1 Run organization and the six data categories

Every original run has a manifest and a run-scoped tree. [RAW_FILES.csv](../manifests/RAW_FILES.csv) inventories the seven accepted members, with relative paths, sizes, available hashes and hash verification status. Anonymous `W1-D01` through `W1-D07` consistently identify the surviving members; private original IDs remain on the Core data machine. The replacement history means seven accepted members are not seven total attempts (the registry has nine attempts). Six accepted members (D02–D07) retain an initial launcher return code of one with a recorded prediction-ready-gate rejection and a later registry salvage; D01 has launcher return code zero. The ledger discloses both facts. Registry acceptance must not be paraphrased as seven originally error-free launcher exits.

| Path family | Contents | Format / time granularity |
| --- | --- | --- |
| `run_manifest.json`, `config/runtime/`, `traffic/config/` | Run identity, frozen network/operation settings, runtime script snapshots and traffic settings | JSON and source files; run-level plus scheduled event offsets |
| `pcap/`, `nf/`, `free5gc.log`, `ran/logs/` | Original packet captures and NF/access text logs | PCAP/PCAPNG (possibly gzip), text; native packet/event times, not a regular time grid |
| `events/` | Parsed signaling/access events, actual fault commands, timeline, recovery actions/checkpoints, PDU probes and phases | JSONL; event/check/window granularity |
| `metrics/` | Control-plane KPIs, NF resources/state, host/interface counters, K8s and RAN workloads, run health | JSONL plus latest JSON snapshots; asynchronous configured 2 s / 5 s polling |
| `traffic/`, `ran/traffic-clients/` | DN/client scenario, terminal flow/segment records and transfer result statistics | JSON, text and JSONL; flow/segment/run scope |
| `derived/` | Session maps, packet/flow summaries, per-interface time series, logical flows and associated records | JSONL / CSV; event, flow and configured bucket scope |
| `report/` | Base/model/per-NF and task-oriented legacy tables, quality/stability/endurance/provenance reports, transfer inventories and dataset card | CSV/JSON/Markdown; table grid, window and run summaries |
| `collectors/`, `fault-state/`, `pids/`, `probe/` | Collector state/diagnostics, saved undo state, process IDs and probes | Runtime support evidence; not model features or credentials for publication |

The exact Figure 1 categories are **Network traffic**, **Signaling and sessions**, **NF resources and state**, **Host / interface statistics**, **gNB and UE status**, and **Application transfers**. [DATA_CATEGORIES.csv](../tables/DATA_CATEGORIES.csv) binds each to artifacts and retains Table I's host-resource wording as an alias. Execution records, configuration and reports are additional provenance, not a seventh observed-data category.

[FILE_CATALOG.csv](../tables/FILE_CATALOG.csv) gives each primary artifact family, field range, producer and validity rule. An inventory hash copied from the historical transfer record is labeled `recorded_transfer_inventory_not_rehashed`; a freshly calculated hash is `recomputed`; an absent digest is explicitly `not_recorded_or_recomputed`. Blank hashes are not checksum success. Run-envelope timestamps must not be mistaken for individual file coverage.

## C.2 Different counting scopes

| Quantity | Verified scope | Interpretation / limit |
| --- | --- | --- |
| 400 dictionary entries | Current `kpi-dictionary/v2`, counted by canonical ID | 215 metric definitions and 185 other definitions. Includes later optional/prevalidation domains and dynamic field families; it is not a 400-column W1 table. Historical identity with the manuscript's dictionary version is unverified. |
| 81 base columns | Frozen `V3_COLUMNS`, every accepted `report/v3_timeseries.csv` | Output contract including IDs, configuration, time, labels, quality/state and numerical observations. Column existence does not establish valid observations. |
| 32 body numerical metrics | Manuscript statement; exact named list not provided | Current dictionary marks 36 V3 items as `metric`. Excluding three timing quantities and the `OT` N3-uplink alias gives a plausible 32-item subset. [METRIC_SCOPE_AUDIT.csv](../tables/METRIC_SCOPE_AUDIT.csv) labels this a candidate interpretation, not an authoritative redefinition. |
| 24 task observations | Existing Core-side candidate manifest has 24 explicit names | Twelve CPU/memory values across six AMF/SMF/UPF instances, four local-host values, six local UPF-interface values and two UPF readiness values. They originate in separate raw streams and later builders, not a certified direct 81-column projection. |
| Prediction input | Final experiment-machine manifest pending | Input fields, masks, anchors, targets and repair revision must be bound to that machine's files/hashes. A Core-side repaired-view manifest is provided for matching, not asserted to be the final model input. |

The English [platform field view](../dictionaries/PLATFORM_FIELDS.csv) preserves source IDs, roles, units, value types, availability, source paths and source fields. Original dictionary caveats are retained verbatim in [source evidence](../evidence/PLATFORM_DICTIONARY_SOURCE.csv), in their original language; mechanical English display labels are not new definitions. The [81-column dictionary](../dictionaries/BASE_TABLE_81.csv) is an intersection by canonical V3 fields. The [Core24 source matching table](../handoff/CORE24_SOURCE_MATCH.csv) preserves candidate entities and conversions. An explicitly counted subset is preferable to silently modifying a dictionary to fit a paper number.

## C.3 Units, timestamps and missingness

Original timestamps are retained with their UTC offset; table time is a bucket label. JSONL, log, packet, command start/end and checkpoint-window time have different meanings. Both absolute time and scheduled offsets are preserved. No new time origin or synthetic alignment replaces original evidence. Configured polling periods and actual timestamp differences must be distinguished.

Bytes, bit/s, packet/s, milliseconds, millicores, memory bytes, percent and ratios are distinct units. In the frozen host-interface collector, `rx_bps`/`tx_bps` are **byte/s**, despite the names; the computation divides counter-byte differences by elapsed seconds without multiplying by eight. In the separate task candidate, `rx_bitrate_bps`/`tx_bitrate_bps` require the byte/s-to-bit/s conversion. Other collectors may use the same name with a different implementation; join by source and entity as well as field name. Cumulative counters require differences; resets/restarts and negative differences require explicit interpretation. The frozen collector clamps negative deltas to zero: this is historical implementation behavior, not proof that no reset occurred.

CPU in millicores is not CPU percent. CPU percent of a limit and percent of node allocatable use different denominators. Physical-host observations can include VM load. Core-host and VM capacities must not be counted twice. Host-network Pod interface counters are not attributable Pod traffic; the sample resource record has `network_status=hostnetwork_skipped` and null network values.

Registration/PDU rates must be interpreted with their source/export convention; the frozen control-plane/model path can express success in percent whereas business completion is a 0–1 ratio. The general dictionary's rate unit must not override the executable source formula. The unit audit flags such fields rather than converting source values silently. No requests or insufficient terminal samples remain missing where the producer specifies that behavior.

JSON `null`, empty CSV cells and unavailable sample statuses are preserved. A valid observed zero is different from unavailable/unsupported/stale/not-applicable. Field coverage status is one of `ok`, `replaced`, `snapshot_only`, `capability_missing` or `export_bug`. `ok` is producer-level coverage metadata, not a guarantee that every cell is present or that it is suitable for any model. `is_valid_row`, `metrics_available`, `is_filled_any` and source-age fields have separate roles. Plans, target labels and post-hoc recovery quantities can leak answers if used as prediction/detection inputs.

## C.4 Recomputed coverage and real examples

[RUN_LEDGER.csv](../tables/RUN_LEDGER.csv) and [FIELD_COVERAGE.csv](../tables/FIELD_COVERAGE.csv) are freshly derived by reading the existing complete base tables, without regenerating them. They report rows, schema width, actual first/last bucket, 1 s continuity, validity counts and per-field observed nonempty ratios alongside recorded coverage. The seven base tables total 611,777 rows. Every source coverage report has 58 `ok`, 19 `capability_missing`, 3 `snapshot_only` and 1 `replaced` fields. This is a status partition of 81 definitions, not a count of 81 successfully observed metrics. Per-run, per-field nonempty ratios are in the coverage table.

The three snapshot fields are `observed_ue_count`, `ran_pdu_active_count` and `ready_gnb_count`; `OT` is replaced from N3 capture-derived values. These are not continuous per-UE 1 s ground truth. Resource streams can contain valid AMF/SMF/UPF observations even when similar base-table columns are missing, which is why Core24 has a separate lineage.

The [W1-D06 sample directory](../samples/W1-D06/README.md) combines complete anonymized configuration, small native stream excerpts, a contiguous 1 s base-table excerpt around the first paired intervention, actual commands/checks, a structured session map and an SMF source-log excerpt. Values/timestamps are retained; only identity/site fields are consistently transformed. These are excerpts, not a standalone replay of all raw records. The separate Core24 candidate excerpt is clearly labeled as a later product with pending final model-input binding.

## C.5 Provided files versus off-site raw materials

`manifests/PROVIDED_FILES.csv` specifies complete-file versus sample-only status, source and publication hashes, field range, time range where extracted, and producer/version. `manifests/RAW_FILES.csv` is a manifest-only inventory; most referenced raw files are not included in Git. `tables/STORAGE_INVENTORY.csv` inventories all seven selected runs by folder and bytes. Large packet captures and logs are reserved for owner-provided cloud storage. [handoff/CLOUD_DATA_INDEX.csv](../handoff/CLOUD_DATA_INDEX.csv) has no invented download links. Upload availability, access rights, hash verification and reviewer anonymity must be checked when URLs arrive. The small Git release does not claim full raw-data delivery.
