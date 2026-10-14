# D-GATE Supplementary Materials: Platform and Data

This branch contains the English platform and data appendices, field dictionaries, experiment configurations, and data examples for D-GATE. Start with the [appendix index](appendices/INDEX.md), or use the guide below.

## Reading guide

| Topic | Materials |
| --- | --- |
| Platform implementation and deployment | [Appendix A](appendices/APPENDIX_A.md) and [module-to-implementation table](tables/PLATFORM_DEVELOPMENT_MAP.csv) |
| Experiment configuration and control | [Appendix B](appendices/APPENDIX_B.md), [configuration table](tables/CONFIGURATION.csv), and [operation settings](tables/OPERATIONS.csv) |
| Data organization and field definitions | [Appendix C](appendices/APPENDIX_C.md), [platform field dictionary](dictionaries/PLATFORM_FIELDS.csv), and [81-column base-table dictionary](dictionaries/BASE_TABLE_81.csv) |
| Session association and data processing | [Appendix D.1–D.2](appendices/APPENDIX_D.md) and [processing stages](tables/PROCESSING_LINEAGE.csv) |
| Configuration and data examples | [W1-D06 sample guide](samples/W1-D06/README.md) |
| Data products and AI task materials | [Data-product guide](handoff/README.md) and [AI evaluation directory guide](experiment-machine/README.md) |

## Data included

The sample directory contains complete configuration and execution-report files for W1-D06, recovery checks, and excerpts of metrics, events, session records, packet-derived flows, and processed tables. The [provided-file catalog](manifests/PROVIDED_FILES.csv) identifies complete files and excerpts. [Run summaries](tables/RUN_LEDGER.csv) and [field coverage](tables/FIELD_COVERAGE.csv) describe the seven runs.

These examples are not the complete dataset. Full original runs, packet captures, and large logs are listed in the [raw-file inventory](manifests/RAW_FILES.csv); download links are not currently provided. The 5 s Core24 example is a separate data product whose correspondence to the final AI inputs has not been established.

## Platform source and AI evaluation

[Platform source](platform/source/) contains selected modules for experiment control, data collection, fault injection, recovery checks, and data processing, together with selected network-function implementations. Running the platform requires the deployment dependencies and local configuration described in [Appendix A](appendices/APPENDIX_A.md). See the [license and attribution notes](licenses/NOTICE.md).

AI task construction, model settings, saved models, and evaluation results are available on this repository's `main` branch under `appendix/` and `evaluation_package/`. The [AI evaluation directory guide](experiment-machine/README.md) lists the relevant paths.

## Current manuscript and appendix numbering

The current English six-page paper cites the A–D series in `main/manuscript_supplement/README.md`. This platform branch uses A for implementation/deployment, B for configuration/control, C for data organization, and D.1–D.2 for processing. See `APPENDIX_NAVIGATION.md` on main for the correspondence. Main also now includes the prepared AI datasets and input contracts; this branch's raw-data download gaps do not mean those prepared inputs are absent.
