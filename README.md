# Supplementary Materials

**A Controlled 5G Core Data Generation Platform for AI Task Evaluation**

This repository provides experiment descriptions, field definitions, data examples, model configurations, evaluation code, and saved results accompanying the paper.

## Start here

| Material | What it contains |
| --- | --- |
| [Supplementary appendix](manuscript_supplement/README.md) | Platform functions, experiment settings, data formats, task construction, and model parameters |
| [Field dictionary](manuscript_supplement/data/field_dictionary.csv) | 400 field definitions with types, units, sources, and availability information |
| [1 s data example](manuscript_supplement/data/timeseries_1s_sample.csv) · [5 s data example](manuscript_supplement/data/core_features_5s_sample.csv) | Examples of the 81-column export and the core observation table |
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

Small data examples are included for reading the formats. Full datasets are not yet available for download; [Data access](DATA_ACCESS.md) explains which evaluation steps require them. Saved summary tables and the supplied figure data can be inspected without the full datasets.

Expanded English platform and data appendices, run examples, and selected platform source are available on the `codex/platform-data-appendices-20261007` branch, under `appendices/`, `samples/`, and `platform/source/`.
