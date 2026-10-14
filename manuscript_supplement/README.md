# D-GATE Supplementary Appendices

These appendices describe the platform implementation, collection settings, data formats, task construction, and evaluation settings used in the D-GATE study. Detailed AI evaluation materials are linked alongside the corresponding sections. These A–D labels are the supplementary appendices cited by the current English manuscript. The [navigation guide](../APPENDIX_NAVIGATION.md) distinguishes them from the older detailed D.3/E series and the expanded platform-branch appendices.

| Appendix | Contents |
|---|---|
| [A. Platform implementation and configuration](#appendix-a-platform-implementation-and-configuration) | Platform modules, intervention and recovery procedures, deployment, and collection settings |
| [B. Data organization, fields, and examples](#appendix-b-data-organization-fields-and-examples) | Data products, the field dictionary, sample records, and derived metrics |
| [C. Task construction](#appendix-c-task-construction) | Prediction inputs, core-network observations, task windows, and data splits |
| [D. Evaluation settings and results](#appendix-d-evaluation-settings-and-results) | Model configurations, hyperparameters, random seeds, and result files |

Prepared AI task inputs and 1 s platform exports are included in this branch; [data access](../DATA_ACCESS.md) links the observations, indices, windows, masks, and preprocessing scales. PCAP files and the complete original log collection are not included. See [the repository overview](../README.md) for the platform appendices and source code maintained in a separate branch.

## Appendix A. Platform implementation and configuration

### A.1 Platform modules

| Module in Fig. 1 | Implementation | Inputs and outputs |
|---|---|---|
| ① Traffic generation | Executes TCP/UDP traffic from protocol, relative timing, direction, and data-volume records; binds the client to the UE TUN interface | Traffic records → actual transfer times, data volumes, and completion, timeout, or failure outcomes |
| ② Experiment control | Prepares the network and traffic; controls UE count changes, UE recreation, gNB restarts, core-network faults, collection, and recovery checks | Configuration and operation plan → actual command start/end times, execution results, and recovery results |
| ③ Multi-source collection | Collects packets, logs, management/container queries, and OS observations, retaining source, time, instance, and collection status | PCAP, text logs, and JSON/JSONL records |
| ④ Data retrieval and archiving | Retrieves files across hosts and checks their completeness and contents before marking retrieval complete | Run-organized files and retrieval results |
| ⑤ Data processing | Associates sessions, aligns and aggregates observations, and checks completeness and field coverage | CSV time series, JSONL association records, and experiment reports |

The table below separates upstream software from platform integration, adaptations, and added programs. Implementation paths refer to the platform source snapshot, which is maintained in the separate platform appendix branch.

| Component | Role | Implementation or output |
|---|---|---|
| Upstream protocol implementations | free5GC network functions and UERANSIM access simulation | Registration, authentication, session management, and access simulation |
| Deployment integration | Two DNN groups, SMF/UPF paths, containers, virtual machines, and instance mappings | Deployment and run configurations; settings summarized in [A.4](#a4-deployment-traffic-and-collection-settings) |
| Traffic tools | Record-driven TCP/UDP traffic, UE TUN binding, and outcome recording | `tools/ue_tracer/trace_play_scenario_v11.py`, `scripts/continuous_traffic_runner.py`; client/server records |
| Experiment control and recovery | Access operations, core-network fault timelines, recovery decisions, and failure handling | `scripts/scenario_timeline_runner.sh`, `scripts/online_recovery_checkpoint.py`; operation and recovery records |
| Multi-source collection | Control-plane events, resources, instance state, and host/interface observations | `scripts/control_plane_collector.py`, `nf_state_collector.py`, `host_metrics_collector.py`, `ran_k3s_workload_collector.py` |
| Data retrieval | Cross-host file retrieval, completeness checks, and run reports | `scripts/traffic_transfer_bundle.py`, `scripts/audit_scenario_one_run.py` |
| Association and export | Session mapping, metric export, and field/quality checks | `scripts/export_session_map.py`, `scripts/export_v3_timeseries.py`, `scripts/dataset_schema.py` |

The platform extends SMF session logs to record user, session, address, and tunnel mappings. Network-function changes include local cleanup after failed release of an old session without removing an index that already points to a new session; SMF PFCP response matching and session error handling in the UPF; AMF registration-state updates; NRF slice-identifier matching; and PCF numeric-type compatibility. These changes support continued operation and record association during interventions.

Control-plane log collectors retain their read positions, parse appended content, and reset when a file is replaced or truncated. Resource records retain instance identifiers and collection status so that zero values can be distinguished from unavailable observations.

### A.2 Interventions and recovery

The access-side operations are UE count changes, UE recreation, and gNB restarts. The six core-network fault types are N3 blocking, added N3 delay, random N3 packet loss, N4 blocking, N6 blocking, and stopping a UPF instance. Planned operations and actual execution records are stored separately.

Recovery removes the injected rules or restores the affected instance, waits for concurrent access-side operations to finish, and checks NF readiness, residual rules, gNB/UE counts, PDU connectivity, and traffic outcomes. Collection continues throughout intervention, recovery, and observation. A failed recovery check prevents subsequent faults from starting; it does not immediately stop all collection.

The [archived recovery implementation](source_notes/recovery_constants.txt) uses two 60 s traffic windows, a minimum of 15 samples, a completion-rate threshold of 0.95, failure- and timeout-rate thresholds of 0.05 each, and a 120 s stability observation. These values describe the implementation; run-specific settings are recorded separately. `WINDOW_SECS`, `WINDOW_COUNT`, and `GUARD_SECS` are constants, separate from the configurable phase durations.

### A.3 Completion and interruption

| Mechanism | Parameter or mode | Behavior |
|---|---|---|
| Phase duration | `--baseline-secs`, `--fault-secs`, `--recovery-secs` | Ends the configured phases, then stops collection and retrieves files according to the execution schedule |
| Fault-plan completion | `--fault-plan FILE` | Proceeds to recovery observation and finalization after the timeline finishes |
| Disk protection | `--min-free-gb` | Interrupts the main workflow and triggers cleanup when the local packet-capture watchdog fails its free-space check |
| Recovery-check failure | Recovery checkpoint in `combined-only` mode | Stops subsequent faults while the main workflow continues recovery, retrieval, and reporting |
| Manual interruption | Ctrl+C / SIGTERM | Records the cause and attempts cleanup and file retrieval |
| Other stop criteria | No common entry-point option | Performance thresholds, sample count, total data volume, and a specified clock time are not general stop settings in this implementation |

In Fig. 1, *Collection settings*, *Collection control*, and *Recovery checks* refer to collection configuration, execution control, and recovery assessment, respectively.

### A.4 Deployment, traffic, and collection settings

An experiment combines network configuration, traffic configuration, an operation plan, and collection settings. Network configuration specifies component counts and locations, interface addresses, gNB/UE group mappings, DNNs, slice identifiers, and address pools. After UE registration and PDU-session establishment create the TUN interface, the traffic client binds to that interface and communicates with the DN application server. Changing UE or NF scale also requires corresponding address, instance-mapping, and run-check settings.

The collection deployment uses three physical hosts and an Ethernet switch. free5GC v4.1.0 NF containers run in a K3s cluster spanning the 5GC host and its virtual machine. Two groups of AMF, SMF, and UPF instances are distributed between the host and virtual machine; the remaining NFs and MongoDB run on the host. UERANSIM v3.2.7 gNB/UE instances and the DN traffic server occupy the other two physical hosts. Each DNN group initially contains two gNBs and 20 UEs, with sessions managed by its SMF and traffic forwarded through its UPF. The groups share the DN server.

| Setting | Value |
|---|---|
| 5GC host | 8 threads; 62.45 GiB K3s-allocatable memory |
| 5GC virtual machine | 2 vCPUs; 5.79 GiB K3s-allocatable memory; runs on the 5GC host |
| UE/gNB host | 32 threads; 128 GiB memory |
| DN traffic server | 20 threads; 64 GiB memory |
| gNBs / initial UEs / DNNs | 4 / 40 / 2 |
| NF types / instances | 9 / 12, excluding MongoDB |
| Transport protocols / traffic UEs | TCP and UDP / one selected UE per DNN |
| Target-group UE count | 20 → 10 → 20 |
| Core-network interventions | N3 blocking, added N3 delay, random N3 loss, N4 blocking, N6 blocking, and UPF stop |
| Added N3 delay / random loss | 200 ms / 10% |
| First planned start / start interval | 1,800 s after the operation-plan origin / 900 s |
| Core-network intervention duration | 120 or 180 s |
| Access-side interventions | gNB restart, UE recreation, and target-group UE count change |
| Configured control-plane statistics period | 2 s |
| Configured host/interface, NF resource/state, and gNB/UE state period | 5 s |

Traffic inputs include normal single-UE records from 5GAD, cited in the paper, and online-game, office, and video traffic records. Each input specifies protocol, relative send/receive timing, direction, and data volume; traffic configuration also specifies start time and duration. Actual transfers traverse the UE client, gNB, N3, UPF, N6, and DN server. Client and server logs record actual times, data volumes, and completion, timeout, or failure outcomes.

Configuration specifies each operation's target, parameters, planned start, and duration; actual execution and recovery outcomes are stored separately. Each run includes 72 core-network faults, with subsequent faults following completion of related operations and successful recovery checks. Packet, log, and periodic-query collection spans traffic, intervention, and recovery. Actual sampling times are recorded because query duration can affect timing. The 2 s/5 s collection periods, 1 s exported table interval, and 5 s task-observation interval describe different stages of data organization.

### A.5 Session association and outputs

Session association groups extended SMF records within a run by SUPI and PDU-session identifier, merges them within a bounded time window, and uses UE addresses, UPFs, and tunnel information to associate network and traffic observations. When direct records are unavailable, packet addresses and deployment configuration provide fallback associations with source markers retained.

PCAP, log, and JSON/JSONL files are retrieved into run-specific directories. Retrieval checks compare source and destination file lists and contents and record failures. Processing then aggregates observations into statistical windows and aligns fault execution, UE count changes, and recovery checks by time, retaining the original records and timestamps. Outputs include time series, association records, and reports covering configuration, operations, recovery, completeness, field coverage, and timing quality.

## Appendix B. Data organization, fields, and examples

### B.1 Data products

| Product | Format | Contents and association information |
|---|---|---|
| Packet captures | PCAP | Interface packets and capture times; associated through source, address, session, and tunnel information |
| NF and access-side logs | Text, JSON/JSONL | Registration, sessions, instances, and control-plane events |
| State, resource, and traffic records | JSON/JSONL and other raw records | Source, actual time, instance/host/interface, and transfer outcomes |
| Operation and recovery records | Structured records within each run | Targets, parameters, planned/actual times, and execution/recovery outcomes |
| Association records | JSONL | User, PDU-session, address, UPF, and tunnel mappings with source markers |
| Derived time series | CSV | Windowed metrics, identifiers, state, and validity information |
| Experiment reports | Reports and check records | Configuration, operations, recovery, completeness, field coverage, and timing quality |

These product categories do not share a single JSON schema. Field names, units, types, source artifacts, and availability are described in the [field dictionary](data/field_dictionary.csv).

### B.2 Field definitions and table dimensions

The dictionary contains **400 definitions: 215 metrics and 185 configuration, state, identifier, label, quality, or other fields**. It contains 400 `canonical_id` values and 379 distinct `field_name` values across raw and derived products; it is not the schema of a single 400-column table.

The seven 1 s exported tables each contain **81 columns**, totaling **611,777 rows**. Matching these columns to the dictionary yields 39 fields with the `metric` role. Availability also depends on states such as `ok`, `snapshot_only`, `replaced`, and `capability_missing`; the role count does not imply that all 39 metrics are usable in every record.

The 5 s core-network observations contain **24 variables**. Their timestamps can be aligned with the 1 s tables, but some same-named fields have different values at the same time. The 5 s observations therefore are not a direct downsampling of the 81-column tables. The **18-variable prediction input** is also constructed separately from the raw records, as described in [C.1](#c1-prediction-inputs). See the [dataset guide](source_notes/DATASET_GUIDE.md) and [schema comparison](data/schema_verification.json) for details.

### B.3 Examples and dictionary

| File | Contents |
|---|---|
| [Field dictionary](data/field_dictionary.csv) | All 400 definitions, including `field_name`, `field_role`, `entity`, `unit`, `value_type`, `source_artifact`, `availability`, and `caveat` |
| [1 s time-series sample](data/timeseries_1s_sample.csv) | Header and first 20 rows of the D06 81-column table, with 1 s spacing and recorded missing values |
| [5 s core-network sample](data/core_features_5s_sample.csv) | First 10 rows of the D06 core-network observations |

Missing or unavailable observations should not be replaced with zero. User/session associations use run scope and time windows, with source markers retained. These small examples illustrate fields, timing, and missing-value representation. The [1 s exports](../data_machine/dataset/timeseries_1s/), [5 s task observations](../data_machine/dataset/task_data/data/), and [prediction inputs](../prediction_inputs/README.md) are available separately.

### B.4 Observation sources and derived metrics

| Category | Source | Entities and representative observations |
|---|---|---|
| Network traffic | N3/N4/N6 and SBI packets | Flows or interfaces; packets, bytes, uplink/downlink bitrates, and flow duration |
| Signaling and sessions | AMF/SMF logs, management interfaces, and protocol packets | UE/PDU sessions and SMF/UPF mappings; registration, session establishment, and active-session statistics |
| NF resources and state | Container management interfaces | AMF, SMF, UPF, NRF, NSSF, UDM, UDR, AUSF, PCF, and MongoDB; CPU, memory, readiness, and restarts |
| Hosts and interfaces | OS interfaces | CPU, memory, system load, and cumulative interface send/receive counters |
| gNB and UE state | UERANSIM logs and state queries | Readiness counts, registration state, and session state |
| Application transfers | UE clients and DN servers | Actual transfer times, data volumes, and completion, timeout, or failure outcomes |

Derived rates use the following definitions:

1. **Interface send/receive rate:** the increment in cumulative bytes divided by the actual interval between samples, in byte/s; multiply by eight for bit/s. Configured sampling periods do not replace actual elapsed time.
2. **Registration and PDU-session establishment success rates:** successful operations divided by corresponding requests, using the same entities and statistical windows for numerator and denominator.
3. **Traffic completion rate:** successful transfers divided by all terminated transfers in the window; terminated timeouts count as failures.

Operation times and recovery outcomes accompany the observations. Unavailable sources, unsupported interfaces, and invalid observations retain their missing-value or status indicators rather than becoming zero-valued rates.

## Appendix C. Task construction

### C.1 Prediction inputs

The 81-column platform tables and prediction inputs use raw records from the same runs but serve different purposes. Prediction histories and targets are constructed separately as `T1_history` and `T1_targets` products.

For anchor time `c`, the history is `[c−60,c)` and the target is the mean of valid values in `[c+60,c+70)`. Targets are N3 downlink bitrate, N6 aggregate bitrate from flow records, and host CPU utilization. The N6 target is not a directly measured per-second receiver throughput. SMA uses the final 10 s; PatchTST uses target history; XGBoost uses 18 variables and their validity indicators.

### C.2 Core-network observations

The 24 variables comprise 12 CPU/memory measurements from six AMF, SMF, and UPF instances; four host-resource measurements; six interface statistics; and readiness indicators for two UPFs. Exact column lists are provided in the `features` field of the [imputation configuration](configs/imputation.json) and the `feature_columns` field of the [detection configuration](configs/detection_AE_seed43.json).

### C.3 Windows, splits, and evaluation scope

| Task | Construction and evaluation |
|---|---|
| Prediction | 60 s history, 60 s gap, and a 10 s target mean; preprocessing parameters estimated from training data |
| Fault detection | Continuous-run evaluation; AE/TranAD use 12-step sequences; KAN-AD takes adjacent differences to obtain 11 time points; RF uses window statistics. Merged alarms are matched one-to-one with events |
| Fault classification and associated-target identification | 12 observations during the 60 s after a known injection start; six fault types × two target UPFs = 12 classes; 288/72/144 training/validation/test samples |
| Metric imputation | 300 s windows with 60 positions; random 20% masking or continuous 30/60/120 s gaps; observations before and after a gap are available, and only originally valid, artificially masked values are scored |

D01–D04 form the training set, D05 the validation set, and D06–D07 the test set. D06/D07 had previously been accessed, so the reported analysis is post hoc under a fixed split. Classification assumes known injection starts; it does not evaluate alarm-triggered online localization. Imputation evaluates artificial missingness in offline windows.

See [detailed task construction](../appendix/D3_data_construction.md) for field lists, preprocessing, sample selection, and evaluation rules.

## Appendix D. Evaluation settings and results

### D.1 Configuration files

| File | Purpose |
|---|---|
| [Prediction selection](configs/prediction_selection.json) | Selected configurations from the completed candidate comparison |
| [Prediction design specification](configs/prediction_design_spec.yaml) | Design settings; execution and selection details are provided separately |
| [AE detection](configs/detection_AE_seed43.json), [KAN-AD detection](configs/detection_KAN_AD_seed43.json), [TranAD detection](configs/detection_TranAD_adapted_v2_seed43.json), [RF detection](configs/detection_RF_seed17.json) | Task-specific training configurations |
| [Classification](configs/classification.json) | Classification inputs and model settings |
| [Imputation](configs/imputation.json) | Imputation variables, masking, and model settings |
| [Task protocol](configs/task_protocol.json) | Shared task and evaluation settings |

### D.2 Main hyperparameters

| Model/task | Configuration |
|---|---|
| PatchTST prediction | `d_model=64`, `heads=4`, `layers=2`, `d_ff=128`, `patch_len=12`, `stride=6`, `dropout=0.1`; selected learning rates below |
| XGBoost prediction | `n_estimators=500`, `learning_rate=0.04`, `min_child_weight=3`, `subsample=0.9`, `colsample_bytree=0.9`; selected depths below |
| Detection models fitted on normal data | Maximum 50 epochs, `patience=8`, effective batch size 128; optimizer and learning rate in the linked configurations |
| Adapted KAN-AD | Adam, `lr=0.003`, `StepLR(5, 0.75)`; per-variable differenced prediction-error scores |
| Adapted TranAD | AdamW, `lr=0.001`, `weight_decay=0.0001`; mean two-stage reconstruction-error scores |
| Supervised RF detection | 160 trees, `max_depth=12`, `min_samples_leaf=20`, `class_weight=balanced_subsample`, `max_features=sqrt`; seed-17 configuration linked above |
| LSTM/TCN classification | `width=64`, `dropout=0.1`; two LSTM layers; two TCN blocks with `dilations=[1,2]` and `kernel=3`; batch size 32, AdamW, `lr=0.001`, maximum 50 epochs, `patience=8` |
| RF classification | 500 trees, `min_samples_leaf=2`, `max_features=sqrt`, `max_depth=None` |
| SAITS-H/M imputation | `d_model=64`, `d_ffn=128`, `heads=4`, `d_k=d_v=16`, two layers per DMSA block, `dropout=0.1`, batch size 64, AdamW, `lr=0.001`, `weight_decay=0.0001`, maximum 50 epochs, `patience=8` |

Selected prediction settings use the architectures listed above:

| Target | PatchTST learning rate | XGBoost maximum depth |
|---|---|---|
| `host_cpu` | 0.0003 | 6 |
| `n3_downlink` | 0.0003 | 6 |
| `n6_aggregate` | 0.0003 | 6 |

Prediction uses seeds **42/43/44**; detection, classification, and imputation use **17/29/43**. Imputation mask seeds are **101/202/303**.

Detection thresholds are selected on labeled validation data at false-alarm budgets of 0.1/h and 1/h, then fixed for testing. Both event recall and actual false-alarm rates are reported. SAITS-H/M share architecture, parameter count, training budget, and masking arrangements; each selects its model using validation error.

Full model adaptations, training and selection rules, and environment details are in [model hyperparameters](../appendix/E1_models_hyperparameters.md).

### D.3 Results and reproduction

| Resource | Contents |
|---|---|
| [Paper result map](../PAPER_RESULT_MAP.md) | Links between reported results and result files |
| [Detailed result correspondence](../appendix/E2_results_correspondence.md) | Tables, figures, and supplementary comparisons |
| [Reproduction guide](../appendix/E3_reproduction.md) | Saved-result calculations, inference replay, and training instructions |
| [Data access](../DATA_ACCESS.md) | Available inputs and data required for each reproduction step |

The repository includes saved models, evaluation results, and the prepared inputs described in the reproduction guide. Inference and training also require the specified runtime dependencies; this data update does not report new model runs. The small samples in this directory remain available for quickly inspecting the formats.
