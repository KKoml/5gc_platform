# Fault detection

The paper's four plotted methods are covered by two executed local sources, with their provenance kept separate.

## Normal-only models

`normal_only/` contains the source, configurations, fitted models, validation thresholds, and validation/test score outputs for AE, KAN-AD, and adapted TranAD. The six source rows (three methods × two target false-alarm budgets) match the paper's event-recall and false-alarm-rate means and sample standard deviations. The four detection-delay rows shown in the paper match as well. Additional delay values in the source are retained in fit outputs but are not added to the paper evidence table.

## Supervised random forest

`supervised_rf/` contains a separate later RF optimization source, including code, model files, D05 threshold receipts, and validation/test predictions for three seeds. Its two test-budget rows match the paper's reported recall, FAR, and their standard deviations. The source describes this as post-hoc offline optimization using previously accessed D06/D07 data; it is not a blind test.

The detection package keeps the RF source distinct from the normal-only source, which generated the AE, KAN-AD, and TranAD matching values. The paper table is a comparison across those runs, not output from one single training directory. Both source runs use the D06/D07 test domain represented by the data-machine task package.

## Evaluation limits and access

The included predictions carry per-window scores and decisions, and the fitted checkpoints/estimators and D05 thresholds are preserved. Event-level interpretation follows the included code and task event ledger. In the combined package, the bundle-only training helper locates `data_machine/dataset/task_data` automatically. This pass replayed all included normal-only and supervised RF checkpoints, recomputed D05 thresholds and frozen-threshold D06/D07 metrics, and separately trained AE/seed17 on D01-D04, selected it on D05, then evaluated it post-hoc on D06/D07. That new AE fit is not a replacement for any paper output. D06/D07 remain previously accessed, non-blind evaluations.
