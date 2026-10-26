# Paper result and figure map

This repository provides appendix materials for **Operational Data Collection and AI Algorithm Performance Validation Benchmark Platform for Core Network**. The [current paper-to-artifact map](../../PAPER_RESULT_MAP.md) is authoritative for the six-page English paper. The [navigation guide](../../APPENDIX_NAVIGATION.md) connects Appendices A–D to retained technical and historical records.

| Current paper item | Bundled evidence | Scope |
|---|---|---|
| Table I: data categories | [W1-specific field dictionary](../../manuscript_supplement/data/field_dictionary.csv) and [data package](../../data_machine/dataset/README.md) | Current category definitions; historical dictionary version remains unconfirmed |
| Section III-B: dataset setup | [1 s exports and 5 s task package](../../data_machine/dataset/README.md) | Seven 1 s exports contain 611,777 rows and 81 fields; the 24-variable task view has separate lineage |
| Table II: forecasting | [Forecast inputs](../../prediction_inputs/README.md), frozen indices, saved predictions, and fit records under evaluation_package/evaluation/prediction | 60 s history; D01–D04 fitting, D05 selection, D06/D07 post hoc testing |
| Table III: detection | Saved scores, thresholds, event records, and supervised-RF comparisons under evaluation_package/evaluation/detection | Normal-only and supervised regimes are distinguished; legacy detection plots remain supplementary |
| Table IV: classification and localization | Saved probabilities, checkpoints, sample contracts, and reports under evaluation_package/evaluation/localization | Twelve joint classes at known injection starts; 288/72/144 train/validation/test cases; no automatic onset detection or complete causal RCA claim |
| Table V: imputation | Windows, artificial masks, predictions, and saved summaries under evaluation_package/evaluation/imputation | Offline artificial-mask reconstruction with 24 input variables and three target metrics |
| Figures 1–3 and Algorithm 1 | [Platform details and samples](../../platform_data/details/INDEX.md), [manuscript supplement](../../manuscript_supplement/README.md) | Architecture, deployment, physical platform, and collection procedure; latest figure/photo sources are not bundled; collection-platform source is not distributed |

Evaluation inputs are included in this repository; PCAP, complete raw collection logs, and workload-input corpora are excluded. See [data access](../../DATA_ACCESS.md) and the [run guide](../../RUN_GUIDE.md). GitHub availability does not establish anonymous-mirror synchronization.

D06/D07 are previously accessed post hoc evaluation runs, not blind tests. Saved-output recomputation and checkpoint replay are distinct from fresh training and from establishing historical paper-run identity. See [lineage](../../appendix/LINEAGE.md) and the [full results correspondence](../../appendix/E2_results_correspondence.md). Historical receipts remain evidence of their recorded execution dates; this English documentation revision does not rerun inference or training.
