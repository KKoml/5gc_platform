"""Build the English interpretation from completed, verified fixed-run results."""
import json
import pandas as pd
from pathlib import Path
R=Path(__file__).resolve().parents[1];s=pd.read_csv(R/'metrics/SUMMARY.csv');v=json.loads((R/'audit/RESULT_VERIFICATION.json').read_text());assert v['status']=='PASS'
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def metric(model,role,key):
 r=s[(s.model==model)&(s.role==role)&(s.stratum=='all')].iloc[0];return f'{100*r[key+"_mean"]:.2f} ± {100*r[key+"_std"]:.2f}'
models=['LSTM','TCN','RF_24','RF_FL10','ReadyMaskRF'];roles={'test':'D06–D07 reevaluation (144)','external_validation':'V4 (72)','supplementary_only':'Core24h closed set (24)'}
main=table(['Model','Evaluation set (cases)','Joint Top-1 %','Joint Macro-F1 %'],[[m,n,metric(m,r,'top1'),metric(m,r,'macro_f1')] for r,n in roles.items() for m in models])
rank=table(['Evaluation set','Joint Top-3 %','MRR','Mechanism accuracy %','Mechanism Macro-F1 %','Associated-target accuracy %'],[[n,metric('RF_24',r,'top3'),f"{s[(s.model=='RF_24')&(s.role==r)&(s.stratum=='all')].iloc[0].mrr_mean:.4f}",metric('RF_24',r,'mechanism_accuracy'),metric('RF_24',r,'mechanism_macro_f1'),metric('RF_24',r,'target_accuracy')] for r,n in roles.items()])
day=table(['Model','D06 Top-1 %','D07 Top-1 %'],[[m,metric(m,'D06','top1'),metric(m,'D07','top1')] for m in models])
mechanisms=['n3-block','n3-delay','n3-loss','n4-block','n6-block','instance-stop'];mrows=[]
for mechanism in mechanisms:
 vals=[]
 for role in roles:
  r=s[(s.model=='RF_24')&(s.role==role)&(s.stratum==mechanism)].iloc[0];vals.append(f'{r.top1_mean*100:.2f} ± {r.top1_std*100:.2f}')
 mrows.append([mechanism]+vals)
