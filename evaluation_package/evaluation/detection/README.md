# Fault Detection

This task evaluates alarms over complete test runs. Autoencoder, adapted KAN-AD, and adapted TranAD are fitted to normal observations; the random forest uses both normal and fault labels.

## Materials

| Directory | Contents |
| --- | --- |
| [Observations and events](../../../data_machine/dataset/task_data/data/) | Run-level 5 s data and event records |
| [Detection indices](../../../data_machine/dataset/task_data/tasks/FD_detection/) | Detection samples and time-window indices |
| [Normal-only models](normal_only/) | Code, configurations, fitted models, scores, and metrics for autoencoder, KAN-AD, and TranAD |
| [Supervised random forest](supervised_rf/) | Code, configurations, fitted models, thresholds, and saved outputs for the supervised baseline |
| [Figure data and plotting](../../../paper_figures/) | Summary data and plotting programs for Figure 4 |

## Evaluation protocol

Thresholds are selected on D05 at targets of 0.1 and 1 false alarms per hour, then fixed for D06–D07. Consecutive alarms are merged and matched one-to-one with injected events. Results report event recall and observed false alarms per hour together, using valid normal observation time for the false-alarm denominator.

The three training seeds are 17, 29, and 43. Details of windows, adapted scores, event matching, and model settings are in [task construction](../../../appendix/D3_data_construction.md) and [model parameters](../../../appendix/E1_models_hyperparameters.md).

Summary metrics can be inspected directly. Task observations, event metadata, and indices are included for the documented evaluation workflow. See [Data access](../../../DATA_ACCESS.md) and the [evaluation instructions](../../../appendix/E3_reproduction.md) for event-metric calculations, checkpoint inference, and training requirements.
