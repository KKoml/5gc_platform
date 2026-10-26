# W1 association provenance evidence

This evidence concerns the seven accepted W1 runs, labelled W1-D01 to W1-D07. It quantifies retained **producer-route metadata and field availability**. It does not estimate association accuracy. No model score enters any denominator.

## Evidence and denominators

`association_summary.json` is the deterministic aggregate of three compact, de-identified evidence tables and retained NF-link summary counts:

| File | Unit | Preserved evidence |
| --- | --- | --- |
| `session_record_projection.csv` | One retained `derived/session_map.jsonl` row | Run-local UE and UE-IP equivalence keys, timestamp, PDU ID, row-level `label_source`, field-presence bits, and selected NF identifiers |
| `flow_file_provenance_counts.csv` | Count of **sampled** flow-artifact rows with the same projection within one source file | Run, capture family, run-local file ordinal, source directory, producer label, optional secondary source, UE-IP lookup status, and field-presence bits |
| `capture_summary_projection.csv` | One retained per-capture summary | All-capture total/labeled row counts, run, capture family, file ordinal, and deterministic sample inclusion |

`source_inventory.json` retains sampled input sizes, canonical file counts, excluded compatibility copies, and the original NF-link summary's record/plane counts. The full NF-link JSONL is not rescanned; only retained NF-link summary totals/plane counts are reported, with an arithmetic check that plane counts sum to the total. The source roots and registry run names are private. No SUPI, IP address, site address, or absolute source path is included in these evidence tables. UE and IP keys are arbitrary run-local aliases; no alias map is published.

`flow_route_summary.csv` provides the same route counts in a compact table for each run/capture family and for the run-pooled `ALL` row within each family. Every proportion uses its **sampled flow-record denominator**. It also repeats the separately sourced all-capture totals/labeled counts so that the population and sample sizes remain visible together; those all-capture totals are not the route-share denominator. Literal producer labels are preserved. `--check` verifies this CSV as well as the JSON summary.

Session-map denominators are **retained records**, not distinct sessions. The same SUPI/PDU key may appear repeatedly during session creation, recovery and address reuse. The summary reports run-qualified unique SUPI and SUPI/PDU keys, repeated-key records, and duplicate `(SUPI, PDU, timestamp, UE-IP, UPF)` keys. The latter is a duplicate-key check, not an independent reconstruction of session lifecycles.

Each flow capture family has a separate row denominator. The extractor inventories `derived/*_flows.jsonl` and uses a `pcap/*_flows.jsonl` compatibility file only when the same basename is absent from `derived/`. It reads **all** retained per-capture summary files for exact producer-reported row totals. The frozen producer defines a "labeled" flow record as one with **nonempty DNN or UPF ID**, not a correct UE identity and not a particular `label_source`. These totals are presented as retained producer summaries, not a fresh full-record scan.

For route and address-reuse analysis it reads every twelfth canonical capture file within each run and capture family in sorted filename order, beginning with the first and always including the final file. It reads **every row** of each selected same-basename CSV. The first record's label/identity projection is checked against the corresponding JSONL representation, and each selected CSV's total row count must match its retained per-capture summary. This check verifies the used representation's first-record projection and record count; it is not a full CSV/JSONL equality proof. File-sample proportions apply **only to the sampled records**. The sample is not uniform over flows and is not presented as a population rate or accuracy estimate.

The extractor never adds CSV and JSONL representations of the same artifact. Rotated captures remain separate source files. The same network communication can appear at multiple capture points; their rows must not be summed and described as unique end-to-end connections or distinct packets. `n6-uplink-logical_flows.jsonl` is an N3-derived view, not an additional physical capture, and is excluded from both these capture totals and the route sample.

## Meaning of the producer labels

- Session-map `control-plane-log` means the row came through the control-plane-log export route. The frozen exporter also combines recent records within a time window, queues sessionless UPF/PFCP observations, obtains selected-SMF identity from the log filename or DNN/address inference, and resolves PFCP addresses from configuration. The label therefore does **not** establish that every field was directly observed. The actual direct versus temporal/configuration fallback fraction is unavailable at field level.
- Session-map `ran-ue-map+n3-gtpu-fallback`, when present, denotes the explicit RAN/N3 fallback route. It contains inferred/default values and is counted separately from the log route.
- Flow `authoritative:session-map` is the frozen parser's name for a static map lookup by inner source/destination UE IP, followed by TEID lookup. It is a match-route label, not an independent truth annotation. The whole-run indices keep the last record for a reused UE-IP/TEID key and do not apply a session lifetime or expose competing candidates.
- Flow `inferred:interface` and `inferred:subnet` are topology-based label routes. Their fractions use flow-record denominators. `label_source` is initialized when a flow aggregate is created; the flow key does not contain the label, and the aggregate label is not updated for every packet. No packet-level attribution accuracy is inferred from it.
- Empty flow `label_source` means no recorded UE/session label route. This can be expected for SBI, PFCP or management traffic, so it is not automatically an association failure. The logical N6 derivative may instead identify its origin in the `source` field.
- NF-link `observation_source` distinguishes event-derived and flow-derived observations. The frozen generator enriches records through whole-run UE/session maps and uses default/topology NF identities. It omits field-level match routes and discarded candidates. Direct, fallback, unmapped and ambiguous NF-link association fractions cannot be recovered from this output alone.

## Run-wide address-reuse exposure

For each run, the extractor builds UE-IP → set of `(SUPI, PDU-session-ID)` keys from **all retained session-map records**. A sampled flow with a nonempty `ue_ip` is classified as a static map hit to one identity, a static map hit to multiple identities, not present in the map, or empty. The summary reports exposure both over sampled rows in a capture family and over sampled rows whose UE IP appears in the session map.

An IP associated with multiple identities over an entire day is evidence of **run-wide address reuse**. It is not evidence of simultaneous IP conflict, a wrong label, or an error rate. The method deliberately does not count bare TEID integer reuse as a conflict: UPF, peer, direction and lifetime scopes would be needed. Reuse exposure makes the frozen whole-run lookup limitation visible without changing or re-attributing the historical data.

## What remains unknown

There is no independently labelled association ground truth, complete rejected-candidate inventory, or per-field provenance ledger in these artifacts. Association precision, recall, actual misassociation rate, and the direct-observation fraction of individual enriched fields remain **unmeasured**. Row completeness and producer-route proportions cannot substitute for these quantities.

## Offline reproduction

From the repository root:

```bash
python3 tools/summarize_w1_association_quality.py --check
```

This command reads only the bundled compact evidence, recomputes every summary value, checks session-row counts and NF-link summary plane arithmetic, and compares with `association_summary.json`. It performs no network access, collection, control action, source-data mutation, or content-hash verification. It is an arithmetic/projection-consistency check; it does not independently certify the raw-to-projection extraction or historical labels.

An authorized holder of the original W1 run artifacts can regenerate the compact evidence:

```bash
python3 tools/summarize_w1_association_quality.py \
  --extract --registry /path/to/W1/registry.json \
  --evidence-dir /path/to/new/association-evidence --sample-every 12
```

The extractor selects only the registry's seven accepted D01-D07 runs, reads session records, capture summaries, selected same-basename flow CSVs and their first JSONL records, plus NF-link summary JSON. It reads source files without modifying them and writes only the specified output directory. It does not include or distribute the platform's collection or control implementation. To reproduce the same evidence use the documented stride of 12.
