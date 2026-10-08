# Dataset guide

> Archived guide for the complete local experiment package. Paths and full-data references below describe that archive, not the current publication tree. For the current 81-column 1 s sample (20 rows), 5 s sample (10 rows), and 400-entry dictionary, see [Appendix B](../README.md). Full datasets remain withheld; the repository access scope is defined in DATA_ACCESS.md.

## Main files

- dataset/task_data/data/D01 through D07: 5 s core-feature tables, source-age tables, episode labels and derived context tables.
- dataset/task_data/tasks/FD_detection: detection index and eligible-sample metadata.
- dataset/task_data/tasks/FL_localization: known-start type/associated-target classification index.
- dataset/task_data/metadata/runs.csv: slot and split map with relative data paths; original raw paths are withheld from this candidate.
- dataset/task_data/imputation/: prepared model windows, validity arrays, frozen train/evaluation masks and scale metadata copied from the completed local experiment.
- dataset/task_data/metadata/EXPERIMENT_KPI_DICTIONARY.csv and FEATURE_COVERAGE_BY_RUN.csv: source-package task metadata. At the time of the original assembly, these task metadata files were distinct from the paper field dictionary. The current manuscript supplement now provides that separate 400-entry dictionary.

## Reading the archived 5 s sample

Run python3 dataset/samples/read_sample.py from the package root. It checks 20 rows, the D06 slot label, and 5 s timestamp continuity. It does not score a model.

## Access status

All included files are local files. Full raw packet/log/state/workload records are not included; dataset/raw_inventory.csv summarizes them without offering a public route. In the archived complete local package, seven existing 81-column 1 s platform exports were added under dataset/timeseries_1s/, with per-slot coverage reports. The current 400-entry platform dictionary is in dataset/metadata/. Historical paper-version identity remains unverified.


## Current schema audit

A streaming audit of all seven exports confirmed 81 columns each, 611,777 rows total, and strictly one-second UTC spacing. The platform dictionary has 400 distinct canonical entries; 215 rows are marked metric. In the current 81-column schema, 39 distinct dictionary entries with metric role occur by field name (per slot: 25 `ok`, one `replaced`, three `snapshot_only`, ten `capability_missing`). This count does not resolve the paper's historical “32 numeric metrics” statement; field-role membership and active numeric availability are distinct, and historical version identity is unverified.

The 5 s task tables contain 24 observations and their UTC timestamps intersect the 1 s exports. Same-timestamp values for sampled host metrics are not elementwise identical. The package therefore does not assert that the 5 s task tables are simple resamples of the 1 s exports. The full executed comparison is in `../../evaluation_package/evaluation/verification/results/data_schema_verification.json`.
