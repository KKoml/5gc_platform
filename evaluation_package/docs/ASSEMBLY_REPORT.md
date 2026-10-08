# D-GATE anonymous-review materials: assembly and evidence map

**Status: local candidate; not uploaded or published.** The original manuscript and experiment-source trees were left untouched. The candidate contains task-ready, anonymized data; evaluation source; configurations; trained artifacts; saved per-sample predictions; table-level results; current 1 s exports; and bundle-only replay/training helpers. The private source-to-run mapping and detailed internal audit are not inside the candidate.

## Manuscript output map

| Paper output | Candidate materials | Actual check and evidence limit |
|---|---|---|
| `tab:data_categories` | `data_machine/dataset/metadata/PLATFORM_FIELD_DICTIONARY_400.csv`, coverage reports, and raw-inventory category summary | Current field definitions support the category view. The current dictionary has 400 entries and 215 metric-role entries; exact historical supplement identity is unconfirmed, and a dedicated paper-table generator was not located. |
| `tab:dataset_setup` | Seven D01–D07 full 81-column, one-second exports; per-slot coverage; `metadata/runs.csv`; protocol and platform snapshot | All seven included exports passed a full schema/time-grid audit (611,777 total rows). The current exporter declares schema `v3-2026-06-17`, but the report inputs needed to recreate these exports are not included. Exact historical paper-version identity is unconfirmed. |
| `tab:prediction_results` | `evaluation/prediction/`, `prediction_inputs/`, saved test indices/predictions, configs, source lock, and `evaluation/evidence/forecast_metrics.csv` | The nine table cells and 54 ablation values recalculate from saved predictions. T1 checkpoint replay rebuilt inputs and matched 54 held-out predictions exactly. The located source is a later prefix-repaired execution; its link to the exact paper revision is unconfirmed. |
| `fig:fault_detection` | Normal-only model artifacts and scores, separate supervised RF artifacts and scores, D05 thresholds, event ledger, evidence tables and original paper-baseline figure | All included normal-only and RF checkpoints were replayed; thresholds and metrics were recomputed. The paper figure is byte-identical to the current manuscript PDF and its labels match the candidate evidence. The original figure generator and the exact historical run combination are unconfirmed. |
| `fig:fault_localization` | 12-class task contract, 612 prepared windows, 15 checkpoints, per-sample probabilities, metrics, confusion tables, and original paper-baseline figure | All 15 checkpoints replayed with class decisions identical; 24 paper-facing metric cells match within floating-point roundoff. This is classification conditional on a known injection start. The paper revision's exact source-run/figure-generator link remains unconfirmed. |
| `tab:imputation_results` | Prepared windows, native/artificial/scoring masks, six checkpoints, predictions, fit records, and metric tables | All six checkpoint pipelines replayed; 54 output files, 6.75 million prediction rows and 12,636 saved metric rows match bitwise. This measures offline reconstruction of originally finite artificially masked values. The exact paper-run identity remains unconfirmed. |
| `fig:architecture` | Platform source snapshot and its deployment/collection configuration | The system description can be inspected against the included platform snapshot. The manuscript figure source itself remains in the private paper baseline and was not presented as an experimental-result artifact. |

`VERIFICATION.md` details exact replay scope, maxima, split handling, warnings and limits. `evaluation/verification/results/` contains executable machine-readable receipts. Newly trained results are identified separately in `evaluation/verification/results/new_training/RETRAINING_VERIFICATION.json`; they are not historical manuscript results and do not replace the included paper result files.

## Current data version and task relationship

The current 400-entry dictionary has 215 metric-role entries; 39 metric-role fields occur by name in the current 81-column schema. Of those 39, each run reports 25 `ok`, one `replaced`, three `snapshot_only`, and ten `capability_missing`. These counts do not directly reconcile with the paper's “32 numeric indicators.” The exact historical field dictionary/export version is unverified.

The seven one-second exports contain 611,777 total rows. Each five-second task view contains 24 variables and has timestamps intersecting the corresponding one-second export; however, same-timestamp sampled host values differ. The candidate does not claim that five-second task values are simple one-second resamples. Raw PCAP content is not included because table-level evaluation/replay did not require it.

One unused absolute source-host path field was removed from a duplicate imputation run-map copy so the reviewer package does not disclose a source-machine filesystem location. No task numeric table, index, label, mask, saved prediction or model checkpoint was changed. The sanitized task manifest and all package manifests were refreshed.

## Provenance boundary

The manuscript source tree lacks a common paper-revision/run/data provenance link and Git history. Cross-file evidence nevertheless identifies later source executions, their model/configuration records, and matching candidate outputs for all four tasks. The checkpoint replays establish that saved candidate materials produce the included saved outputs; they do not establish that those exact later runs generated the historical manuscript tables or figures. The source records and code/checkpoint comparisons are kept separately in the private lineage report.

D06/D07 were accessed before this verification and are post-hoc evaluation runs, not blind tests. New training output is written under separate run IDs and directories. No platform start, traffic generation, fault injection, recapture, external hosting or publication occurred.

## Running the package

Extract the top-level archive and follow `RUN_GUIDE.md`. `SHA256SUMS.txt` covers every packaged file except itself. The adjacent `.sha256` file covers the complete `.tar.gz` archive. The evaluation inventory and data-machine manifests record paths, byte counts, SHA-256 values and content roles.

The package contains pinned non-PyTorch Python dependencies; install a PyTorch wheel appropriate to the reviewer's system. The verified neural commands used Python 3.10.12, PyTorch 2.11.0+cu128 and CUDA 12.8 on a CUDA GPU. A reviewer URL has not been created or configured; access is only through a submission-platform attachment or a separately established anonymous route.