mt=table(['True mechanism','D06–D07 Joint Top-1 %','V4 Joint Top-1 %','Core24h Joint Top-1 %'],mrows)
comp=pd.read_csv(R/'reports/COMPOSITE_CASES.csv');comp=comp[(comp.model=='RF_24')&(comp.seed==17)];ct=table(['Compound case','True associated target','RF24 seed17 top three candidates (probabilities)'],[[r.fault_id,r.target,r.top3] for r in comp.itertuples()])
t=json.loads((R/'tracker.json').read_text());tt=table(['Model','seed','Training time (s)','Executed epochs','Selected epoch'],[[r['model'],r['seed'],f"{r['seconds']:.3f}",r['epochs_run'],r['selected_epoch'] if r['selected_epoch'] is not None else 'N/A'] for r in t])
report=f'''# RCA_joint12: controlled Core fault mechanism and associated-target diagnosis

Task status: **15/15 formal fits succeeded; held-out evaluation and result recomputation completed**. The earlier input-role blocker was resolved through the user-scoped clarification. The historical blocker report remains at `audit/history_blocked/FINAL_REPORT_ZH.md`; the original `audit/BLOCKER.json` and two discrepancy tables are retained unchanged. This report preserves the history of that blocker.

## 1. Conclusions

**The 24 collected observation columns support limited joint mechanism/associated-target diagnosis beyond distinguishing Gold/Silver paths, but do not establish stable separation of every mechanism or reliable diagnosis across settings.** RF24 joint Top-1 is 65.05% on D06–D07 and 64.81% on V4, exceeding RF10 and the Ready/missingness control on the same 12-class task. It falls to 45.83% on Core24h; both deep models degrade more substantially on Core24h.

Readiness/missingness alone does not explain all performance: ReadyMaskRF joint Top-1 is 25% in each of these three roles. For network-fault subsets ranked among all 12 candidates, RF24 achieves 58.06%, 57.78%, and 35.00%, versus 10% for ReadyMaskRF in each subset. These controls establish additional discriminative information in the current input/model combination; they do not establish causal mechanisms or exclude user-behavior confounding.

Path identification is stronger than mechanism discrimination: RF24 marginal associated-target accuracy is 100% on D06–D07 and mechanism accuracy is 66.67%; the corresponding Core24h values are 83.33% and 45.83%. These results support feasibility of joint diagnosis/candidate ranking in controlled settings, not a solution to the full RCA problem.

## 2. Task, labels, and role contract

The formal task is joint mechanism/associated-target diagnosis or root-cause candidate ranking from a fixed 60 s observation after a known recorded start, labeled by actual injection records. The 6 mechanisms are ordered n3-block, n3-delay, n3-loss, n4-block, n6-block, and instance-stop; each has upf-silver then upf-gold, giving 12 classes. Network mechanisms refer to Silver/Gold-associated paths, not exclusively internal UPF software faults. fault_id is used only for labels and audit, never as model input.

The delay/loss mapping verified on the source machine is recorded as `source_verified_rule_received_in_prompt`; the local audit did not access the original faults.jsonl. Existing quality flags such as `source_marked_inferred` remain unchanged and are not upgraded to independently established causal ground truth for service damage.

- Training: 288 D01–D04 cases, 24 per class; validation: 72 D05 cases, 6 per class.
- Additional reevaluation under the fixed existing split: 144 D06–D07 cases, 12 per class, 72 per run. These runs were previously accessed; this is neither new blind testing nor a chronological forward split.
- V4 external validation: 72 cases, 6 per class; Core24h supplementary closed set: 24 cases, 2 per class, plus 4 compound delay+loss cases; diagnostic5: 8 cases.
- 612 cases = 608 closed-set + 4 compound. The complete 621-entry ledger additionally excludes 8 AMF/SMF stop events and 1 V4 prelude. baseline2h is not used for training.

The only special Core24h run is `supp_core24h`. source_episode_run_split=event_block_protocol is retained, while registry_split/index_split/effective_split=supplementary_only. The rule applies only to the exact run, slot, and value combination, matching 36 ledger entries/28 FL cases. Core24h contributes 0 cases to preprocessing fits or training. All other inconsistencies still raise errors. See `data_contract/role_resolution.json` and `audit/BLOCKER_RELEASE.json`.

## 3. Inputs, preprocessing, and models

The original FL [start_row,stop_row) windows of 12 steps × 5 s are reused directly: one window per case, with no additional pre/post-event data. Actual cutoffs occur after the recorded start and within 60 s; the anchor lies near the observation end. Elementwise checks of all 612 windows and their time boundaries are in `data_contract/window_boundaries.csv`.

Main inputs are the 24 observations in the FD_detection_24 whitelist and their 24 masks. Minimum window coverage is 71.53%; W1 has no channel missing for an entire window. The fixed 0.5 coverage requirement retains all 612 cases. Raw NaN values remain in the cache. Median imputation and median/IQR scaling are fitted only to observed values from 288 training events; zero IQR falls back to training standard deviation, then 1. Observed Ready values remain 0/1, with separate masks. Training IDs, parameters, and coverage are saved.

LSTM uses two width-64 layers; TCN uses two residual blocks with dilations 1/2 and kernel 3. Both use dropout 0.1 and output 12 classes. Training uses cross-entropy, AdamW lr=0.001/weight_decay=0.0001, batch=32, and at most 50 epochs. Early stopping uses only D05 macro-F1 with patience 8, breaking ties by lower validation loss, then earlier epoch. Seeds 17/29/43 share the same configuration. Old checkpoints are not reused.

RF24 and RF10 extract each numerical channel's mean, population standard deviation, minimum, maximum, last value, last−first, and observed fraction, giving 168/70 features. ReadyMaskRF uses the same 6 value statistics for two Ready channels, stepwise masks for 24 columns, and observed fractions: 324 features, without CPU/memory/traffic values. All three RF variants use 500 trees, min_samples_leaf=2, max_features=sqrt, and max_depth=None. There is no grid search, oversampling, or case duplication.

## 4. Main results

Tables report three-seed means ± sample standard deviations, evaluated by event. Seeds are not independent physical collection repetitions and do not establish generalization significance. RF_24/RF_FL10 denote RF24/RF10.

{main}

The W1 uniform-random reference is joint Top-1=8.33%, Top-3=25%, mechanism accuracy=16.67%, and associated-target accuracy=50%. Probability ties strictly follow the frozen class order. The random reference is not an additional trained model.

RF24 ranking and marginal-classification results follow; corresponding metrics and standard deviations for every model are in `reports/FULL_TABLES_ZH.md`. Mechanism probabilities sum the same 12-class probabilities over associated targets; target probabilities sum over mechanisms. Marginal argmax can differ from components of the joint argmax. Two independently optimized models are not combined.

{rank}

Per-run results:

{day}

On diagnostic5, RF24 joint Top-1 is 95.83%±7.22% and macro-F1 is 97.22%±4.81%. This subset contains only 4 supported joint classes from n3-block and instance-stop, totaling 8 cases. Macro-F1 averages these 4 classes, while prediction still considers all 12. High scores on this small subset do not replace full-mechanism validation. Per-item support is recorded in `metrics/ALL_METRICS.csv`.

## 5. Controls and mechanism differences

Relative to RF10, RF24 joint Top-1 increases by 18.98 percentage points on D06–D07 (41.21% relative), 18.52 points on V4 (40.00%), and 11.11 points on Core24h (32.00%). This is the combined effect of adding 14 numerical channels and their masks/fractions, not a gain attributable to one KPI. Gains over ReadyMaskRF are 40.05, 39.81, and 20.83 percentage points. All model comparisons, paired per-seed differences, and relative changes are in `metrics/CONTROL_COMPARISONS.csv`.

RF24 joint classification by true mechanism follows. Subset evaluation retains all 12 candidates rather than filtering candidates by the known truth.

{mt}

instance-stop and n4-block both achieve 100% joint Top-1 on these fixed evaluation cases; this does not establish universal separability across runs. n3-block, delay, loss, and n6-block are weaker, with Core24h n3-loss and n6-block joint recognition at 0. Both deep models have 16.67% marginal mechanism accuracy on Core24h, indicating that mechanism discrimination does not transfer stably.

The main RF24 mechanism confusions on D06–D07 are n6-block→n3-delay, n3-delay→n6-block, and each→n3-block. Counts across three seeds are respectively 31, 19, and 19/17. These are repeated predictions of the same cases, not additional physical events. Core24h network mechanisms are often classified as n4-block. Six-class marginal and all 12×12 joint confusion matrices are in `metrics/`.

## 6. Error cases and observations

Examples use fixed seed 17 and the first misclassified case in each true joint class, without selecting the best seed. `reports/ERROR_CASE_OBSERVATIONS.csv` includes examples for all models with means/coverage of the 24 observation columns.

- D06 `b02_p03_n3_delay_silver_core`: truth n3-delay|upf-silver; RF24 predicts n6-block|upf-silver. Window coverage is 100%, both Ready values are 1, Silver tx_dropped_delta averages 0, and Silver RX rate averages approximately 206,940.5 bps. Mechanism confusion occurs without a missing window or obvious Ready-indicated shutdown.
- V4 `r01_p04_n3_delay_gold_core`: truth n3-delay|upf-gold; prediction n6-block|upf-gold. Coverage is 100%, both Ready values are 1, and Silver RX rate averages approximately 1,316,283.1 bps. The Gold-associated path lacks corresponding interface observations; this example cannot determine which missing signals caused the error.
- Core24h `r1_05_n3_delay_silver`: truth n3-delay|upf-silver; prediction n3-block|upf-gold. Both mechanism and associated target are wrong despite 100% coverage and both Ready values being 1. Complete coverage does not imply sufficient information.

These descriptions place errors alongside observations; they are not causal explanations. SHAP, feature importance, or attention is not presented as causal evidence.

## 7. Four compound cases

All four true interventions are n3-delay+n3-loss, outside the 12 classes. Only the top three candidates from RF24 with fixed seed 17 are shown below. All 60 cases from 15 model/seed combinations are in `reports/COMPOSITE_CASES.csv`, with all 12 probabilities retained. No 12-class accuracy or unknown-fault detection metric is computed for these cases.

{ct}

## 8. Execution and verification

Before training, a smoke check used one actual training example per class, totaling 12 cases. LSTM reached 100% training accuracy in 36 steps and TCN in 21; those weights were discarded. These figures establish trainability only, not formal model results. The formal fit count remains 15.

The first LSTM took 3.097 s, ran 39 epochs, and selected epoch 31; PyTorch peak allocated GPU memory was 50,475,008 bytes and peak process RSS was 1,450,688 KiB. Based on that measurement, the remaining 5 deep fits were estimated at 15.48 s; RF duration was then unknown. Actual durations of all 15 fits sum to 20.342 s, excluding data checks, smoke checks, evaluation, and reporting. No GPU-hour claim is inferred from this total. Detailed logs and the tracker retain durations, epochs, and statuses.

{tt}

`audit/FORMAL_START_FREEZE.json` records the formal start freeze after the smoke check; `audit/TEST_FREEZE.json` records the freeze after all models completed and before held-out evaluation. Configuration, training-code, model, and preprocessing hashes matched.

The first evaluation encountered an implementation error when serializing numpy.int64 supported-class labels to JSON. Original frozen code is retained. The corrected `code/pipeline_eval_v2.py` only converts that label list to Python integers. The diff, first-attempt failure log, and partial outputs remain in `audit/EVALUATION_SERIALIZATION_FIX.json` and `audit/evaluation_attempt1/`. Prediction definitions, models, hyperparameters, and seeds did not change; there was no retraining or held-out-score-based configuration selection.

Independent NumPy confusion-matrix/ranking arithmetic recomputed all 1800 metric rows, with maximum difference {v['max_metric_error']:.3g}; replay from 15 saved models covered 9180 case-probability outputs, with maximum difference {v['max_replay_probability_error']:.3g}. Means/sample standard deviations, support, rankings, confusion matrices, checkpoint selection, and 154 source-package hashes all passed. See `audit/RESULT_VERIFICATION.json`. Independent arithmetic checking is not reproduction by an independent external research team.

## 9. Limitations and supported contribution

1. Silver has interface rate/drop/error columns; Gold lacks symmetric interface columns. Observability is asymmetric. Models do not receive unavailable control-plane error counters or logs.
2. W1 user behavior may confound results. Core24h has only 24 closed-set cases and provides a limited Core-only control; its degradation cannot be attributed solely to the model, data, or background.
3. There are only 288 training events under an existing nonblind split. Sliding windows, random seeds, and different models are not new physical collection repetitions.
4. Models know the recorded start and wait a fixed 60 s before diagnosis. This task does not verify automatic onset detection or advance prediction. These scores do not compensate for missed events in the earlier detector.
5. Service damage from every intervention has not been independently established. Natural unknown faults, complete causal chains, open-set rejection, and end-to-end automatic RCA are not verified.

Supported contribution: platform-collected Core observations support joint mechanism/associated-path diagnosis and candidate ranking under the specified controlled interventions. The 24-column observations provide additional discriminative information over the original 10 columns and Ready/missingness control, while mechanism confusion and transfer across roles remain substantial limitations. The evidence extends beyond path localization but does not establish complete, reliable root-cause analysis.

## 10. Artifact entry points

Directory: `evaluation/localization/`.

- `config.json`, `README.md`, `code/`: frozen settings, environment, and rerun instructions.
- `data_contract/sample_index.csv`, `event_disposition_621.csv`: revised labels, four role fields, and complete event disposition.
- `data_contract/feature_whitelists.json`, `coverage.csv`, `fit_sample_ids.json`: input whitelists, coverage, and fitting scope.
- `models/`, `logs/`, `tracker.json`: 15 model sets, training logs, preprocessing parameters, and formal status.
- `predictions/`: 12 probabilities, complete rankings, predictions/truth, and configuration/model identity for 612 cases per set, including 4 compound cases.
- `metrics/ALL_METRICS.csv`, `SUMMARY.csv`, `CONTROL_COMPARISONS.csv`, confusion matrices: all per-seed/per-run/stratified metrics.
- `reports/FULL_TABLES_ZH.md`, `ERROR_CASE_OBSERVATIONS.csv`, `COMPOSITE_CASES.csv`: full numerical results and cases.
- `audit/RESULT_VERIFICATION.json`, freeze receipts, and historical blocker/release records: verification chain.
'''
(R/'reports/FINAL_REPORT_ZH.md').write_text(report)
print('FINAL_REPORT_WRITTEN')
