# Data Documentation

The following materials describe the collected observations, field definitions, and task data used in the evaluation.

| Material | Description |
| --- | --- |
| [1 s platform exports](dataset/timeseries_1s/) | D01–D07 exported tables, with 81 columns per table |
| [5 s task data](dataset/task_data/data/) | Core observations, events, and recovery information by run |
| [Task indices](dataset/task_data/tasks/) · [Metadata](dataset/task_data/metadata/) | Sample definitions, features, labels, and evaluation splits |
| [Prediction inputs](../prediction_inputs/README.md) | Prediction histories and target tables for D01–D07 |
| [Dataset guide](docs/DATASET_GUIDE.md) | Data organization, observation tables, and field availability |
| [Platform guide](docs/PLATFORM_GUIDE.md) | Platform components and data-processing context |
| [Field dictionary](../manuscript_supplement/data/field_dictionary.csv) | Definitions, units, sources, and availability for 400 fields |
| [1 s example](../manuscript_supplement/data/timeseries_1s_sample.csv) | Twenty rows from the 81-column platform export |
| [5 s example](../manuscript_supplement/data/core_features_5s_sample.csv) | Ten rows containing 24 core observations plus run and time information |
| [Task construction](../appendix/D3_data_construction.md) | Input variables, windows, labels, and preprocessing for the four tasks |

The prepared task data and exported tables are included in this branch. The small examples offer a quick view of their formats. PCAP files are excluded, and the complete original log collection is not included. See [Data access](../DATA_ACCESS.md) for the data products and their uses.

The 1 s export and 5 s task observations are separate products. Their shared timestamps do not imply that the latter is a direct resampling of the former.
