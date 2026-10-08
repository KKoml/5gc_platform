# Evaluation materials

This package combines the task-ready dataset, T1 forecasting history/target tables, source code, configurations, trained artifacts, and saved evaluation outputs. Use the top-level `RUN_GUIDE.md` for commands. The helpers under `verification/` write separate validation outputs and do not replace paper-result files.

## Paper output mapping

| Paper output | Included source/material | Current verification | Source status |
|---|---|---|---|
| `tab:prediction_results` | `prediction/src/`, `resolved_config.yaml`, search records, model artifacts, `outputs/indices/`, saved predictions, and `prediction_inputs/` | Rebuilt the T1 tensor inputs from all seven bundled history tables. For the three paper targets, 54 checkpoint/split outputs (3 methods × 3 seeds × 2 splits) replayed with max absolute prediction difference 0.0. Saved-output aggregation independently checks 200 MAE rows, nine mean/SD table cells, and 54 ablation values. | Later four-field prefix-repaired execution; numeric/code correspondence is established, historical manuscript execution is not. |
| `fig:fault_detection` | `detection/normal_only/` (AE, KAN-AD, adapted TranAD); `detection/supervised_rf/` (separate RF run); D05 thresholds and model artifacts | Nine normal-only checkpoint fits replayed on validation and test score sequences (18 arrays; max difference 0). D05 thresholds and frozen-threshold D06/D07 event metrics recomputed; six model/budget summaries match within `2.23e-16`. Three RF seeds replayed, D05 thresholds exactly match, and all 6 RF test rows match the included event metrics (max difference 0). | Normal-only suite and later RF optimization are separate source runs. Neither is proven the historical figure source. |
| `fig:fault_localization` | `localization/code/`, data contract, 612 prepared windows, five classifier variants, three seeds, probabilities and reports | All 15 saved checkpoints replayed: 9,180 class predictions and 110,160 probability values. Class labels match exactly; max probability difference `2.23e-16`; 24 paper metric cells differ by at most `2.23e-16`. | Later fixed-split evaluation with documented role resolution; historical manuscript/figure lineage is unconfirmed. |
| `tab:imputation_results` | `imputation/code/`, train/evaluation windows, masks, checkpoints, predictions, and result tables | All six checkpoint pipelines replayed over six evaluation slots. 54 prediction files, 6,748,290 rows, and 12,636 metric rows match saved outputs exactly (bitwise numeric arrays, including NaNs). | Later offline reconstruction experiment; historical manuscript lineage is unconfirmed. |

The displayed prediction table has three target series (N3 downlink, N6 aggregate, host CPU). The configuration also contains other targets and ablations; the flow-RTT proxy is not a reported main-table series.

## Current 1 s exports and 400-entry dictionary

`../data_machine/dataset/timeseries_1s/` contains the seven current D01–D07 exports: 81 columns each, 611,777 rows total, and exact one-second UTC increments. `../data_machine/dataset/metadata/PLATFORM_FIELD_DICTIONARY_400.csv` has 400 unique canonical entries, 215 with `field_role=metric`. Among field definitions marked as metrics that occur in the current 81-column schema, 39 are present by name: 25 `ok`, one `replaced`, three `snapshot_only`, and ten `capability_missing` per run. The paper's historical count of 32 numeric indicators therefore has no exact mapping to this current schema/dictionary version. The exact historical field version remains unverified.

The 5 s task tables each contain 24 observations and share UTC timestamps that intersect the 1 s exports. Direct same-timestamp values for sampled host metrics are not equal, so the package does not establish that the task tables were created by simple 1 s resampling. See `verification/results/data_schema_verification.json`.

## Saved-output recomputation, inference, and training

- Saved-output recomputation: `verify_paper_tables.py` and `prediction/verify_saved_predictions.py`; no model inference.
- Checkpoint inference: scripts in `verification/`; outputs are separate summaries under `verification/results/`. They do not fit models.
- Training: bundle-only helpers under `verification/` create a fresh run directory and a `NEW_RUN_MANIFEST.json`. Every new fit is separately identified. They use D01–D04 for fit and D05 for selection; any D06/D07 evaluation occurs only after the fit freeze and is post-hoc.

## Interpretation limits

D06/D07 were previously accessed and are not blind tests. Known-start classification conditions on an already recorded injection time; it is not onset detection or causal root-cause analysis. Imputation is offline reconstruction of artificially masked values that were originally finite, with observations on both sides of a gap; it is not online repair. The original PCAP files are not included and are not needed for these table-level replays.
