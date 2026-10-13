# Shared Core Observations

Each run has its own directory. [runs.csv](../metadata/runs.csv) lists the run names, evaluation roles, and relative paths.

| File in each run directory | Contents |
| --- | --- |
| `core_features_5s.csv.gz` and `core_features_5s.parquet` | Run and time fields plus 24 observation variables; original missing values are retained |
| `source_age_5s.parquet` | Source-age information for interpreting observation freshness; not a default model input |
| `source_context_index.csv.gz` | Earlier context records for interpreting activity and recovery intervals |
| `episodes.csv` | Recorded core interventions, start/end times, and associated targets |
| `user_behavior_events.csv` | Access-side activity, kept separate from core-fault labels |
| `recovery_audit.csv` and `excluded_episode_audit.csv` | Recovery and event-exclusion records |

The current window selections and feature rules are described in the [task-index guide](../tasks/README.md) and [task construction appendix](../../../../appendix/D3_data_construction.md). Earlier context labels do not replace those definitions. Run boundaries and gaps must be retained when constructing windows.

These tables provide processed observations for evaluation. PCAP files and complete original collection logs are not included.
