# Appendix B. Configuration and execution control

## B.1 Configuration carriers and actual settings

| Carrier | Scope and actual saved setting | Where applied / evidence |
| --- | --- | --- |
| Network/deployment | Core K8s multi-worker, access K3s; four gNBs / forty initial UEs; dual DNN, SMF and UPF mapping; host networking for AMF/UPF | `samples/W1-D06/config/runtime/k8s-topology.json`, run manifest and selected `platform/source/config/` |
| Traffic scenario | `scenario_vali1.json`; main normal single-UE records, gaming auxiliary directory, office/video random pool; TCP and UDP | Saved `traffic/config/scenario_vali1.json`; actual selected files require source/segment evidence |
| Traffic controls | Random seed 20260713; auxiliary start offset 15 s; gaming pause at 10 s for 10 s, skip at 700 s for 100 s; random pool 80 files, office/video proportions 20%/80%; server acceptors/workers/admission 4/6144/12288 | These are configuration values, not realized traffic rates or delivered content. The scenario's historical `attack` tag for office/video does not make those transfers a Core fault label. |
| Operation plan | Continuous workload 86,400 s; first planned Core operation 1,800 s, subsequent starts 900 s apart; 72 Core operations paired with 72 access operations | `samples/W1-D06/config/runtime/fault-plan.json`; actual execution times may differ |
| Collection | Control-plane polling 2 s; host/interface and supported NF/access state polling 5 s | `platform/source/scripts/core_collectors.sh` passes a literal 2 s to control-plane collection; queries retain actual timestamps and may take longer than the configured period |
| Capture | Rotation 300 s or 512 MiB; snap length 256 bytes | Saved `run_manifest.json.capture_rotation`; retained packets may be truncated, so full application payload reconstruction is not promised |
| Bandwidth | `unlimited`, `metadata_only`, application not requested | Run manifest; this does not establish measured path capacity or actual shaping |
| Recovery | Two 60 s business windows, at least 15 terminal samples per window/tier; completion >=0.95, failure <=0.05, timeout <=0.05; 120 s clean guard | Source constants plus actual `recovery_checkpoints.jsonl`; distinct from base-table completion-window rules |

Parameters are [tabulated with plan values and actual evidence](../tables/CONFIGURATION.csv). Complete sample plans retain all seventy-two paired groups; the [nine operation families](../tables/OPERATIONS.csv) and [execution rows](../tables/ACTUAL_OPERATIONS.csv) provide machine-readable start/end details.

## B.2 Traffic records and two-ended use

| Figure field | Executable representation | Meaning | Client / server use |
| --- | --- | --- | --- |
| Protocol | `flow.protocol` | Transport protocol; UDP if the normalized value is `udp`, otherwise TCP path | Client selects datagram/stream socket; server uses protocol-specific handling |
| Relative time | `flow.start_time`, `actions[].delay`, scenario `start_offset` | Flow start relative to the trace's first start and per-action delay in seconds relative to that flow's replay start | Client schedules `start + delay`, including pause/skip/cut adjustments. TCP server schedules from its own accepted flow start; the two origins are not a guarantee of synchronized absolute time. |
| Direction | `actions[].dir`, `send` or `recv` | Direction from the UE client viewpoint | `send`: client sends / TCP server receives. `recv`: client receives / TCP server sends. |
| Data size | `actions[].size` | Requested action payload bytes | Sender constructs `b'x' * size`; TCP receiver reads until requested bytes or termination. It is not original payload content, total wire length or a guaranteed packet count. |

The TCP client sends a replay-ID header so the server can locate the flow's action list. Each end logs its actual behavior. Trace time and configured direction are plans; actual socket/terminal statistics are observations. Padding still produces real packets through UE-TUN/gNB/N3/UPF/N6/DN. The frozen UDP server primarily receives/discards datagrams; the TCP two-ended schedule must not be generalized into complete bidirectional UDP application replay. The input trace corpus is not republished here without its source rights and provenance.

