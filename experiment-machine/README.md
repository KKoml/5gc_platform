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

The platform branch contains configuration and data examples; the AI materials are on `main`. Complete raw-data downloads are not currently provided, so full input reconstruction, inference replay, and training require additional data. The available reproduction instructions distinguish calculations from saved results from these data-dependent steps.

For platform-side input examples and their relationship to task data, see the [data-product guide](../handoff/README.md) and [appendix index](../appendices/INDEX.md).
