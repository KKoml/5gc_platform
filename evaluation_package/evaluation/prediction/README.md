# Network performance prediction

This folder contains the locally found later `T1` source run whose saved outputs match the paper's N3 downlink, N6 aggregate, and host CPU results. It includes source code, paper-target configuration, selected model-search records, checkpoints/estimators, validation records, D06/D07 per-sample predictions, task indices, and metrics. Lower-scoring and incomplete methods remain included.

## Recompute the reported table

Run `python3 verify_saved_predictions.py` from this directory. It checks index/prediction row alignment, recomputes 200 saved-output MAEs within `3e-8` in native reported units, verifies the input-ablation values, and recalculates the nine table cells using the paper's order: equal-weight D06/D07 per seed, followed by mean and sample standard deviation across seeds. It performs no inference or fitting.

The main table's nine cells and 54 per-run/seed input-ablation values match the current paper evidence. D06/D07 were previously accessed and are post-hoc evaluation data.

The combined-package replay rebuilt T1 tensors from the adjacent `prediction_inputs/` histories and replayed 54 checkpoint/held-out outputs for the three paper targets. IDs and labels matched exactly and the maximum prediction difference was 0.0. The bundle-only training helper fits a selected T1 target/model from D01-D04 and selects on D05 without copying or reading D06/D07. A fresh XGBoost host-CPU fit for seeds 42/43/44 was executed; this verifies that path independently, not every paper target/model combination.

## Contents and limits

- `src/` contains the run source modules. `third_party/timefilter/` contains the vendored TimeFilter dependency used by the paper-target run and its retained license/attribution notes; other libraries are listed in the environment/configuration rather than copied as vendor trees.
- `resolved_config.yaml` and `spec/`: experiment and model settings with private absolute paths replaced by reviewer-configuration placeholders.
- `outputs/indices/`, `outputs/predictions/`, and `outputs/metrics_long.csv`: saved test indices, predictions, and metrics. Stable run identifiers were mapped consistently; sample order, values, and numeric results were retained.
- `outputs/jobs/`: candidate and final checkpoints, estimators, selection records, and validation predictions for the three paper targets. The T1 run's low-performing methods remain present.
- `outputs/SELECTION_FROZEN_T1.json`: a filtered view of the larger source freeze, limited to the paper targets. Its original combined-source hash is retained as a receipt.

The full 3.3 GB preprocessed tensor cache is not copied. The combined archive instead includes the T1 history/target tables under `prediction_inputs/` so replay and the documented bundle-only T1 fit do not need the old external cache. The source run's full legacy preparation path still expects these optional roots for non-bundled supplementary workflows:

- `DGATE_PREFIXFIX_LEGACY_PARENT`
- `DGATE_PREFIXFIX_SUPPLEMENT_ROOT`
- `DGATE_PREFIXFIX_INPUT_PACKAGE`
- `DGATE_PREFIXFIX_SOURCE_ARCHIVE`

The shipped `resolved_config.yaml` marks the legacy dataset and task-root entries as `REVIEWER_CONFIGURE_*`. Configure them only for the legacy full-source preparation path. For the T1 path verified here, follow `RUN_GUIDE.md`; it reconstructs tensors from bundled histories and writes new outputs outside the release package.

## Source status

The included run is a later four-field prefix-repaired evaluation. Its 9 table cells and 54 input-ablation values reproduce the paper evidence, including the seed-level standard deviations. This supports the numeric and code correspondence. It does not prove that this run produced the historical manuscript values. Its own record describes D06/D07 as previously accessed post-hoc evaluation data.