Scenario inheritance is item > role > kind > defaults. Source types are `file`, `dir` and `random_pool`. Controls are `pause`, `skip` and `cut`; a main-task cut/end can set the global stop event. Runtime segments may restart after disruptive operations, and their identity must remain separate from the original trace identity.

## B.3 Three access-side and six Core-side operation families

The [operation table](../tables/OPERATIONS.csv) supplies target, parameters, actual plan values, implementation and undo. Access families are UE-count adjustment, UE re-creation and gNB restart. A gNB restart is a workload lifecycle operation; it is not inferred from a transient missing log line. UE-count adjustment is 20 -> 10 -> 20 in the target group. Re-creation can reduce the group/workload to zero and restore twenty; gNB restart uses zero then one replica for a targeted gNB. Saved access parameters include a 180 s readiness wait, a 300 s command timeout, `one_shot=true` and explicit restore values.

The six Core families are N3 block, N3 delay (200 ms), N3 random loss (10%), N4 block, N6 block and UPF stop. N3/N4 blocking uses targeted UDP rules (2152/8805) and exact-rule removal; N6 blocking uses the target UPF GTP interface and DN peer in FORWARD. Netem uses the route-resolved device, UDP 2152 matching and a netem child queue; undo removes the configured qdisc. UPF stop in the saved K8s path scales the chosen deployment to zero and restores the saved replica count. No such commands were executed during this preparation.

Core durations are label/tier dependent: N3/N4 block are 120 s on both tiers; N3 delay is gold 120 s / silver 180 s; N3 loss is silver 120 s / gold 180 s; N6 block is silver 180 s / gold 120 s; UPF stop is gold 180 s / silver 120 s in the saved plan. Each family has twelve operations per run (six per tier), whereas the source `netem` command type covers both delay and loss. Thus there are six scientific Core labels even though implementation command types are fewer. Each access family has twenty-four paired actions per run. The planned file includes 144 startable entries; the execution report includes 288 start/end command results. These are not 288 separate Core faults.

A sample first group is `b01_p01_n3_block_silver`: N3 block and silver UE down-scaling share `overlap_group`. The execution report records Core start/finish and access start/finish separately, with return codes and scheduling lateness. Undo timestamps and accepted checkpoints are distinct evidence. Access behavior must not be labeled as a Core failure.

## B.4 Recovery, later interventions and abnormal finalization

After operation durations expire, the executor undoes the Core rule/stopped deployment and completes/restores the paired access action. Recovery checks cover group contract, Core readiness, residual fault rules on both workers, exactly four ready gNBs and forty ready UEs, required session rebuilding, a tier PDU probe and post-readiness terminal traffic cohorts. Business windows use half-open intervals and avoid counting arbitrary pre-readiness flows as recovered transfers. The source records its anchor strategy and window boundaries in each result. Both tiers and both windows must satisfy the thresholds; this is a statistical criterion, not a claim of zero disruption.

A 120 s stable observation guard follows. Only accepted recovery admits a later operation. Failure, timeout or insufficient evidence stops later interventions, records the reason and attempts to undo remaining active operations. A restore command with return code zero is not itself proof of recovery. `recovery_checkpoints.jsonl` contains checks and acceptance, while `recovery_actions.jsonl` records assisted recovery actions.

Collection continues through baseline, intervention, undo, checks and continued observation. Normal stopping follows completion of the plan/workload and final recovery checks, then traffic/capture/collector stop, closed-file transfer verification, offline processing and reporting. Runtime interruption, failed mandatory checks, timeout, resource/health failure and external termination can instead enter abnormal finalization. The shell traps and health/interruption scripts preserve failure status and cleanup evidence. This appendix describes existing logic; the package validation never launches the experiment.

The sample final status is historical `completed`. This does not describe any currently running platform. No network, process scale, fault injection, recovery command or new collection was started during the appendix work.
