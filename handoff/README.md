# Data Products and Task Inputs

This directory describes the relationship between platform observations and the data products used to construct AI tasks. The platform's 1 s base table, 5 s Core24 candidate, and prediction views have separate construction rules.

| Data product | Reference | What it describes |
| --- | --- | --- |
| 1 s base table | [81-column dictionary](../dictionaries/BASE_TABLE_81.csv) and [processing stages](../tables/PROCESSING_LINEAGE.csv) | Fields and processing steps for the platform's base table |
| 5 s Core24 candidate | [Variable list](CORE24_CANDIDATE_FEATURES.json), [source-field mapping](CORE24_SOURCE_MATCH.csv), and [sample description](CORE24_SAMPLE_PROVENANCE.json) | The 24 variables, source streams, units, and conversions behind the example |
| Prediction views | [D06 view summary](CORE_SIDE_REPAIRED_VIEW_MANIFEST.json) and [builder details](REPAIR_PROGRAM_PROVENANCE.json) | Histories constructed from observations before each cutoff, with targets calculated in separate intervals |
| Raw data | [Download index](CLOUD_DATA_INDEX.csv) and [file inventory](../manifests/RAW_FILES.csv) | Full-run files; download links are not currently provided |

## Interpreting the data products

The Core24 candidate draws on NF resources, host resources, interface counters, and NF state. Its 5 s grid does not describe the native sampling interval of every source. Interface byte rates require conversion to bit/s, cumulative counters require a difference and reset policy, and CPU percentages and millicores describe different quantities. Readiness and missing observations also have distinct meanings.

The prediction builder uses source records available before the history cutoff. Its target interval is separate from that history. The historical base-table exporter uses some completed-flow summaries, so directly selecting its columns does not reproduce the prefix-based prediction construction.

The Core24 example and prediction-view summary document platform-side data products. Their correspondence to the final AI input files has not been established. The final task definitions, windowing, masks, splits, and training-set preprocessing are described in `appendix/D3_data_construction.md` on the `main` branch; see the [AI evaluation directory guide](../experiment-machine/README.md).

Small examples are available in [W1-D06](../samples/W1-D06/README.md). Reconstructing complete inputs requires the full source records and the corresponding task builders.

Prepared task inputs and their file hashes are now available on main under the paths listed in `DATA_ACCESS.md`, `manifests/dataset_files.csv`, and `manifests/input_manifest.csv`. Their upload does not establish the unresolved correspondence between this branch's Core24 example or repaired-view summary and the final task inputs. The full raw-data download gap above concerns reconstruction from collection records, not availability of the prepared evaluation inputs.
