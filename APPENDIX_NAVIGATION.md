# Review navigation

The latest English manuscript uses one supplementary A–D series. Start with [the readable appendix](manuscript_supplement/README.md); do not switch branches to read the platform evidence.

| Appendix | Main content | Expanded supporting files |
| --- | --- | --- |
| A | Platform implementation, deployment, configuration, control and recovery | [Implementation](platform_data/details/IMPLEMENTATION.md), [configuration](platform_data/details/CONFIGURATION.md), [development map](platform_data/tables/PLATFORM_DEVELOPMENT_MAP.csv) |
| B | Data organization, dictionary, units, coverage and examples | [Data contract](platform_data/details/DATA_CONTRACT.md), [dictionary guide](platform_data/dictionaries/README.md), [one-run linked examples](platform_data/samples/W1-D06/README.md) |
| C | Separate prediction/Core24 construction, preprocessing, windows and splits | [Processing/quality](platform_data/details/PROCESSING.md), [detailed task construction](appendix/D3_data_construction.md), [lineage](appendix/LINEAGE.md) |
| D | Actual configurations, model hyperparameters, seeds, saved results and reproduction | [Model detail](appendix/E1_models_hyperparameters.md), [result correspondence](appendix/E2_results_correspondence.md), [reproduction](appendix/E3_reproduction.md) |

`appendix/D3_*.md` and `appendix/E*.md` retain historical filenames for link compatibility; they are supporting technical records, not a competing appendix-number series. Their original-language details are preserved. `platform_data/details/` uses descriptive filenames rather than a second A–D series.

Figure 1: architecture; Figure 2: deployment; Figure 3: physical testbed. Table I: data categories; Tables II–V: the four task results; Algorithm 1: collection workflow. The [manuscript fingerprint](manifests/english_manuscript.json) matches the owner's latest PDF.

No collection-platform source is in this review tree. Evaluation/task-processing code is retained. Prior Git history may retain source uploaded earlier; no force push or history rewrite was performed. [Checks](CHECKS.md) and [anonymous access status](PUBLICATION_STATUS.md) distinguish local verification from reviewer availability.
