# Task Indices

Each directory contains `index.csv.gz` and `index.parquet` representations of its sample index.

| Directory | Use |
| --- | --- |
| [FD_detection](FD_detection/) | Windows for fault detection |
| [FL_localization](FL_localization/) | Original known-start event indices with 10-variable primary and 6-variable comparison settings; the final classification data definitions are linked below |
| [FP_forewarning](FP_forewarning/) | Additional pre-onset warning indices retained from the source data package; not the paper's network performance prediction task |

`start_row` and `stop_row` describe a zero-based, half-open interval in the same run's 5 s observation table. Eligible windows contain 12 steps. Rows with `eligible=false` are retained as excluded candidates. Normal-only detection fitting and preprocessing additionally require `normal_train_window`.

The source package's [feature sets](../metadata/feature_sets.json) include earlier 10-variable and 6-variable classification settings. For the paper's final classification models, use the [classification data definitions](../../../../evaluation_package/evaluation/localization/data_contract/) and [task construction appendix](../../../../appendix/D3_data_construction.md). The final evaluation uses 24-variable models, a 10-variable random-forest comparison, and a readiness/missingness comparison; it assumes a known injection start.

Index columns describe sample selection and labels, rather than model observations. In the additional warning indices, `next_core_*` and `seconds_to_next_core_onset` are evaluation labels and must not be used as input features.

For the paper's forecast histories and targets, see [prediction_inputs](../../../../prediction_inputs/README.md). Imputation uses the separate [prepared windows](../../../../evaluation_package/evaluation/imputation/data/) and [fixed masks](../../../../evaluation_package/evaluation/imputation/masks/). The [evaluation overview](../../../../evaluation_package/evaluation/README.md) links all four tasks.
