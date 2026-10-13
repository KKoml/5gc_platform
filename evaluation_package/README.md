# AI Task Evaluation

This directory contains code, model configurations, fitted models, and saved results for the four tasks evaluated in the paper.

| Task | Contents |
| --- | --- |
| [Network performance prediction](evaluation/prediction/README.md) | SMA, PatchTST, and XGBoost results, including input comparisons |
| [Fault detection](evaluation/detection/README.md) | Autoencoder, adapted KAN-AD, adapted TranAD, and supervised random forest |
| [Fault classification](evaluation/localization/README.md) | LSTM, TCN, and random-forest classification of fault types and associated targets |
| [Network metric imputation](evaluation/imputation/README.md) | Statistical baselines and SAITS-H/M under artificial missingness |

For the shared protocol and table-generation entry point, start with the [evaluation overview](evaluation/README.md). Detailed descriptions cover [task inputs](../appendix/D3_data_construction.md), [model hyperparameters](../appendix/E1_models_hyperparameters.md), and [result aggregation](../appendix/E2_results_correspondence.md).

## Using the materials

Saved metric tables can be read and aggregated directly. The repository also includes the prepared task inputs, indices, windows, masks, and preprocessing scales used by the evaluation workflow. [Data access](../DATA_ACCESS.md) links these files; the [evaluation instructions](../appendix/E3_reproduction.md) describe dependencies and commands for calculations from individual predictions, checkpoint inference, and training. This data update does not report new inference or training runs.
