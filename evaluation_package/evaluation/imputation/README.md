# Network Metric Imputation

This task reconstructs artificially masked UPF interface receive/transmit bitrates and host CPU utilization. Each window spans 300 s at 5 s resolution. Missingness is either 20% random masking or a continuous gap of 30, 60, or 120 s.

The comparisons include the training-set median, forward fill, linear interpolation, target-history SAITS-H, and multivariate SAITS-M. Evaluation uses only originally valid target values that were masked. Related interface or host-resource variables are masked together, and offline reconstruction can use observations on both sides of each gap.

## Materials

| Path | Contents |
| --- | --- |
| [Prepared windows](data/) | Per-run input arrays |
| [Fixed masks](masks/) | Artificial missingness patterns used in evaluation |
| [Preprocessing scales](metadata/scales.npz) | Training-derived scales |
| [Source code](code/) | Masking, model training, and evaluation |
| [Configuration](metadata/config.json) | Features, architecture, optimization, and masking settings |
| [Results](results/) | MAE summaries and comparisons by run, target, and missingness condition |
| [Main comparisons](results/main_comparison.csv) | SAITS-H/M and statistical baseline comparisons |

Table IV reports the two test runs, D06 and D07. SAITS training uses seeds 17, 29, and 43; the three fixed mask seeds are 101, 202, and 303. Results are averaged over masks and training seeds, then equally over the two runs.

Use the [evaluation overview](../README.md) to aggregate the saved table. [Task construction](../../../appendix/D3_data_construction.md) and [model parameters](../../../appendix/E1_models_hyperparameters.md) give the detailed masking and model settings.

Prepared windows, fixed masks, and preprocessing scales are included in this directory. See [Data access](../../../DATA_ACCESS.md) and the [evaluation instructions](../../../appendix/E3_reproduction.md) for calculations from individual predictions, checkpoint inference, and training requirements.
