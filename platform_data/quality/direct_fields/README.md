# W1 mapping-field consistency with original SMF logs

This evidence compares retained session-map values with the explicit text in
the corresponding original SMF logs. It is a platform-data consistency check;
no model score enters any denominator. It does **not** establish independently
adjudicated association accuracy or reconstruct historical per-field
direct/fallback decisions, which the producer did not retain.

## Observed results and denominators

Across W1-D01–W1-D07, 9,100 of 9,140 retained mapping records (99.56%) have an
exact context in their corresponding `nf/smf-gold.log` or `nf/smf-silver.log`.
These are all 9,100 records whose producer lies in the audited two-log scope.
The remaining 40 records name the aggregate core log and remain **outside the
audited source scope**; they are not counted as missing files, mismatches or
fallback decisions. No extra aggregate-core-log scan was performed.

Matching uses producer-log basename, UTC timestamp at microsecond precision,
SUPI and PDU-session ID. SUPI and PDU ID are structural matching keys, not
independent validation of UE identity. The nine non-key attributes are DNN,
UE IP, UPF ID, PFCP address, UL/DL TEID, local DL TEID, RAN address and RAN DL
TEID. All **81,900 assessed record–attribute pairs agree**; 360 pairs from the
40 out-of-scope records remain unassessed. No evaluated field is null, no
conflicting exact source context was found, and no scoped record lacks its
exact context. D03 has two mapping records with repeated, identical raw
contexts; these are one semantic candidate each, not conflicting candidates.

Selected-SMF identity has a separate producer/path binding in the 9,100 scoped
records; it is not an explicit field of the `SessionMap` message body.
Selected AMF is null in all 9,140 mappings. S-NSSAI and the PFCP-established
boolean are also not explicit fields of this message body and are not counted
as body corroboration. Their presence elsewhere is a separate question.

The 15-second association window used by the historical producer is not used
as an accuracy tolerance here: context matching is exact after timestamp
normalization. Neither that window nor this comparison measures cross-host
same-event timing error. Empty strings and zero-valued TEIDs normalize to null
consistently with the historical mapping semantics.

## Files and offline reproduction

`evidence_counts.json` contains only anonymous run labels and field/count
summaries from the owner-side original-log inspection. It contains no raw
values, UE identifiers, IP addresses, private source paths or original run IDs.
The compact evidence supports independent arithmetic reproduction, not a fresh
inspection of original log contents.

```bash
python3 tools/summarize_w1_direct_field_quality.py --check
```

This standard-library-only command reads the anonymous evidence, recomputes
the three CSVs and JSON summary in memory, validates aggregate/denominator
conservation, and compares their entire saved text. It performs no network
calls, model execution, dataset mutation or hash checks. Without `--check` it
writes the regenerated summaries; use `--output-dir` to choose another folder.

| File | Counting unit |
| --- | --- |
| `record_summary.csv` | Retained mapping records, and nine non-key attribute comparisons per record |
| `field_summary.csv` | Per-run/aggregate mapping-record × field counts, with matching keys marked separately |
| `other_provenance.csv` | Selected-SMF path binding and fields not explicit in this message body |
| `direct_field_summary.json` | The same summaries with interpretation limits |

## Re-extract from owner-provided original logs

An authorized data holder may create a local JSON mapping seven anonymous
labels to seven distinct original run directories, in this form:

```json
{"W1-D01":"/path/to/D01","W1-D02":"/path/to/D02","W1-D03":"/path/to/D03","W1-D04":"/path/to/D04","W1-D05":"/path/to/D05","W1-D06":"/path/to/D06","W1-D07":"/path/to/D07"}
```

Keep this owner-side path map private, then run:

```bash
python3 tools/summarize_w1_direct_field_quality.py \
  --run-map /path/to/private-run-map.json \
  --output-dir /path/to/separate/direct-field-evidence
```

Extraction reads only each `derived/session_map.jsonl` and the two original
SMF logs. It resolves only the audited producer basenames under each run's
`nf/` directory; other producer names remain outside scope, and absent audited
logs are counted separately. It independently reads the explicit bracket
fields; it neither imports nor distributes the platform collector/parser.
It never opens PCAP, flow records, the aggregate core log, or files outside the
seven supplied directories. Malformed exact-context text raises an error.
Counts separately preserve map nulls, raw-value nulls, mismatches, conflicting
contexts, missing audited sources and sources outside scope. Original run
files are read without modification; only anonymous counts and summaries are
written to the selected output directory.
