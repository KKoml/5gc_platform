# Known-start fault-type and associated-target classification

The included source run evaluates a 12-class joint label: six recorded injection mechanisms crossed with two associated UPFs. The window is the 12-step observation following a known injection start. The result is controlled-target classification; it does not predict an unknown onset or establish causal root cause.

The package includes the classification/training/evaluation source, 288/72/144 train/validation/test sample contract, feature whitelist and class labels, prepared input windows, 15 fitted model artifacts, per-sample class probabilities, and result tables. LSTM/TCN use 24 numeric channels plus 24 validity channels; the random-forest variants retain their distinct 24-variable, 10-variable, and ready/missingness-only inputs. All three seeds and the lower-scoring ablations are preserved.

`metrics/SUMMARY.csv`, `audit/RESULT_VERIFICATION.json`, and `tracker.json` are included for the report formatter. The included checkpoint replay compared probabilities for all 15 models across the 612 fixed windows: all predicted classes matched; max probability difference was 2.22e-16; all 24 paper-facing metric cells matched within 2.22e-16. The role-resolution helper also passed three accepted and eight rejected cases. A new full package-only fit completed all five classifiers × seeds 17/29/43 and generated 1,800 grouped metric rows after the test freeze.

Every one of the 15 model/seed rows matches the current paper evidence for fault-type accuracy, associated-target accuracy, joint accuracy, and macro-F1 with maximum absolute error `1.12e-16`. The metric result is therefore independently traceable to an executed local classifier source.

## Data-dependent preparation

The included `cache/windows.npz` and `data_contract/` support inspection of prepared cases and saved outputs. Full preparation requires the task package supplied through `DGATE_LOCALIZATION_DATA_PACKAGE`. The copied code uses this reviewer-configurable path in place of the author-machine path. A small legacy model-source reference is bundled under `legacy_reference/` for model provenance checks.

The result is a later additional fixed-split evaluation. Its record keeps a previously documented Core24h role conflict and the explicit resolution: Core24h remains supplementary-only, with no training cases. The D01–D07 paper split remains 288 training, 72 D05 validation, and 144 D06/D07 test cases. D06/D07 had been accessed previously and are not blind tests. The copied source freeze refers to the later source run; its code hashes do not describe the path-adapted release code. The new training helper emits a separate freeze for each fresh run. Neither the exact historical paper run nor the original figure generator is confirmed.
