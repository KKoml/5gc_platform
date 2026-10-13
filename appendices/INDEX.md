# Appendix Index

The appendices describe the D-GATE platform, experiment configuration, collected data, and processing methods.

| Appendix | Contents | Supporting files |
| --- | --- | --- |
| [A. Platform implementation and deployment](APPENDIX_A.md) | Deployment structure, platform functions, and implementation details | [Module-to-implementation table](../tables/PLATFORM_DEVELOPMENT_MAP.csv) |
| [B. Experiment configuration and control](APPENDIX_B.md) | Network and traffic configuration, operations, and recovery checks | [Configuration](../tables/CONFIGURATION.csv), [operation settings](../tables/OPERATIONS.csv), and [executed operations](../tables/ACTUAL_OPERATIONS.csv) |
| [C. Data organization, formats, and coverage](APPENDIX_C.md) | File organization, field definitions, units, timestamps, and missing values | [File catalog](../tables/FILE_CATALOG.csv), [platform dictionary](../dictionaries/PLATFORM_FIELDS.csv), [base-table dictionary](../dictionaries/BASE_TABLE_81.csv), and [unit conventions](../tables/UNIT_AUDIT.csv) |
| [D.1–D.2. Association, alignment, and data construction](APPENDIX_D.md) | Session association, time aggregation, quality checks, and task-oriented data products | [Processing stages](../tables/PROCESSING_LINEAGE.csv) and [data-product guide](../handoff/README.md) |

## Data examples and run summaries

- [W1-D06 examples](../samples/W1-D06/README.md): configuration files, execution records, recovery checks, and data excerpts.
- [Run summaries](../tables/RUN_LEDGER.csv) and [field coverage](../tables/FIELD_COVERAGE.csv): duration, table size, and available observations across seven runs.
- [Provided-file catalog](../manifests/PROVIDED_FILES.csv): files included in this branch, with complete-file and sample status.
- [Raw-file inventory](../manifests/RAW_FILES.csv): full-run files listed for reference; complete raw-data downloads are not currently provided.

## AI tasks and evaluation

Appendix D.3 and Appendix E are available on the `main` branch under `appendix/`, alongside the code, saved models, and results in `evaluation_package/`. See the [AI evaluation directory guide](../experiment-machine/README.md) for the file paths.
