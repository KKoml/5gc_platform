# Field Definitions and Run Summaries

| File | Contents |
| --- | --- |
| [Platform field dictionary](PLATFORM_FIELD_DICTIONARY_400.csv) | 400 field definitions, including 215 metrics, with sources, units, and availability information |
| [1 s export index](TIMESERIES_1S_INDEX.json) | Row counts, run roles, table width, and coverage summaries for D01–D07 |
| [Task observation dictionary](../task_data/metadata/EXPERIMENT_KPI_DICTIONARY.csv) | Definitions for the 24 variables in the 5 s observation tables |

The platform dictionary describes field capabilities across data sources. An entry does not imply a valid observation in every run. The [1 s tables](../timeseries_1s/README.md) include per-run coverage reports describing available, unavailable, replaced, and snapshot fields.

Dictionary definitions, the 81 columns in each platform export, and the 24 task observation variables are separate scopes. See [task construction](../../../appendix/D3_data_construction.md) for the variables actually used in each evaluation.
