# Dataset and Task Inputs

This directory contains the platform time-series exports, 5 s core observations, labels, and task indices supplied with the evaluation.

| Material | Contents |
| --- | --- |
| [1 s platform exports](timeseries_1s/README.md) | Full 81-column tables for D01–D07, with per-run coverage reports |
| [5 s core observations](task_data/data/README.md) | Run-level tables containing 24 observation variables, event records, and recovery information |
| [Task indices](task_data/tasks/README.md) | Window and event selections, with links to the final evaluation definitions |
| [Field definitions and run summaries](metadata/README.md) | The screened W1 dictionary, the archived 400-entry catalog, and an index of the 1 s exports |
| [Small example](samples/README.md) | Twenty contiguous rows from D06 for inspecting the 5 s format |
| [Prediction inputs](../../prediction_inputs/README.md) | Task-specific history and target tables for network performance prediction |
| [Evaluation instructions](../../RUN_GUIDE.md) | Saved-result calculations, data checks, checkpoint inference, and training entry points |

D01–D04 are the training runs, D05 is used for validation and model selection, and D06–D07 are previously accessed, post hoc test runs. Additional directories have separate development, diagnostic, or supplementary roles listed in [runs.csv](task_data/metadata/runs.csv).

The screened W1 dictionary contains 277 retained definitions, including contextual fields; it is not a fixed feature tensor. The 400-entry platform catalog remains a historical reference with a complete screening crosswalk. The platform export retains 81 columns, while the shared 5 s observation table has 24 variables plus run and time fields. These are separate counting scopes and products. Neither output grid establishes the native sampling rate or a direct 1 s-to-5 s resampling lineage.

The supplied tables and task inputs support the evaluation procedures described in the package. They are not the full collection archive. PCAP files are excluded; complete original collection logs and traffic-input corpora are not included. The [raw-file inventory](raw_inventory.csv) lists source material, and [Data access](../../DATA_ACCESS.md) describes the release scope.
