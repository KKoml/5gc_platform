# AI Task and Evaluation Materials

The AI materials are available on this repository's `main` branch. Select `main` in the branch menu, then open the following paths.

| Topic | Path on `main` |
| --- | --- |
| Evaluation package overview | `evaluation_package/README.md` |
| Task inputs, windows, labels, and data splits | `appendix/D3_data_construction.md` |
| Models, hyperparameters, and random seeds | `appendix/E1_models_hyperparameters.md` |
| Paper results and supporting files | `appendix/E2_results_correspondence.md` |
| Reproduction instructions | `appendix/E3_reproduction.md` |
| Code, configurations, saved models, and results | `evaluation_package/` |

The evaluation covers forecasting, fault detection, fault classification with associated-target identification, and imputation. Classification uses windows aligned to known injection start times. Imputation evaluates artificial missingness in offline data.

The platform branch contains configuration and data examples; the AI materials are on `main`. Prepared evaluation inputs, indices, classification windows, imputation masks, and preprocessing scales are now included on main; `DATA_ACCESS.md` lists them, `manifests/dataset_files.csv` lists the uploaded files, and `manifests/input_manifest.csv` describes their contracts. Inference replay and training use these supplied inputs and the runtime dependencies specified by the reproduction guide. Full raw-data reconstruction remains a separate incomplete delivery: complete original logs, PCAP, and the original traffic corpus are not included. This documentation update does not report new inference or training.

For platform-side input examples and their relationship to task data, see the [data-product guide](../handoff/README.md) and [appendix index](../appendices/INDEX.md).

The current English paper reports prediction, detection, classification/localization, and imputation in Tables II–V. On main, open `APPENDIX_NAVIGATION.md` for the correspondence between the manuscript-supplement A–D series and the detailed D.3/E series. The platform branch uses its own A–D.2 headings.
