# Completed network-metric imputation experiment

This path-configured copy preserves prepared windows, fixed masks, checkpoints, predictions and metrics. DGATE_DATASET_ROOT is a 待配置数据位置 and must point to dataset/task_data for source-table loading.

- Saved-result table aggregation: run python3 verify_paper_tables.py from evaluation/.
- Full saved-result audit: run python3 code/audit.py from evaluation/imputation; it reads prepared inputs and saved predictions/checkpoints and may run substantial inference.
- Evaluation from saved windows: code/experiment.py evaluate after configuring the dataset path.
- From-scratch fit: use the combined-package command in `RUN_GUIDE.md`. A full six-checkpoint bundle-only fresh fit and post-freeze evaluation was executed; the run is recorded in `evaluation/verification/results/new_training/RETRAINING_VERIFICATION.json`. It is a new local run and does not replace the included paper-result artifacts.

The paper reports D06/D07 only. Completed supplementary slots remain identified in the full result ledger.
