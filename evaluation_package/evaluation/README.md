# Evaluation Overview

The evaluation covers four offline tasks using a fixed split of complete runs: D01–D04 for training, D05 for validation, and D06–D07 for post hoc testing. Preprocessing parameters are fitted on training data; model settings and detection thresholds are selected on validation data.

## Tasks and results

| Task | Main materials | Reported result |
| --- | --- | --- |
| [Prediction](prediction/README.md) | Model settings, selected models, and saved prediction metrics | Table III: MAE for N3 downlink bitrate, N6 aggregate bitrate, and host CPU utilization |
| [Detection](detection/README.md) | Normal-only and supervised models, thresholds, and event metrics | Figure 4: event recall and false alarms per hour |
| [Classification](localization/README.md) | Sequence models, random forests, and input comparisons | Figure 5: fault-type, associated-target, and joint accuracy |
| [Imputation](imputation/README.md) | Statistical baselines, SAITS-H/M, and missingness comparisons | Table IV: MAE under random and continuous missingness |

## Read or aggregate the saved results

The [paper result index](../../PAPER_RESULT_MAP.md) links each table and figure to its supporting files. From this directory, the following command aggregates the saved prediction and imputation metric tables:

```bash
python3 verify_paper_tables.py
```

The [figure directory](../../paper_figures/) contains the detection and classification summary data and plotting programs. These table and figure summaries do not require the full task datasets.

## Task inputs and further evaluation

See [task construction](../../appendix/D3_data_construction.md) for feature lists, windows, validity indicators, labels, and preprocessing, and [model parameters](../../appendix/E1_models_hyperparameters.md) for settings and seeds.

Prepared task inputs are included: [5 s observations and events](../../data_machine/dataset/task_data/data/), [task indices](../../data_machine/dataset/task_data/tasks/), and [prediction histories and targets](../../prediction_inputs/README.md). The task directories also contain prepared classification windows, imputation masks, and preprocessing scales. Use [Data access](../../DATA_ACCESS.md) and the [evaluation instructions](../../appendix/E3_reproduction.md) to find the files and runtime dependencies for each step. This update adds data without reporting new model execution.

Classification uses observations following a known injection start. Imputation uses artificial masks and observations on both sides of each gap. These task definitions are retained throughout the results.
