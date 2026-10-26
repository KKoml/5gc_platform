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
| Platform data-quality evidence | [Quality summary](platform_data/quality/README.md) · [Metrics](platform_data/quality/PLATFORM_QUALITY_METRICS.csv) | All remote-clock probe rows, anonymous source-log corroboration counts, session/capture projections and route-sample counts; no model scores |
| W1 field definitions | [W1-specific dictionary](manuscript_supplement/data/field_dictionary.csv) · [Screening guide](platform_data/dictionaries/W1_DICTIONARY_GUIDE.md) | 277 evidence-supported definitions; full 400-entry screening decisions are retained separately |

The 1 s exports, 5 s observations, and prediction tables are separate data products. Matching timestamps do not establish a direct resampling relationship. See [task construction](appendix/D3_data_construction.md) for inputs and preprocessing, and [data lineage](appendix/LINEAGE.md) for documented relationships and remaining gaps.

The [data file index](manifests/dataset_files.csv) lists the included files.

## Using the data

[Evaluation instructions](appendix/E3_reproduction.md) describe saved-result calculations, checkpoint inference, and training. Saved summary tables can be aggregated without loading the task data; calculations from individual predictions and model execution use the linked inputs. Install the dependencies specified for each step. Including these files does not imply that inference or training has been rerun for this update.

## Collection records and platform code

**PCAP files are excluded from this release.** The repository also does not contain the complete set of original non-PCAP logs and raw collection records; [the raw-record inventory](data_machine/dataset/raw_inventory.csv) describes source material and does not imply that each listed file is included. Consequently, the included exports and task inputs do not by themselves provide every input needed to regenerate all derived data from raw collection records.

Expanded implementation/configuration descriptions, source/version references and linked anonymized real-run examples are in [platform_data](platform_data/readme.md), without collection-platform source. Complete seven-run non-PCAP records and the current full traffic corpus are available separately through the [public Google Drive archive](https://drive.google.com/drive/folders/1cQTv0CbireblU9055l0rPhgnDDDSwLyJ). Each run has `01_Raw_Records`, `02_Derived_Data`, and `03_Reports` packages. Start with the [download and restore instructions](https://drive.google.com/file/d/15TNAxdYwus_3pCS2KRWLzte3bO69S5WQ/view) and [package index and checksums](https://drive.google.com/drive/folders/1ltfF2pHkPVJ3OV1Eb0Iml3Ir3Bicwaub); download every listed part and verify its SHA-256 before restoration. The restoration helper requires Python 3.12 or newer and a new empty output directory. PCAP/PCAPNG files are excluded. Historical source archives and transfer-test files remain private and outside the public folder. See [publication status](PUBLICATION_STATUS.md) for access checks and verification limits.
