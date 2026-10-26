# W1 association quality: direct evidence summary

This report separates retained producer-route evidence, field availability, and measured limits. It contains no model results.

## Session-map records (full retained population)

| Run | Retained rows | SUPI/PDU keys | Control-plane-log route | Explicit RAN/N3 fallback route | Selected-AMF nonempty | Multi-identity UE-IP keys / all UE-IP keys |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| W1-D01 | 1,304 | 40 | 1,304 | 0 | 0 | 82 / 210 |
| W1-D02 | 1,307 | 40 | 1,307 | 0 | 0 | 139 / 280 |
| W1-D03 | 1,302 | 40 | 1,302 | 0 | 0 | 105 / 350 |
| W1-D04 | 1,303 | 40 | 1,303 | 0 | 0 | 105 / 310 |
| W1-D05 | 1,306 | 40 | 1,306 | 0 | 0 | 125 / 250 |
| W1-D06 | 1,313 | 40 | 1,313 | 0 | 0 | 79 / 250 |
| W1-D07 | 1,305 | 40 | 1,305 | 0 | 0 | 117 / 250 |

The population contains **9,140 retained records**, not 9,140 distinct sessions. It contains 40 SUPI/PDU keys per run (280 run-qualified keys); all 280 keys occur repeatedly, with 8,860 records beyond the first per key. There are no duplicate `(run, SUPI, PDU, timestamp, UE-IP, UPF)` keys. These are record/key counts, not an independently reconstructed lifecycle count.

All records have the producer route `control-plane-log`; none use the explicit `ran-ue-map+n3-gtpu-fallback` route, and there are no empty/unrecognized route labels. However, the log route can include temporal, queue, path and configuration enrichment. **Its field-level direct versus fallback fraction is not recorded.** The named route shares are not accuracy.

SUPI, PDU ID, UE IP, DNN, UPF ID, selected SMF, UL/DL TEID and the PFCP-established flag are nonempty in all retained records. `selected_amf` is empty in all 9,140 records. Presence is not an independent correctness check.

Across run-qualified UE-IP keys, **752 / 1900 (39.579%)** map to multiple SUPI/PDU identities over their run. This is address-reuse evidence, not simultaneous IP conflict or a misassociation rate.

## Flow provenance (deterministic capture-file sample)

The all-capture totals come from retained producer summaries. Route and IP-exposure results use the separate system sample: every twelfth file per run/family, first and last files included, with every row of each selected same-basename CSV inspected. The literal route counts are available in `flow_route_summary.csv` and the full per-run breakdown in `association_summary.json`.

| Capture family | Sample / all files | Sample / all retained flow rows | Observed sample route labels | Sample rows exposed to run-wide multi-identity IP reuse |
| --- | ---: | ---: | --- | ---: |
| gtp-gold | 182 / 2,044 | 280,731 / 3,177,265 | `authoritative:session-map`: 280,731 (100.000000%) | 116,943 (41.6566%) |
| gtp-silver | 182 / 2,041 | 292,338 / 3,091,373 | `authoritative:session-map`: 292,338 (100.000000%) | 165,594 (56.6447%) |
| n3-gtpu | 182 / 2,037 | 579,217 / 6,311,678 | `<empty>`: 4 (0.000691%); `authoritative:session-map`: 579,213 (99.999309%) | 288,401 (49.7915%) |
| n4-pfcp | 182 / 2,038 | 737 / 8,387 | `<empty>`: 737 (100.000000%) | 0 (0.0000%) |
| n6-uplink | 182 / 2,037 | 289,467 / 3,100,018 | `<empty>`: 289,467 (100.000000%) | 0 (0.0000%) |
| sbi-http | 58 / 570 | 53,988 / 531,194 | `<empty>`: 53,988 (100.000000%) | 0 (0.0000%) |

The sample covers **968 / 10,767 capture files and 1,496,478 flow-artifact rows**; all-capture summaries report 16,219,915 rows. Each family retains its own denominator. These are rotated, capture-point-specific records, not unique end-to-end connections. The logical N6 derivative is excluded. The file sample is not uniform over flows, and its proportions are not population estimates.

The frozen producer's all-capture labeled count means DNN or UPF ID is nonempty. A flow labelled `authoritative:session-map` has a static whole-run map lookup, not an independently verified true session. Empty labels in N4/SBI/N6-uplink capture records are not by themselves association failures. Source labels initialize with a flow aggregate's first packet, so no packet-attribution fractions are claimed.

Run-wide reused-IP exposure is only a potential identity/lifecycle join ambiguity. Original parsed flow records carry UE IP/DNN/UPF but no SUPI/PDU identity. Reuse across SUPIs can preserve the same DNN/UPF, so the exposure percentage does not establish those labels are wrong. TEID integers are not evaluated as globally unique keys.

## NF links and unmeasured quantities

Retained NF-link summaries report **5,567,843 records**: N4 26,440, N6 5,508,475, and SBI 32,928. These are producer-reported retained summary counts; the full NF-link JSONL was not rescanned in this audit. They do not prove complete plane coverage or a field-level association success rate.

NF-link output has no per-field direct/fallback route or complete rejected/unmapped/ambiguous candidate inventory. **Independent association precision, recall, actual misassociation rate and field-level direct fractions remain unmeasured.** These unknowns are explicit in the machine-readable summary.

## Reproduction

`python3 tools/summarize_w1_association_quality.py --check` recomputes the JSON/CSV from bundled compact evidence and verifies arithmetic consistency. See `README.md` for extraction scope, privacy handling and exact denominators.
