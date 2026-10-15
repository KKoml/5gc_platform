# Appendix D.3 — Data construction for the four tasks

This technical appendix was compiled against the historical Chinese platform revision from configurations, task indices, training records, and saved results. Its manuscript and figure hashes are recorded in `manifests/paper_baseline.json`. For the current English paper and Appendices A–D, see [the navigation guide](../APPENDIX_NAVIGATION.md). Numerical agreement, checkpoint replay of saved outputs, and the identity of the historical paper run are separate evidence questions; the first two do not establish the third.

D01–D04 are training runs; D05 is used for validation and model/threshold selection; D06–D07 are previously accessed, post hoc test runs. These identifiers denote seven independent executions, not seven consecutive days. Windows never cross runs. Model and artificial-mask seeds represent algorithmic variation, not independent platform repetitions. `validation_v4r6`, `supp_core24h`, and `diagnostic5` are reported separately; `development_excluded` is excluded from the main paper test. The 5 s task named T1 in the legacy `task_data/provenance/SOURCE_PROTOCOL.json` is not the forecasting task in this paper.

## D.3.1 — Network performance forecasting

Inputs are `T1_history.csv.gz` and `T1_targets.csv.gz` under `prediction_inputs/D01` through `D07/`, with target/run-specific frozen Parquet indices under `evaluation_package/evaluation/prediction/outputs/indices/`. At cutoff c, history covers [c−60,c), with 60 one-second positions and a 60 s window stride. After the gap [c,c+60), the target is the mean of valid target values in [c+60,c+70). At least eight of the ten target buckets must be valid. Target tables retain candidate eligibility and counts; frozen indices determine the samples actually used. Future target validity determines evaluation eligibility only and is not an input.

The exact order of the 18 variables is:

```text
n3_uplink_bitrate_bps, n3_downlink_bitrate_bps, n6_bitrate_bps,
cp_pdu_session_success_rate, cp_pdu_session_failure_count,
end_to_end_rtt_ms, jitter_ms, packet_loss_rate,
cp_active_session_count, cp_pending_session_count,
cp_pdu_session_request_count, registration_success_rate,
registration_failure_count, registration_request_count,
n4_bitrate_bps, host_cpu_pct, host_mem_used_pct, host_loadavg_1
```

Each variable has a `<field>__missing` indicator equal to 1 for nonfinite values. `prediction/src/data.py:transform` imputes training-channel medians and standardizes with training means/standard deviations, producing an N×60×36 tensor of values and missingness indicators. PatchTST uses only N×60×1 target history. XGBoost computes the mean, population standard deviation, minimum, maximum, last value, and (last−first)/59 for each of 36 channels, giving 216 features. SMA averages valid target values in the final ten history positions. Target scaling is fitted to observed training targets. Predictions are restored to original units; bitrate evaluation divides by 10^6.

The three paper targets are `n3_downlink_bitrate_bps`, `n6_bitrate_bps`, and `host_cpu_pct`. Full results also retain `end_to_end_rtt_ms`, a source-defined flow RTT proxy, not a verified UE-to-DN end-to-end RTT measurement. N6 is a flow-record aggregate, not verified per-second received throughput. Native sampling intervals, hold rules, and online availability remain unknown for some sources. These inputs come from the later four-field prefix-repaired view; cutoff checks alone do not establish strictly causal online availability of every original measurement.

Input controls use target history plus missingness indicators, the time schedule, or missingness indicators alone. The time schedule consists of row position/86400 and sine/cosine terms with 600 and 900 s periods. Controls reuse the main XGBoost hyperparameters selected on D05. The strong N6 time-schedule control, close to the multivariate model, is retained. `verification/replay_prediction_checkpoints.py` checks ordering, time, and missingness indicators; CSV label round trips allow 2e−8 absolute error in original units plus 2e−15 relative error. Forecast histories were not regenerated from the 81-field tables in this package.

## D.3.2 — Fault detection

Observations are `data_machine/dataset/task_data/data/<run>/core_features_5s.parquet`; `tasks/FD_detection/index.parquet` binds samples, while episodes, EVENT_EVALUABILITY, and `metadata/protocol.json` constrain events and eligibility. Each sample spans the zero-based row interval [start_row,stop_row), containing 12 five-second cutoffs; the last cutoff is the scoring anchor. `eligible` includes time/range checks and an overall valid-observation fraction of at least 0.8. Original tables retain NaN; finite values define validity indicators. The legacy `is_valid_row` is not a universal eligibility rule.

Detection, post-intervention classification, and imputation use these 24 variables:

```text
amf-a__cpu_millicores, amf-b__cpu_millicores,
smf-silver__cpu_millicores, smf-gold__cpu_millicores,
upf-silver__cpu_millicores, upf-gold__cpu_millicores,
amf-a__memory_bytes, amf-b__memory_bytes,
smf-silver__memory_bytes, smf-gold__memory_bytes,
upf-silver__memory_bytes, upf-gold__memory_bytes,
core-host-local__cpu_pct, core-host-local__mem_used_pct,
core-host-local__loadavg_1, core-host-local__swap_used_bytes,
core-if-upfgtp-silver__rx_bitrate_bps,
core-if-upfgtp-silver__tx_bitrate_bps,
core-if-upfgtp-silver__rx_packet_rate_pps,
core-if-upfgtp-silver__tx_packet_rate_pps,
core-if-upfgtp-silver__tx_dropped_delta,
core-if-upfgtp-silver__tx_errors_delta,
upf-silver__ready, upf-gold__ready
```

