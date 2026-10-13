# Supplementary Materials

**A Controlled 5G Core Data Generation Platform for AI Task Evaluation**

This repository provides experiment descriptions, field definitions, prepared datasets, model configurations, evaluation code, and saved results accompanying the paper.

## Start here

| Material | What it contains |
| --- | --- |
| [Supplementary appendix](manuscript_supplement/README.md) | Platform functions, experiment settings, data formats, task construction, and model parameters |
| [Field dictionary](manuscript_supplement/data/field_dictionary.csv) | 400 field definitions with types, units, sources, and availability information |
| [Platform exports and task data](data_machine/README.md) | 1 s exported tables, 5 s core observations, event records, and task indices |
| [Prediction inputs](prediction_inputs/README.md) | History and target tables for D01–D07 |
| [1 s data example](manuscript_supplement/data/timeseries_1s_sample.csv) · [5 s data example](manuscript_supplement/data/core_features_5s_sample.csv) | Small examples for viewing the table formats |
| [Evaluation materials](evaluation_package/README.md) | Code, configurations, fitted models, and results for the four AI tasks |
| [Paper result index](PAPER_RESULT_MAP.md) | Connections between paper tables and figures and their supporting files |
| [Evaluation instructions](appendix/E3_reproduction.md) | Commands and data requirements for aggregation, inference, and training |

## Evaluation tasks

| Task | Code and settings | Paper output |
| --- | --- | --- |
| Network performance prediction | [Prediction](evaluation_package/evaluation/prediction/README.md) | Table III |
| Fault detection | [Detection](evaluation_package/evaluation/detection/README.md) | Figure 4 |
| Fault classification and associated-target identification | [Classification](evaluation_package/evaluation/localization/README.md) | Figure 5 |
| Network metric imputation | [Imputation](evaluation_package/evaluation/imputation/README.md) | Table IV |

Detailed descriptions are available for [task construction](appendix/D3_data_construction.md), [model parameters](appendix/E1_models_hyperparameters.md), and [result aggregation](appendix/E2_results_correspondence.md).

## Data and platform materials

The prepared AI inputs and 1 s platform exports are included in `main`, together with task indices, prepared windows, fixed masks, and preprocessing scales. [Data access](DATA_ACCESS.md) links each data product to its evaluation use. PCAP files are excluded, and the complete collection of original logs and raw records is not included. The provided data support the documented evaluation workflow; regenerating every derived product from raw collection records requires additional source material.

Expanded English platform and data appendices, run examples, and selected platform source are available on the `codex/platform-data-appendices-20261007` branch, under `appendices/`, `samples/`, and `platform/source/`.
