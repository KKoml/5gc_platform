# Fault Classification and Associated-Target Identification

The task classifies observations from the first 60 s after a known injection start. Twelve joint classes combine six fault types with two associated UPF targets. Location refers to the UPF or its associated path.

The fixed split contains 288 training, 72 validation, and 144 test cases. LSTM and TCN use 12-step sequences with 24 variables and validity indicators. Random forests use window statistics, with comparisons between 24 variables, 10 variables, and readiness/missingness-only inputs. Models use seeds 17, 29, and 43.

## Materials

| Path | Contents |
| --- | --- |
| [Prepared windows](cache/windows.npz) | Input arrays for the fixed classification samples |
| [Sample descriptions](data_contract/) | Indices, class counts, coverage, and window boundaries |
| [Source code](code/) | Sample preparation, model training, and evaluation |
| [Configuration](config.json) | Task settings and model parameters |
| [Fitted models](models/) | Model artifacts for the classifiers and input comparisons |
| [Result tables](metrics/) | Fault-type, associated-target, and joint classification metrics |
| [Summary](metrics/SUMMARY.csv) | Aggregated results used to describe the main comparisons |

The [figure directory](../../../paper_figures/) contains the summary data and plotting programs for Figure 5. See [task construction](../../../appendix/D3_data_construction.md) for class definitions and window rules, and [model parameters](../../../appendix/E1_models_hyperparameters.md) for the complete settings.

These results assume a known injection start; they evaluate classification rather than unknown-onset detection. Prepared windows and sample descriptions are included, together with the [underlying task observations](../../../data_machine/dataset/task_data/data/). See [Data access](../../../DATA_ACCESS.md) and the [evaluation instructions](../../../appendix/E3_reproduction.md) for inference and training requirements.
