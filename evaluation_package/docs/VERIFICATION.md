# Verification record

> Historical scope: the 400/215 dictionary counts and earlier validation statements below describe the legacy platform catalog. For the current W1 dictionary and every screening decision, use the [W1 screening guide](../../platform_data/dictionaries/W1_DICTIONARY_GUIDE.md). This dictionary update preserves the original tables and saved evaluation results.

## Recomputed paper results and checkpoint replay

| Task | Executed check | Observed result |
|---|---|---|
| Forecasting | `verify_paper_tables.py`; `prediction/verify_saved_predictions.py`; `verification/replay_prediction_checkpoints.py` | Saved outputs: 200 per-seed MAEs, all 9 table mean/SD cells and 54 ablation values recalculate. Checkpoint replay: 54 T1 predictions across the three reported targets, three model types, three seeds and D06/D07; exact IDs/labels and maximum absolute prediction difference 0.0. |
| Detection | `verification/replay_detection_checkpoints.py`; `replay_normal_only_metrics.py`; `replay_supervised_rf_checkpoints.py` | Nine normal-only checkpoints replayed on D05/D06/D07 (18 score arrays), max score difference 0. D05 thresholds recalibrated; six normal-only model/budget metric cells match within 2.23e-16. Three RF checkpoints replayed; D05 thresholds match exactly and all six RF test metric rows match exactly. |
| Known-start classification | `verification/replay_localization_checkpoints.py` | All 15 checkpoints replayed on all 612 fixed windows: 9,180 predicted classes and 110,160 probabilities. Class predictions match exactly; max probability difference 2.22e-16; 24 paper-facing metric cells differ by at most 2.22e-16. |
| Offline imputation | `verification/replay_imputation_checkpoints.py`; `imputation/code/audit.py` | All six checkpoints replayed over six evaluation slots. 54 prediction files, 6,748,290 rows and 12,636 saved metric rows match bitwise, including NaNs; maximum numeric difference 0. |
| Data exports | `verification/verify_data_package.py` | All seven current 1 s exports pass whole-file row/schema/time checks: 81 columns each, 611,777 rows total, exact one-second UTC increments. The dictionary contains 400 unique IDs, 215 metric-role entries; 39 metric-role fields occur in this schema. |

The floating-output replay tolerances were fixed in the verification scripts before replay (`rtol=1e-6`, `atol=2e-6` for probabilities/scores/predictions; task-metric limits are recorded in each JSON result). IDs, labels, sample order, validity masks and predicted classes are checked exactly. Imputation numeric arrays and metrics are checked bitwise. Measured differences were zero or at floating-point roundoff; no tolerance was widened after inspection.

The paper table/figure matches establish output correspondence. They do not establish the historical run identity for this exact manuscript revision. Source code, configs, fit logs, checkpoints, data manifests, and execution receipts are compared separately in the private lineage report retained outside this package.

## Fresh training-flow checks

Four new, separately named local runs were started from the package bundle and wrote to new directories outside the release package. `verification/results/new_training/RETRAINING_VERIFICATION.json` gives the run IDs, seeds, code/input hashes, split rules, checkpoint hashes and resource records:

- T1 XGBoost, host CPU target: seeds 42/43/44, D01–D04 fit, D05 selection; D06/D07 were not read.
- Detection AE, seed 17: D01–D04 fit, D05 checkpoint/threshold selection, D06/D07 evaluation after freeze.
- Classification: five model variants × seeds 17/29/43; all 15 models frozen before held-out evaluation, then 1,800 grouped metric rows produced.
- Imputation: M/H × seeds 17/29/43; all six fits used D01–D04 and D05 selection; D06/D07 and supplemental slots were evaluated only after the six-checkpoint freeze.

These are package executability checks, not replacements for manuscript scores. Forecasting was freshly fit for one target/method family, and detection for one model/seed; the other historical method/seed artifacts were checked by full checkpoint replay and their retained training receipts. The classification and imputation fresh fits covered all included variants and seeds.

Several first attempts exposed package-adaptation issues and are preserved as separate private runs. The successful runs completed after fixing the reviewer paths, role derivation for the anonymized Core24h package slot, use of the current sealed data manifest, and classifier metric JSON serialization. Detection fitting itself completed before a driver NameError; its post-fit D05/test stages were resumed from that same new checkpoint. No failure output was used to replace a paper result.

## Data/schema limits

The paper's “32 numeric indicators” statement has no exact mapping to this current export/dictionary: 39 metric-role definitions occur in the 81-column schema, with ten marked capability-missing per run, one replaced and three snapshot-only. The 215 metric-role dictionary entries, 39 schema matches, and paper's 32 indicators are different scopes. The historical dictionary/export version is unconfirmed. The platform source snapshot identifies schema version `v3-2026-06-17`, but the per-run report inputs required to regenerate the exports are not bundled; no generator for the current dictionary was found.

Each 5 s task table contains 24 variables and timestamps intersect the 1 s series. Sampled same-timestamp host values are not equal, so a simple 1 s-to-5 s resampling lineage is not claimed. The raw packet captures are excluded; none of the table-level verifiers or checkpoint replays required PCAP content.

## Independence and access limits

Prediction replay rebuilds its tensors from the bundled `prediction_inputs/` histories and removes the temporary cache afterward. Detection replay uses temporary fit copies and removes them on success. Imputation replay operates in a temporary copy. The bundle-only fit helpers resolve task data from the extracted package and write new outputs outside it. Reviewer-configurable roots in legacy task scripts are placeholders, not author-machine locations; the published run guide uses the bundle helpers.

The current package is local and has no external anonymous access URL. D06/D07 had been accessed before this verification and are post-hoc, not blind. The task-start classification is conditional on a known injection start; imputation scores originally finite values hidden artificially and uses within-window context, so it is offline reconstruction, not online repair. CPU fallback was not validated; neural replay/fitting was executed with PyTorch 2.11.0+cu128 and CUDA 12.8. The Python 3.10.12 isolated environment passed `pip check`. `strace` was unavailable, so no OS syscall trace is claimed.

