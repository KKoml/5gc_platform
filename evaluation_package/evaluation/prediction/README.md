# Network Performance Prediction

The prediction task uses 60 s of history, followed by a 60 s gap, to estimate the mean target value over the next 10 s. The reported targets are N3 downlink bitrate, N6 aggregate bitrate, and host CPU utilization.

SMA averages the last 10 s of valid target observations. PatchTST uses target history; XGBoost uses 18 variables and validity indicators. Input comparisons also include target-history-only and time-variable-only settings.

## Materials

| Path | Contents |
| --- | --- |
| [Histories and targets](../../../prediction_inputs/README.md) | Prediction input tables for D01–D07 |
| [Sample indices](outputs/indices/) | Fixed target/run indices |
| [Source code](src/) | Input construction and model evaluation |
| [Experiment configuration](resolved_config.yaml) | Task and model settings |
| [Selected configurations](outputs/SELECTION_FROZEN_T1.json) | Model selection records for the paper targets |
| [Model runs](outputs/jobs/) | Candidate and selected models, configurations, and saved outputs |
| [Metrics](outputs/metrics_long.csv) | Results by target, model, run, and seed |

## Table III and input comparisons

For each seed, MAE is averaged equally over D06 and D07. The table reports the mean and sample standard deviation across seeds 42, 43, and 44; SMA requires no fitting. Bitrates are reported in Mbit/s and CPU errors in percentage points.

The [evaluation overview](../README.md) gives the command for aggregating the saved table. [Task construction](../../../appendix/D3_data_construction.md) and [model parameters](../../../appendix/E1_models_hyperparameters.md) describe the inputs and comparisons in detail.

Prediction histories, target tables, and sample indices are included in this branch. See [Data access](../../../DATA_ACCESS.md) and the [evaluation instructions](../../../appendix/E3_reproduction.md) for calculations from saved predictions, checkpoint inference, and training requirements.
