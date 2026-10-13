# Data Access

The `main` branch includes the prepared AI task inputs and platform exports used by the accompanying evaluation materials. These files can be downloaded with the repository; no separate data download is required for the included inputs.

## Included data

| Data product | Location | Contents |
| --- | --- | --- |
| 1 s platform exports | [Exported tables](data_machine/dataset/timeseries_1s/) · [Run index](data_machine/dataset/metadata/TIMESERIES_1S_INDEX.json) | D01–D07, 81 columns per table, 611,777 rows in total |
| 5 s task observations and events | [Run data](data_machine/dataset/task_data/data/) | Core observations, episode records, recovery information, and source context |
| Prediction histories and targets | [Prediction inputs](prediction_inputs/README.md) | `T1_history` and `T1_targets` for D01–D07 |
| Prediction indices | [Target/run indices](evaluation_package/evaluation/prediction/outputs/indices/) | Fixed sample indices for the three prediction targets |
| Detection and classification indices | [Task indices](data_machine/dataset/task_data/tasks/) · [Task metadata](data_machine/dataset/task_data/metadata/) | Window membership, labels, split roles, feature definitions, and event information |
| Prepared classification windows | [Windows](evaluation_package/evaluation/localization/cache/windows.npz) · [Sample descriptions](evaluation_package/evaluation/localization/data_contract/) | Prepared arrays, sample indices, class counts, and window boundaries |
| Imputation data and masks | [Window data](evaluation_package/evaluation/imputation/data/) · [Fixed masks](evaluation_package/evaluation/imputation/masks/) | Prepared windows and artificial missingness patterns |
| Imputation scales and window metadata | [Preprocessing scales](evaluation_package/evaluation/imputation/metadata/scales.npz) · [Window metadata](data_machine/dataset/task_data/imputation/metadata/) | Training-derived scales, window indices, run information, and masking configuration |
| Field definitions | [Field dictionary](manuscript_supplement/data/field_dictionary.csv) | 400 definitions covering metrics and contextual fields |

The 1 s exports, 5 s observations, and prediction tables are separate data products. Matching timestamps do not establish a direct resampling relationship. See [task construction](appendix/D3_data_construction.md) for inputs and preprocessing, and [data lineage](appendix/LINEAGE.md) for documented relationships and remaining gaps.

The [data file index](manifests/dataset_files.csv) lists the included files.

## Using the data

[Evaluation instructions](appendix/E3_reproduction.md) describe saved-result calculations, checkpoint inference, and training. Saved summary tables can be aggregated without loading the task data; calculations from individual predictions and model execution use the linked inputs. Install the dependencies specified for each step. Including these files does not imply that inference or training has been rerun for this update.

## Collection records and platform code

**PCAP files are excluded from this release.** The repository also does not contain the complete set of original non-PCAP logs and raw collection records; [the raw-record inventory](data_machine/dataset/raw_inventory.csv) describes source material and does not imply that each listed file is included. Consequently, the included exports and task inputs do not by themselves provide every input needed to regenerate all derived data from raw collection records.

The platform implementation and expanded platform appendices are maintained separately on the `codex/platform-data-appendices-20261007` branch under `platform/source/` and `appendices/`. See [the repository overview](README.md). Anonymous reviewer access is tracked in [access status](PUBLICATION_STATUS.md).
