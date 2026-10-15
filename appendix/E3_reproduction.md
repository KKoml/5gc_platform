# Appendix E.3 — Reproduction guide

**Data and entry points:** This repository includes [platform time-series tables and 5 s task data](../data_machine/dataset/README.md), [forecast histories and targets](../prediction_inputs/README.md), [forecast indices](../evaluation_package/evaluation/prediction/outputs/indices/), [classification windows](../evaluation_package/evaluation/localization/cache/), and imputation [window data](../evaluation_package/evaluation/imputation/data/), [artificial masks](../evaluation_package/evaluation/imputation/masks/), and [training scales](../evaluation_package/evaluation/imputation/metadata/scales.npz). Install the dependencies below before execution. PCAP is explicitly excluded; complete raw collection logs and workload-input corpora are not included. See [data access](../DATA_ACCESS.md).

First run `sha256sum -c SHA256SUMS.txt` from the repository root. Use a separate writable copy for execution: some verification programs write to `evaluation_package/evaluation/verification/results/`, and forecast inference creates a temporary cache. Preserve the archived copy and original experiments. Table-level entry points do not require the original experiment directories or raw PCAP.

Install `evaluation_package/evaluation/verification/requirements-replay.txt` in an isolated environment. Neural inference additionally requires PyTorch/CUDA matching the historical record and suitable for the local machine; CPU inference has not been verified. The saved-statistic audit environment is in `checks/current/environment.json`. Check GPU availability and active experiments before checkpoint inference. The documentation update itself does not launch inference or training.

## E.3.1 — Recompute saved results without inference

```bash
cd evaluation_package/evaluation
python verify_paper_tables.py
python prediction/verify_saved_predictions.py
cd ../..
python tools/recompute_saved_metrics.py
python tools/recompute_detection_saved.py
python evaluation_package/evaluation/verification/verify_data_package.py
```

Inputs include saved predictions/indices; D05/test detection scores, thresholds, and events; classification probabilities/labels; imputation truth/predictions and training scales; and current 1 s exports/dictionaries and 5 s tables. Outputs include console receipts, forecast `outputs/T1_SAVED_OUTPUT_RECOMPUTATION.json`, receipts under `verification/results/`, and `checks/current/saved_metrics.json` and classification_recomputed.csv. These checks establish numerical agreement, the data contracts actually checked, and separately recorded source hashes. They do not perform inference or establish historical run identity.

## E.3.2 — Checkpoint inference

```bash
python evaluation_package/evaluation/verification/replay_prediction_checkpoints.py
python evaluation_package/evaluation/verification/replay_detection_checkpoints.py
python evaluation_package/evaluation/verification/replay_supervised_rf_checkpoints.py
python evaluation_package/evaluation/verification/replay_localization_checkpoints.py
python evaluation_package/evaluation/verification/replay_imputation_checkpoints.py
```

Inputs are forecast histories/targets and scales, task tables/indices, fitted preprocessing, weights, and fixed artificial masks. Outputs go to verification/results. Forecasting removes its temporary cache on exit; imputation uses a temporary directory. Retained receipts from 2026-10-03 cover 54 forecast model/data combinations, nine normal-only and three RF detection checkpoints, 15 classification models, six SAITS models, and 54 prediction files. This is previously executed verification, not inference rerun for the documentation update. Each program records numerical tolerances and exact identifier/mask/decision checks. Earlier neural checks used CUDA; CPU is unverified. Replay shows that checkpoints explain bundled outputs, not that the historical paper run has been identified.

## E.3.3 — Train from scratch using separate run directories

Choose a new empty directory outside the material tree. Entry points write `NEW_RUN_MANIFEST.json` without overwriting bundled checkpoints or results.

```bash
python evaluation_package/evaluation/verification/train_prediction_t1_from_bundle.py \
  --run-dir ../new-runs/forecast-hostcpu-xgboost --target host_cpu --model XGBoost
python evaluation_package/evaluation/verification/train_detection_from_bundle.py \
  --run-dir ../new-runs/fd-ae17 --model AE --seed 17 --skip-test
python evaluation_package/evaluation/verification/train_localization_from_bundle.py \
  --run-dir ../new-runs/known-start-classification
python evaluation_package/evaluation/verification/train_imputation_from_bundle.py \
  --run-dir ../new-runs/offline-imputation
```

Forecast fitting/selection reads only D01–D05; n3_downlink, n6_aggregate, PatchTST, and TimeFilter are also supported. Normal-only detection supports AE, KAN-AD, TranAD, and seeds 17/29/43; `--skip-test` stops after D05. The original supervised-RF entry point is `detection/supervised_rf/code/pilot.py`, with its protocol retained. A standalone portable RF training wrapper has not been verified; checkpoint replay is the verified entry point. Classification trains five variants × three seeds before frozen evaluation. Imputation prepares masks, trains M/H × three seeds, then performs frozen evaluation.

Retained isolated-training receipts from 2026-10-03 cover only three host_cpu/XGBoost seeds, AE17, 15 classification models, and six SAITS models. They do not verify fresh training of every forecast/detection model. These are post-paper runs and do not replace original results. No training is launched for this documentation revision.

Supplementary plotting entry points are `python paper_figures/plot_detection.py` and `python paper_figures/plot_localization.py`, run in a writable copy. They read adjacent CSV files and produce adjacent PDF/SVG/PNG files. The earlier audit reproduced these two plots with pixel-identical rendering at 1500 pixels against the then-current manuscript plots; PDF time metadata need not match. These are legacy supplementary evaluation plots, not Figures 1–3 of the current English paper.

## E.3.4 — Scope and access limitations

The repository provides 1 s exports, the 400-entry dictionary, 5 s task tables, and evaluation inputs listed above. It does not provide all logs, workload corpora, and deployment materials needed to reconstruct the complete original collection process; PCAP is excluded. Unresolved relationships among forecast inputs, 24-variable tables, and platform exports are documented in [LINEAGE.md](LINEAGE.md). Platform documentation, configuration evidence, and associated samples are under `platform_data/`; the review tree does not contain the collection-platform source code. Repository availability does not establish synchronization or readability of the anonymous entry. [RUN_GUIDE.md](../RUN_GUIDE.md) provides additional commands and the scope of prior verification.
