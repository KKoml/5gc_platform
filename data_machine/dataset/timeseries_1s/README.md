# 1 s Platform Time-Series Exports

D01–D07 each contain `v3_timeseries.csv.gz` and `v3_field_coverage.json`. The seven tables contain 611,777 rows in total and share an 81-column schema. The [export index](../metadata/TIMESERIES_1S_INDEX.json) lists the row count and coverage summary for each run.

Read the compressed CSV files with Python's gzip and csv modules or with `pandas.read_csv`, which detects gzip compression from the filename. Empty values, observed values, and timestamps are retained.

A 1 s table grid does not imply that every source was sampled once per second. Coverage reports distinguish available observations, missing capabilities, substitutions, and snapshots. Operation labels, outcomes, and recovery fields require task-specific handling before use as model inputs.

D01–D04 are training runs, D05 is used for validation and model selection, and D06–D07 are post hoc test runs. These platform exports are separate from the [5 s observations](../task_data/data/README.md) and [forecast inputs](../../../prediction_inputs/README.md); they do not replace those task-specific inputs. See [task construction](../../../appendix/D3_data_construction.md) for the corresponding rules.
