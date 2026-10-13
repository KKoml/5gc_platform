# Network Performance Prediction Inputs

Each of D01–D07 contains two compressed tables:

| File | Contents |
| --- | --- |
| `T1_history.csv.gz` | Ordered 60 s histories at 1 s resolution, with observations before each sample cutoff |
| `T1_targets.csv.gz` | Target means, validity information, and sample identifiers for the corresponding target intervals |

For a cutoff `c`, history spans `[c−60,c)` and the target interval is `[c+60,c+70)`. These task-specific tables use the prefix-based construction described in the [task construction appendix](../appendix/D3_data_construction.md). They are separate from the [1 s platform exports](../data_machine/dataset/timeseries_1s/README.md).

The [prediction indices](../evaluation_package/evaluation/prediction/outputs/indices/) select eligible target rows and bind them to the history order. [INPUT_MANIFEST.json](INPUT_MANIFEST.json) lists the supplied files. [Prediction materials](../evaluation_package/evaluation/prediction/README.md) provide the model configurations, saved results, and related code.

D01–D04 supply training data, D05 supplies validation data, and D06–D07 supply post hoc test data. The [run guide](../RUN_GUIDE.md) includes commands for recalculating saved metrics, checkpoint inference, and training in a separate output directory.