Normal-only models use exactly 55,196 D01–D04 windows satisfying `eligible ∧ split=train ∧ normal_train_window`. Entire histories exclude recorded activity, recovery exclusion periods, and preparatory operations. Preprocessing uses medians and median/IQR scaling from this same subset; a zero IQR falls back to the training standard deviation, then 1. Observed Ready values remain 0/1; imputed missing Ready values retain validity 0. AE/TranAD use values and validity indicators; KAN-AD uses validity in loss and scoring. Only valid numerical channels contribute reconstruction error; indicators do not contribute to that error term.

Supervised RF uses all eligible training windows and injection-positive labels, reusing training preprocessing. For each variable it computes the last value, mean, standard deviation, last−first, final-three mean−first-three mean, valid fraction, and final-point validity: 168 features. It fits 66,069 training windows (7,705 positive). This is post hoc optimization under different supervision, not an equivalent normal-only alternative. Labels denote recorded interventions, not independently certified service-impact ground truth. Run identifiers, timestamps, operations, labels, and schedule metadata are excluded from model inputs.

D05 calibrates thresholds at 0.1 or 1 false alarms/h. Consecutive valid above-threshold points form alarm segments; invalid, negative, or missing points break segments, as do gaps exceeding 7.5 s. A segment starts at its first valid positive cutoff and is matched one-to-one in deterministic order within [event start,event end). Normal exposure counts 5 s per eligible, scored normal point; invalid points do not enter the denominator. There is no point adjustment or test-score normalization. A validation budget does not guarantee the same test false-alarm rate. Low recall, misses, and no-alarm operating points are retained.

## D.3.3 — Fault type and associated-target classification at known injection starts

`tasks/FL_localization/index.parquet` binds events to the observations above. `localization/data_contract/` records feature whitelists, class order, sample indices, window boundaries, event handling, and coverage. Given the recorded start s, each sample contains 12 five-second cutoffs in (s,s+60 s], with a valid-observation fraction of at least 0.5. This task does not detect s. Main train/validation/test counts are 288/72/144, with 24/6/12 examples per joint class. Four compound delay+loss events remain outside closed-set metrics. `supp_core24h` is supplementary and cannot be used for training.

Six mechanisms—n3-block, n3-delay, n3-loss, n4-block, n6-block, and instance-stop—cross with upf-silver/upf-gold to form 12 classes, ordered in the configuration. Joint prediction takes the maximum of twelve probabilities. Type and associated-target predictions marginalize over the other dimension before taking the maximum; ties follow the fixed class order. The associated target denotes the injected UPF or associated path, not an independently established causal root cause.

Preprocessing is fitted only to the 3,456 time positions in 288 training examples: valid-value medians, median/IQR scaling, and standard-deviation→1 fallback. Ready has center 0 and scale 1; finite-value masks are retained. LSTM/TCN inputs are N×12×48. RF_24 computes mean, standard deviation, minimum, maximum, last value, last−first, and valid fraction, giving 168 features. RF_FL10 uses the ten SMF/UPF CPU, memory, and readiness variables in `feature_whitelists.json`, giving 70 features. ReadyMaskRF uses statistics of the two Ready variables, the full mask, and mask means, giving 324 features. Controls share the same examples and configurations. Legacy FL10/FL6 plans do not replace the actual 24-variable joint-classification task.

## D.3.4 — Offline missing-value reconstruction

`imputation/data/<slot>.npz` stores raw, original_valid, time, phase, and delta; `metadata/window_index.csv` binds windows to the 5 s task tables. Continuous five-second segments are identified first, then divided into 60-position (300 s) windows with a 12-position training stride and a 60-position evaluation stride. Time gaps restart segmentation; incomplete tails are discarded. Means, standard deviations, medians, and variation-stratification thresholds are computed from D01–D04 only. Among the 24 variables above, target indices 16, 17, and 12 denote RX, TX, and CPU.

Fixed artificial masks in `masks/<slot>.npz` have shape N×3 targets×4 conditions×3 mask seeds×60. Random20 selects 12 positions without replacement. gap30/60/120 hide 6/12/24 consecutive positions, leaving at least 6 positions on each side. Interface targets simultaneously hide channels 16–21; CPU hides channels 12–15, reducing direct within-group leakage. Originally missing values remain invisible; scoring includes only artificially hidden, originally finite target values. H hides all nontarget variables while retaining the 24-channel structure; M retains other valid observations. Missing positions receive training means, becoming zero after standardization, with validity indicators passed separately.

Each training window queries one uniformly sampled target/condition per epoch. M/H share window order and masking plans. Model seeds are 17/29/43; fixed evaluation-mask seeds are 101/202/303. Training-median filling, forward filling (leading gaps fall back to training medians), and bidirectional within-window linear interpolation use the same targets/masks. Raw predictions are saved; reported predictions for all methods are clipped below at zero. Other runs are evaluated only after checkpoint selection on D05. Recovery phase labels proxy recorded exclusion periods, not certified physical recovery. Observations on both sides of a gap are available, so this is offline reconstruction under artificial missingness. M slightly underperforms H for RX random missingness in both main test runs; this negative result is retained.

## D.3.5 — Core handoff and unresolved lineage

`manifests/input_manifest.csv` lists actual relative paths, SHA-256 hashes, row counts or array shapes, fields/types, time ranges, run aliases, processing programs, and program hashes. `core_handoff.csv` separates pre/post-transformation hashes and records compression, format conversion, identifier anonymization, or path-metadata removal. Different formats need not share a hash. [LINEAGE.md](LINEAGE.md) records source checks and remaining gaps. Current 1 s exports, repaired forecast histories, and 24-variable 5 s tables are separately versioned views. Matching slots and timestamps are not evidence of a transformation chain.
