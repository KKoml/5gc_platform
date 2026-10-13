# Local run guide

Run commands from the extracted package root. They write verification outputs below `evaluation_package/evaluation/verification/results/`; the supplied paper-result files remain read-only. Model replays and the neural fits require a working PyTorch install; neural fits were run with CUDA, while CPU fallback has not been validated. The recorded validation environment is in `evaluation_package/evaluation/verification/runtime_environment.json`. Install pinned non-PyTorch packages with `python -m pip install -r evaluation_package/evaluation/verification/requirements-replay.txt`, then install the PyTorch wheel compatible with the local CUDA/CPU environment separately.

## 1. Recompute saved results

```bash
cd evaluation_package/evaluation
python verify_paper_tables.py
python prediction/verify_saved_predictions.py
cd ../..
```

The first command compares saved paper-table aggregates. The second recomputes per-seed forecasting MAEs, the nine table cells, and the 54 input-ablation values from the supplied predictions and indices. Neither command runs model inference or fitting.

## 2. Verify data tables

```bash
python evaluation_package/evaluation/verification/verify_data_package.py
```

This streams all seven compressed 1 s tables, checks each full schema, row total, UTC one-second grid, coverage reports, field dictionary counts, and the 5 s task tables. It records that same-timestamp host values are not elementwise identical; it does not claim a 1 s-to-5 s resampling lineage.

## 3. Replay saved checkpoints

```bash
python evaluation_package/evaluation/verification/replay_prediction_checkpoints.py
python evaluation_package/evaluation/verification/replay_detection_checkpoints.py
python evaluation_package/evaluation/verification/replay_normal_only_metrics.py
python evaluation_package/evaluation/verification/replay_supervised_rf_checkpoints.py
python evaluation_package/evaluation/verification/replay_localization_checkpoints.py
python evaluation_package/evaluation/verification/replay_imputation_checkpoints.py
```

These compare inference outputs to the supplied saved outputs; they do not retrain. Prediction reconstructs temporary T1 tensors from the bundled histories. Detection recalibrates thresholds from D05 only and evaluates D06/D07 with those fixed thresholds. The imputation command evaluates into a temporary directory. All generated summaries are kept separate from the saved paper-result files.

## 4. Start a fresh training run

Choose a new, empty run directory outside the package so new artifacts cannot replace bundled results. The scripts write a `NEW_RUN_MANIFEST.json` with code/input hashes, seeds, fit records, checkpoints, metrics, environment, and resource evidence.

Forecasting (example; one target and method, all three seeds, D05 selection only):

```bash
python evaluation_package/evaluation/verification/train_prediction_t1_from_bundle.py \
  --run-dir ../dgate-new-runs/forecast-hostcpu-xgboost \
  --target host_cpu --model XGBoost
```

Use `n3_downlink` or `n6_aggregate` and `PatchTST`, `TimeFilter`, or `XGBoost` for other paper-target runs. The helper imports only D01–D05 windows for fitting and selection; it does not read D06/D07.

Detection (example):

```bash
python evaluation_package/evaluation/verification/train_detection_from_bundle.py \
  --run-dir ../dgate-new-runs/fd-ae-seed17 --model AE --seed 17
```

The helper supports AE, KAN-AD, and adapted TranAD seeds 17, 29, and 43. It trains on D01–D04, selects the checkpoint and calibrates thresholds on D05, then optionally computes a separate D06/D07 post-hoc report. Use `--skip-test` to stop after D05.

Known-start 12-class classification (full five variants × three seeds, with post-freeze evaluation):

```bash
python evaluation_package/evaluation/verification/train_localization_from_bundle.py \
  --run-dir ../dgate-new-runs/classification-full
```

Imputation (fresh data/mask preparation, six fits, then post-freeze evaluation):

```bash
python evaluation_package/evaluation/verification/train_imputation_from_bundle.py \
  --run-dir ../dgate-new-runs/imputation-full
```

Imputation uses only D01–D04 to fit and D05 for checkpoint selection. D06/D07 and supplementary slots are accessed only after all six checkpoints are frozen. All these new runs are separate post-paper executions and must not replace paper outputs or be reported as historical runs.

## 5. Access and limits

The repository includes the [platform tables and task observations](data_machine/dataset/README.md), [forecast histories and targets](prediction_inputs/README.md), [prediction indices](evaluation_package/evaluation/prediction/outputs/indices/), [classification windows](evaluation_package/evaluation/localization/cache/), and imputation [windows](evaluation_package/evaluation/imputation/data/), [masks](evaluation_package/evaluation/imputation/masks/), and [preprocessing scales](evaluation_package/evaluation/imputation/metadata/scales.npz).

These are the prepared inputs for the supplied evaluation code. PCAP files are excluded. Complete original collection logs and traffic-input corpora are not included, and the supplied inputs do not constitute a full reconstruction of the collection archive. See [Data access](DATA_ACCESS.md) for the release scope. Availability in this repository does not by itself establish access through the paper's anonymous entry. D06/D07 are post hoc test runs.
