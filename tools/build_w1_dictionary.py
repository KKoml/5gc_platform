#!/usr/bin/env python3
"""Build the W1-only dictionary from frozen public rows and audited evidence.

This is an offline documentation-maintenance tool. It neither collects data nor
imports platform implementation code. It never modifies the original W1 runs.
Counts refer to field definitions, not independent numeric measurements.
"""

import argparse
import csv
import io
import json
from collections import Counter
from pathlib import Path


LEGACY_COLUMNS = [
    "schema_version", "canonical_id", "field_name", "domain", "field_role",
    "entity", "unit", "value_type", "granularity", "collection_mode",
    "availability", "source_artifact", "source_field", "dimensions",
    "ai_task_fit", "caveat",
]
W1_COLUMNS = [
    "definition_en", "w1_support", "evidence_class", "evidence_artifact",
    "evidence_field", "verification_level", "verified_runs",
    "verified_nonempty_count", "native_granularity", "scope_limit",
    "canonical_signal", "alias_ids",
]
SCREEN_COLUMNS = ["original_index", "decision", "decision_reason"]
SLOTS = ["D01", "D02", "D03", "D04", "D05", "D06", "D07"]

# Only explicit same-definition aliases are merged. Aggregated V3 views and
# instance-level source metrics remain separate definitions with stated scope.
ALIASES = {
    "v3.OT": "v3.n3_uplink_bitrate_bps",
    "nf.health_state": "nf.state",
    "traffic.service_completion_rate": "v3.business_completion_rate",
    "traffic.app_success_rate": "v3.business_completion_rate",
    "config.peak_ue_count": "access.expected_ue_count",
}
LEGACY_PROXIES = {
    "v3.end_to_end_rtt_ms", "v3.packet_loss_rate",
    "flow.estimated_rtt_ms", "flow.packet_loss_rate", "link.latency_ms",
}
EXCLUSIONS = {
    "cp.attempt_count": (
        "placeholder", "The historical collector initializes attempt_count to 1 without incrementing retries; a populated field is not a measured establishment-attempt count."
    ),
    "v3.is_filled_any": (
        "placeholder", "The historical exporter writes a fixed zero; it does not audit whether source values were filled."
    ),
    "fault.fault_label_source": (
        "no_producer", "No verified W1 production source for this proposed label-provenance field."
    ),
    "nf.capacity": (
        "placeholder", "No measured or configured K8s capacity field exists in the W1 NF-state records."
    ),
    "per_nf.resource_satisfaction": (
        "placeholder", "The historical score can default to 1 without resource-limit observations; it does not establish resource satisfaction."
    ),
    "traffic.timeout_count": (
        "invalid_aggregation", "The legacy recursive aggregation can count the same timeout in both summary and flow records; use deduplicated raw flow outcomes instead."
    ),
    "traffic.client_error_count": (
        "unverified_semantics", "The legacy recursive error aggregation has no verified one-event-one-count mapping for the W1 rotated stats schema."
    ),
    "gate.tun_present_ratio": (
        "invalid_aggregation", "Repeated TUN snapshot rows can inflate the numerator; the legacy value is not a verified fraction of unique UEs with TUNs."
    ),
    "health.collector_alive_count": (
        "no_producer", "W1 records collector_status[]; no same-name, correctly defined live-collector count is verified."
    ),
    "traffic.terminal_event_max_gap_sec": (
        "no_producer", "No verified W1 production source for this proposed terminal-event gap field."
    ),
    "config.slice_type": (
        "composite_template", "No independent slice_type field; use the separately retained session.dnn, session.snssai_sst and session.snssai_sd definitions."
    ),
}

DEFINITIONS = {
    "v3.time": "UTC start time of the exported time bucket; source streams retain their own native timestamps.",
    "v3.run_id": "Identifier of the W1 run whose records are exported.",
    "v3.session_id": "Experiment session identifier copied from run metadata; it is not a UE PDU-session identifier.",
    "v3.sample_index": "Zero-based index of the exported time bucket.",
    "v3.scenario_type": "Scenario name recorded in experiment metadata.",
    "v3.experiment_id": "Experiment identifier recorded in run metadata.",
    "v3.event_id": "Fault-timeline identifier associated with the current export interval; presence alone does not prove successful injection.",
    "v3.seconds_from_session_start": "Export-bucket time minus the first model bucket time, in seconds; this is experiment elapsed time.",
    "v3.time_to_planned_start_sec": "Seconds until the next planned intervention start according to the experiment timeline.",
    "v3.time_since_last_fault_end_sec": "Seconds since the previous intervention interval ended according to the timeline used by the exporter.",
    "v3.pre_state_status": "Declared pre-intervention status, with a historical stable fallback inferred from timeline presence; it is not an independently verified baseline-health measurement.",
    "v3.load_level": "Configured experiment load label.",
    "v3.ue_count": "Configured total number of UE workloads for the run.",
    "v3.gnb_count": "Configured total number of gNB workloads for the run.",
    "v3.gold_ue_count": "Configured UE workload count assigned to the gold tier.",
    "v3.silver_ue_count": "Configured UE workload count assigned to the silver tier.",
    "v3.traffic_profile_id": "Name or identifier of the configured business-traffic replay profile.",
    "v3.topology_id": "Topology label synthesized or recorded for the configured runtime and RAN profile.",
    "v3.dnn_profile": "DNN context attached to the export bucket from experiment/session metadata.",
    "v3.policy_version": "Recorded policy-version label, including the historical default fallback; it does not verify the policy installed in the network.",
    "v3.target_upf_id": "UPF target associated with the relevant planned intervention.",
    "v3.observed_phase": "Experiment phase reconstructed from phase events and projected onto the export grid.",
    "v3.observed_fault_active": "Fault-active label reconstructed from recorded fault intervals and projected onto the export grid.",
    "v3.recovery_elapsed_sec": "Elapsed seconds from the first exported recovery-phase bucket, populated only on recovery-labelled buckets; this is not per-fault service recovery latency.",
    "v3.data_quality_status": "Run-level quality conclusion projected onto export buckets; it is not an independent validation of every bucket.",
    "v3.is_valid_row": "Historical exporter validity mask based on run quality, paired intervals, access state and business coverage; it does not certify completeness or causal safety of every field.",
    "v3.metrics_available": "Historical resource-availability flag computed from direct model UPF CPU, UPF memory and host CPU columns before the gold/silver UPF aggregation fallback; it can remain zero despite later populated UPF resource exports.",
    "v3.is_filled_any": "Historical constant-zero compatibility placeholder, not a measured fill-provenance flag.",
    "v3.n3_uplink_bitrate_bps": "Historical N3 capture-total bitrate: captured bytes from both directions multiplied by 8 per packet time bucket, copied from N3 OT. Despite the legacy name this is not uplink-only bitrate.",
    "v3.OT": "Exact W1 compatibility alias of n3_uplink_bitrate_bps, containing bidirectional N3 capture-total bitrate.",
    "v3.n3_downlink_bitrate_bps": "N3 parser receive-classified captured bytes multiplied by 8 per packet time bucket, using the parser server-IP direction convention.",
    "v3.n6_bitrate_bps": "Retrospective N6 logical-link bitrate obtained by distributing completed-flow byte totals over their first-to-last-seen interval.",
    "v3.n4_bitrate_bps": "N4 captured-byte total multiplied by 8 per packet-time bucket, copied from the N4 PFCP parser OT series in accepted W1 runs.",
    "v3.cp_pdu_session_success_rate": "100 times cumulative parsed PDU-session successes divided by cumulative parsed PDU-session requests, held on the export grid; historical association fallback may also contribute.",
    "v3.cp_pdu_session_failure_count": "Cumulative parsed PDU-session failure-event count since control-plane collector initialization, held on the export grid.",
    "v3.cp_pdu_session_request_count": "Cumulative parsed PDU-session request-event count since control-plane collector initialization, held on the export grid.",
    "v3.cp_active_session_count": "Control-plane log-parser active-session state count held on the export grid; this is not authoritative NF population truth.",
    "v3.cp_pending_session_count": "Control-plane log-parser pending-session state count held on the export grid.",
    "v3.registration_success_rate": "100 times cumulative parsed registration successes divided by cumulative parsed registration requests, held on the export grid.",
    "v3.registration_failure_count": "Cumulative parsed registration failure-event count since control-plane collector initialization, held on the export grid.",
    "v3.registration_request_count": "Cumulative parsed registration request-event count since control-plane collector initialization, held on the export grid.",
    "v3.jitter_ms": "Mean completed-flow packet-interarrival variation grouped by flow first-seen bucket; this retrospective statistic can use packets observed after that bucket.",
    "v3.end_to_end_rtt_ms": "Legacy alternating-source packet-time-delta proxy without TCP sequence/ACK matching; it is not validated end-to-end RTT.",
    "v3.packet_loss_rate": "Legacy TCP sequence-backtracking fraction, confounding reordering and retransmission; it is not measured end-to-end packet loss.",
    "v3.business_completion_rate": "Rolling 60-second terminal sender-flow completed fraction, requiring at least 20 terminal records; not a server-confirmed delivery-success probability.",
    "v3.perf_upf_cpu_millicores": "Sum of available gold and silver UPF Pod CPU observations on the export grid; the original coverage metadata omitted this aggregation provenance.",
    "v3.perf_upf_memory_bytes": "Sum of available gold and silver UPF Pod memory observations on the export grid; the original coverage metadata omitted this aggregation provenance.",
    "v3.ran_pdu_active_count": "RAN log-parser PDU-active UE count projected from sparse log-supported snapshots.",
    "v3.ready_gnb_count": "Held gNB Ready-replica count from periodic RAN workload observations, applied after log-KPI snapshots by the historical model exporter; this is workload readiness rather than registered-UE truth.",
    "v3.observed_ue_count": "Historical observed-UE export field overwritten by ready_ue_count from periodic RAN workload observations and held on the export grid; it is not independently observed registered or traffic-active UE population.",
    "v3.host_cpu_pct": "Core-host CPU busy percentage from host-resource observations, held on the export grid.",
    "v3.host_mem_used_pct": "Core-host memory-used percentage from host-resource observations, held on the export grid.",
    "v3.host_loadavg_1": "Core-host one-minute load average, held on the export grid.",
    "context.runtime": "Runtime label carried in the verified W1 resource records; the accepted W1 runs use K8s.",
    "context.core_mode": "Configured core-network execution mode recorded in the run manifest.",
    "context.phase": "Recorded experiment phase event; this is an experiment label rather than an independent network-health measurement.",
    "fault.fault_id": "Identifier linking a scheduled or recorded fault action to its recovery and pairing evidence.",
    "fault.fault_type": "Fault-family label recorded for a core intervention.",
    "fault.fault_action": "Recorded fault action such as injection or restoration; execution evidence and effect must be checked separately.",
    "fault.target_nf": "NF-type target label recorded for the fault action.",
    "fault.target_instance": "NF/workload instance target recorded for the fault action.",
    "fault.affected_plane": "Protocol/data-plane label attached to the fault action.",
    "fault.affected_peer": "Peer endpoint label attached to the fault action.",
    "fault.fault_scope": "Scope label attached to the fault action, such as network or instance.",
    "fault.fault_active": "Recorded fault-interval label projected into model time buckets.",
    "pair.overlap_group": "Identifier pairing a core fault with the associated access-side behavior intervention.",
    "pair.component_role": "Planned component-role label distinguishing core-fault and access-behavior actions within a pair.",
    "pair.paired_required": "Configured requirement that the paired core/access interventions overlap.",
    "pair.v3_label": "Configured label of the paired intervention group.",
    "dimension.nf_type": "NF type associated with the observed K8s resource/state record.",
    "dimension.nf_id": "Mapped NF entity identifier in the resource record; retain runtime and instance context.",
    "dimension.instance_id": "NF instance identifier used to group resource and state observations.",
    "dimension.component_id": "Configured deployment/component identifier attached to a K8s observation.",
    "dimension.namespace": "K8s namespace of the observed workload.",
    "dimension.ifname": "Host network-interface name for the interface observation.",
    "dimension.pod_name": "K8s Pod name; recreation can change this identifier.",
    "dimension.pod_uid": "K8s Pod UID identifying a particular Pod lifetime.",
    "dimension.node_name": "K8s node name associated with the observed Pod/resource record.",
    "dimension.flow_id": "Parser-generated identifier of a captured flow; retain capture file/type context when joining.",
    "dimension.capture_type": "Packet/flow encapsulation label such as plain or gtpu recorded by the parser; the N3/N4/N6 observation plane must be obtained from capture-file context separately.",
    "host.loadavg_5": "Core-host five-minute system load average.",
    "host.loadavg_15": "Core-host fifteen-minute system load average.",
    "host.mem_total_bytes": "Core-host total physical memory reported by the host collector.",
    "host.mem_available_bytes": "Core-host memory available to applications reported by the host collector.",
    "host.mem_used_bytes": "Core-host total memory minus available memory, in bytes.",
    "host.swap_total_bytes": "Core-host configured swap capacity, in bytes.",
    "host.swap_free_bytes": "Core-host free swap bytes.",
    "host.swap_used_bytes": "Core-host total swap minus free swap, in bytes.",
    "host.swap_used_pct": "100 times used swap divided by configured swap capacity, subject to the collector zero-capacity convention.",
    "host.interface_count": "Number of interfaces represented in the latest host-collector snapshot.",
    "interface.rx_bytes": "Host-interface cumulative received-byte counter.",
    "interface.tx_bytes": "Host-interface cumulative transmitted-byte counter.",
    "interface.rx_packets": "Host-interface cumulative received-packet counter.",
    "interface.tx_packets": "Host-interface cumulative transmitted-packet counter.",
    "host_interface.rx_bps": "Host-interface received-byte counter difference divided by elapsed seconds; the legacy bps name denotes bytes/s here.",
    "host_interface.tx_bps": "Host-interface transmitted-byte counter difference divided by elapsed seconds; the legacy bps name denotes bytes/s here.",
    "interface.rx_pps": "Host-interface received-packet counter difference divided by elapsed seconds.",
    "interface.tx_pps": "Host-interface transmitted-packet counter difference divided by elapsed seconds.",
    "nf.state": "NF deployment health state inferred from desired, available and Ready replica observations.",
    "nf.health_state": "K8s NF health category equal to the inferred deployment state; it is an alias in this W1 runtime.",
    "nf.health_score": "Rule-derived K8s NF health score assigned from replica readiness/availability, using the historical 100/60/0 levels.",
    "nf.accept_new": "Rule-derived flag set when the K8s NF state is healthy; it is not a probed admission-control decision.",
    "k8s.desired_replicas": "Desired replica count reported for the NF deployment.",
    "k8s.available_replicas": "Available replica count reported for the NF deployment.",
    "k8s.ready_replicas": "Ready replica count reported for the NF deployment.",
    "k8s.updated_replicas": "Updated replica count reported for the NF deployment.",
    "k8s.pod_count": "Number of Pods associated with the NF deployment at the observation time.",
    "k8s.ready_pod_count": "Number of Ready Pods associated with the NF deployment at the observation time.",
    "k8s.restart_count": "Container restart count reported for the observed Pod or aggregated NF snapshot; preserve the exact source and Pod lifetime.",
    "k8s.container_count": "Number of containers represented by the Pod-state observation.",
    "k8s.ready_container_count": "Number of Ready containers represented by the Pod-state observation.",
    "k8s.cpu_millicores": "Pod/NF CPU usage reported by the K8s metrics API, converted to millicores.",
    "k8s.memory_bytes": "Pod/NF memory usage reported by the K8s metrics API, converted to bytes.",
    "k8s.cpu_request_millicores": "CPU resource request read from the observed Pod specification and expressed in millicores.",
    "k8s.memory_request_bytes": "Memory resource request read from the observed Pod specification and expressed in bytes.",
    "k8s.cpu_limit_millicores": "CPU resource limit read from the observed Pod specification and expressed in millicores.",
    "k8s.memory_limit_bytes": "Memory resource limit read from the observed Pod specification and expressed in bytes.",
    "k8s.node_cpu_allocatable_millicores": "Allocatable CPU capacity reported for the K8s node, in millicores.",
    "k8s.node_memory_allocatable_bytes": "Allocatable memory capacity reported for the K8s node, in bytes.",
    "k8s.cpu_pct_of_node": "100 times NF/Pod CPU usage divided by node allocatable CPU.",
    "k8s.cpu_pct_of_limit": "100 times NF/Pod CPU usage divided by its configured CPU limit; missing limits remain unavailable.",
    "k8s.memory_pct_of_limit": "100 times NF/Pod memory usage divided by its configured memory limit; missing limits remain unavailable.",
    "k8s_nf_network.rx_bps": "Pod-namespace received-byte counter difference multiplied by 8 and divided by elapsed seconds; hostNetwork and unavailable Pod-PID cases remain null.",
    "k8s_nf_network.tx_bps": "Pod-namespace transmitted-byte counter difference multiplied by 8 and divided by elapsed seconds; hostNetwork and unavailable Pod-PID cases remain null.",
    "k8s_nf_network.rx_pps": "Pod-namespace received-packet counter difference divided by elapsed seconds, only where private Pod-network observation is available.",
    "k8s_nf_network.tx_pps": "Pod-namespace transmitted-packet counter difference divided by elapsed seconds, only where private Pod-network observation is available.",
    "k8s.network_scope": "Network-observation scope identifying private Pod-network versus hostNetwork observations.",
    "k8s.network_status": "Network-sample availability/status explaining null private-network measurements.",
    "k8s.sample_status": "Resource-sample status distinguishing successful metrics from missing Pod or metrics API observations.",
    "k8s.event_count": "K8s Event object's cumulative occurrence count at observation time; repeated observations are not separate occurrences.",
    "cp.registration_success_count": "Cumulative registration-success log-event count since control-plane collector initialization.",
    "cp.pdu_session_success_count": "Cumulative PDU-session-success log-event count since control-plane collector initialization.",
    "cp.registered_ue_count": "Number of registered UEs represented in the control-plane log-parser state.",
    "cp.freshness_state": "Collector freshness category based on time since the last parsed control-plane event.",
    "cp.overall_status": "Aggregate control-plane collector-state label; it is not an independent health probe of the core.",
    "cp.snapshot_age_seconds": "Snapshot timestamp minus most recent parsed control-plane event timestamp, in seconds.",
    "cp.last_event_timestamp": "Timestamp of the latest control-plane event consumed by the log parser.",
    "cp.event_type": "Type of control-plane event parsed from retained NF logs.",
    "cp.attempt_count": "Cumulative establishment attempts tracked for the parser's UE/session state key.",
    "cp.establishment_latency_ms": "Elapsed time between matched parsed establishment-request and success events for a UE/session key.",
    "cp.failure_reason": "Failure reason attached to the parsed UE/session establishment state.",
    "cp.pfcp_session_established": "Parser-derived PFCP-session establishment evidence attached to the UE/session state or map.",
    "session.supi": "SUPI identifying the UE represented by the parsed session record.",
    "session.ue_id": "Parser UE identifier; retain its original string and run context.",
    "session.pdu_session_id": "PDU-session identifier within the UE context; it is not globally unique.",
    "session.dnn": "DNN associated with the parsed UE/session record.",
    "session.snssai_sst": "S-NSSAI SST associated with the parsed UE/session record where available.",
    "session.snssai_sd": "S-NSSAI SD associated with the parsed UE/session record where available.",
    "session.selected_amf": "AMF label carried by the parsed session state; W1 can contain the generic label AMF rather than an amf-a/amf-b instance association, while session_map values are empty.",
    "session.selected_smf": "SMF association reconstructed for the UE/session from retained logs.",
    "session.upf_id": "UPF association reconstructed for the UE/session from retained logs/configuration evidence.",
    "session.upf_pfcp_addr": "PFCP endpoint address associated with the parsed UPF/session mapping.",
    "session.ue_ip": "UE IP address associated with the parsed session; addresses may be reused over time.",
    "session.local_dl_teid": "Local downlink TEID associated with the parsed session; retain UE, time and tunnel context.",
    "session.teid_ul": "Uplink TEID associated with the parsed session; it is a tunnel identifier rather than a performance metric.",
    "session.teid_dl": "Downlink TEID associated with the parsed session; it is a tunnel identifier rather than a performance metric.",
    "session.ran_dl_teid": "RAN-side downlink TEID recorded by the session parser.",
    "session.ran_addr": "RAN endpoint address associated with the parsed session.",
    "access.expected_gnb_count": "Configured expected gNB count attached to the RAN log-KPI output; a final snapshot can have a different/default value.",
    "access.expected_ue_count": "Configured expected UE count attached to the RAN log-KPI output, not a measured peak population.",
    "access.registration_success_count": "Registration-success UE count reconstructed by the RAN log parser, with sparse retained-event support.",
    "access.pdu_active_count": "PDU-active UE count reconstructed by the RAN log parser, with sparse retained-event support.",
    "access.overall_status": "RAN log-parser aggregate status, distinct from periodic K8s workload readiness.",
    "access.gnb_anomaly_event_count": "gNB anomaly-event count within the RAN parser's native KPI bucket.",
    "access.ue_anomaly_event_count": "UE anomaly-event count within the RAN parser's native KPI bucket.",
    "access.ran_anomaly_event_count": "Access-side anomaly-event count within the RAN parser's native KPI bucket.",
    "access.ue_degraded_count": "UE count classified as degraded in the RAN parser's reconstructed state.",
    "access.gnb_degraded_count": "gNB count classified as degraded in the RAN parser's reconstructed state.",
    "access.ue_no_cell_available_count": "UE count with no-cell-available state in the RAN parser's reconstructed state.",
    "access.registration_state": "Last reconstructed UE registration state in the final retained RAN map.",
    "access.pdu_state": "Last reconstructed UE PDU-session state in the final retained RAN map.",
    "access.radio_state": "Last reconstructed UE radio state in the final retained RAN map.",
    "access.current_status": "Aggregate reconstructed UE status in the final retained RAN map.",
    "access.tun_up_time": "ISO-8601 timestamp of the UE TUN-up event in the retained RAN map; this is not elapsed TUN uptime.",
    "access.cell_selection_failure_count": "Cell-selection-failure event count accumulated for the UE in the retained RAN map.",
    "access.service_request_retry_count": "Service-request retry event count accumulated for the UE in the retained RAN map.",
    "access.no_cell_available_count": "No-cell-available event count accumulated for the UE in the retained RAN map.",
    "access.workload.ready_ue_count": "UE workload Ready-replica count from periodic K3s workload observation; it is not registered or traffic-active UE count.",
    "access.workload.gold_ue_count": "Ready UE workload replica count in the gold tier from periodic K3s observation.",
    "access.workload.silver_ue_count": "Ready UE workload replica count in the silver tier from periodic K3s observation.",
    "flow.packets": "Number of captured packets assigned to the complete parsed flow.",
    "flow.bytes": "Captured-byte total assigned to the complete parsed flow.",
    "flow.duration_s": "Last captured packet time minus first captured packet time for the flow, in seconds.",
    "flow.uplink_packets": "Flow packets classified as uplink by the parser's server-IP convention.",
    "flow.downlink_packets": "Flow packets classified as downlink by the parser's server-IP convention.",
    "flow.uplink_bytes": "Flow captured bytes classified as uplink by the parser's server-IP convention.",
    "flow.downlink_bytes": "Flow captured bytes classified as downlink by the parser's server-IP convention.",
    "flow.uplink_throughput_bps": "Complete-flow uplink-classified bytes multiplied by 8 and divided by complete-flow duration.",
    "flow.downlink_throughput_bps": "Complete-flow downlink-classified bytes multiplied by 8 and divided by complete-flow duration.",
    "flow.avg_pkt_size": "Complete-flow captured bytes divided by captured packet count.",
    "flow.flow_duration_ms": "Last captured packet time minus first captured packet time, expressed in milliseconds.",
    "flow.avg_inter_arrival_ms": "Mean adjacent captured-packet timestamp difference over the complete flow.",
    "flow.jitter_ms": "Mean absolute difference between adjacent packet interarrival intervals over the complete flow; insufficient samples or mean interval at least 10 seconds are encoded as zero by the historical parser.",
    "flow.burst_count": "Count of short time buckets exceeding a threshold based on the complete-flow mean; it is not a count of contiguous burst episodes.",
    "flow.burst_max_bytes": "Largest byte total among threshold-exceeding burst buckets; zero when no bucket exceeds the historical complete-flow threshold.",
    "flow.burst_max_rate_bps": "Historical burst_max_bytes converted using the fixed burst-bucket duration, rather than a separately observed rate.",
    "pcap.tx_pkts": "Captured-packet count in a parser-transmit-classified packet-time bucket.",
    "pcap.tx_bytes": "Captured-byte count in a parser-transmit-classified packet-time bucket.",
    "pcap.rx_pkts": "Captured-packet count in a parser-receive-classified packet-time bucket.",
    "pcap.rx_bytes": "Captured-byte count in a parser-receive-classified packet-time bucket.",
    "pcap.tcp_conns": "Distinct directed TCP tuple count observed in the packet-time bucket; handshake success is not checked and both directions may count separately.",
    "pcap.icmp_cnt": "Captured ICMP packet count in the packet-time bucket.",
    "link.observation_count": "Indicator/count of retained log-event or flow observations supporting an NF link; it is not a count of network packets.",
    "link.ue_count": "UE-association indicator/count for the link observation; repeated observations do not imply distinct online UEs.",
    "link.session_count": "Session-association indicator/count for the link observation; repeated edges/events do not imply distinct active sessions.",
    "link.packets": "Complete-flow captured packet total attributed to the inferred NF link; the flow can be bidirectional despite first-packet edge orientation.",
    "link.bytes": "Complete-flow captured-byte total attributed to the inferred NF link; it can share a capture source with flow-level products.",
    "link.session_setup_latency_ms": "Matched session-establishment duration copied to an inferred NF link; it is not that link's network propagation or request-response latency.",
    "traffic.success_count": "Sender flows with completed=true in the retrospective terminal-outcome window.",
    "traffic.failure_count": "Other terminal sender-flow outcomes in the retrospective window, including timeout, stop or cancellation.",
    "traffic.sample_count": "Terminal sender-flow records counted in the retrospective completion window.",
    "traffic.completion_rate": "Sender completed-flow count divided by terminal-flow count in the completion window, output only when the minimum terminal-sample threshold is met.",
    "traffic.coverage": "Terminal-sample sufficiency/coverage label for the business completion window.",
    "traffic.terminal_sample_count": "Number of terminal sender-flow outcomes in the trailing 60-second model window across retained tiers.",
    "traffic.terminal_sample_count_gold": "Number of gold-tier terminal sender-flow outcomes in the trailing 60-second model window.",
    "traffic.terminal_sample_count_silver": "Number of silver-tier terminal sender-flow outcomes in the trailing 60-second model window.",
    "traffic.service_completion_rate": "Fraction completed=true among at least 20 terminal sender-flow records in the trailing 60-second model window.",
    "traffic.service_completion_rate_gold": "Gold-tier completed fraction among at least 20 terminal sender-flow records in the trailing 60-second model window.",
    "traffic.service_completion_rate_silver": "Silver-tier completed fraction among at least 20 terminal sender-flow records in the trailing 60-second model window.",
    "traffic.completed_flows": "Retrospective run-summary count of recorded sender flows marked completed; not a fresh per-second measurement.",
    "traffic.launched_flows": "Historical run-summary field populated from archived flow-record counts in the rotated W1 producer; it is not an independently measured initiation count.",
    "traffic.stats_file_count": "Number of traffic statistics files included by the historical run-summary aggregation.",
    "traffic.total_planned_flows": "Historical planned-flow summary value, with an archived-record-count fallback when no explicit plan total exists.",
    "traffic.recorded_flows": "Number of flow records represented in the retrospective traffic summary.",
    "traffic.unfinished_threads": "Unfinished sender worker/thread count reported in the retrospective traffic summary.",
    "traffic.sent_packets": "Application sender action/data-block count from the retrospective run summary; this is not necessarily an IP packet count.",
    "traffic.sent_bytes": "Sender-reported bytes in the retrospective run summary; TCP framing and UDP payload accounting can differ and delivery is not confirmed.",
    "traffic.iteration": "Rotation/iteration index attached to the archived sender statistics segment.",
    "traffic.rotation_secs": "Configured duration of a sender statistics rotation segment.",
    "traffic.partial": "Flag identifying an incomplete final sender statistics rotation segment.",
    "model.concurrency_ratio": "Model observed-UE count divided by configured expected UE count; parser state can be stale and this is not traffic concurrency.",
    "model.per_ue_ul_mbps": "Aggregate model uplink-labelled bitrate divided by observed UE count and 1e6; a cohort mean inheriting legacy direction and retrospective-flow limitations.",
    "model.per_ue_dl_mbps": "Aggregate model downlink-labelled bitrate divided by observed UE count and 1e6; a cohort mean rather than per-SUPI throughput observation.",
    "per_nf.active_ues": "Cumulative UE association-set size attached to an NF by the historical exporter; associations are not removed on UE departure.",
    "per_nf.pdu_sessions": "Cumulative session association-set/map size attached to an NF by the historical exporter, not current active-session occupancy.",
    "per_nf.session_events": "Historical NF session-association/event accumulator; it is not automatically a per-bucket event-arrival count.",
    "per_nf.traffic_bytes": "Complete-flow bytes retrospectively distributed into time buckets and attributed to an UPF; not independently sampled per-NF wire bytes.",
    "per_nf.traffic_packets": "Complete-flow packets retrospectively distributed into time buckets and attributed to an UPF; fractional weighted values can occur.",
    "per_nf.throughput_bps": "Retrospective UPF-attributed complete-flow byte allocation converted to bitrate per export bucket.",
    "per_nf.pod_ready": "Held Pod readiness observation in the per-NF export; the export grid does not add independent Pod samples.",
    "per_nf.pod_restart_count": "Held cumulative Pod restart count in the per-NF export; preserve the Pod UID/lifetime.",
    "recovery.recovery_latency_s": "Retrospective elapsed time from fault recovery reference to observed session reconstruction, where such reconstruction is observed.",
    "recovery.affected_session_count": "Number of fault/session evaluation rows in the run-level recovery summary; the same UE/session may appear for multiple faults.",
    "recovery.rebuilt_session_count": "Number of fault/session evaluation rows classified as rebuilt in the run-level recovery summary.",
    "recovery.unobserved_session_count": "Number of fault/session evaluation rows classified as unobserved; missing reconstruction evidence is not proof of recovery failure.",
    "recovery.recovery_success_rate": "Run-summary rebuilt_session_count divided by affected_session_count, rounded to six decimals; empty when the affected-row denominator is zero.",
    "recovery.flow_recovery_ratio": "Retrospective post-recovery flow rate relative to the pre-fault baseline over the configured evaluation windows.",
    "recovery.recovery_result": "Retrospective session recovery outcome such as rebuilt, unobserved or not_required.",
    "recovery.old_instance": "NF instance associated with the session before the evaluated fault/recovery event.",
    "recovery.new_instance": "NF instance associated with the reconstructed session after the evaluated recovery event.",
    "health.disk_free_bytes": "Free bytes on the monitored artifact filesystem at the run-health sample time.",
    "health.raw_offset_ms": "Raw remote-clock offset estimated from a clock probe before latency correction; retain probe availability and host role.",
    "health.offset_uncertainty_ms": "Clock-probe offset uncertainty estimated from probe round-trip latency.",
    "health.probe_latency_ms": "Clock-probe round-trip latency, not one-way network propagation delay.",
    "health.clock_skew_ms": "Aggregate estimated clock skew reported by the run-health monitor; clock-probe uncertainty still applies.",
    "health.capture_files": "Structured capture-file status with path, observed byte size and expected-active state.",
    "health.traffic_liveness": "Structured traffic-path/process and lifecycle liveness evidence, including whether remote checks were actually performed.",
    "dataset.dataset_ready": "Retrospective dataset-card readiness flag; it does not replace the separate experiment, quality and recovery verdicts.",
    "dataset.known_limits": "List of known data/coverage limitations recorded in the retrospective dataset card.",
    "config.service_type": "Service-type scenario/configuration label, distinct from actual packet transport or verified application behavior.",
    "config.user_level": "Configured or DNN-inferred user-tier label attached to model buckets; mixed can denote multiple tiers.",
    "config.bandwidth_limit_mbps": "Declared bandwidth-limit metadata, including unlimited; this does not by itself verify installed traffic-control enforcement.",
    "gate.accepted": "Stored Boolean verdict of the separately named quality, stability or endurance gate; each gate retains its own checks and acceptance scope.",
    "gate.actual_overlap_secs": "Duration in seconds of the recorded overlap between paired core-fault and access-behavior intervals, as evaluated retrospectively by the pairing gate.",
    "gate.actual_to_planned_ratio": "Recorded actual overlap/intervention duration divided by the corresponding planned duration in the pairing-gate detail; preserve the event/detail key.",
}


def load_json(path):
    with Path(path).open(encoding="utf-8") as stream:
        return json.load(stream)


def read_csv(path):
    with Path(path).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, columns, extrasaction="ignore", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def csv_text(rows, columns):
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, columns, extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def classify_evidence(path, row):
    if path == "run_manifest.json" or row["field_role"] == "configuration":
        return "config"
    if path.startswith("report/"):
        return "report"
    if path.startswith("derived/"):
        return "derived"
    if path in {"metrics/control-plane-kpis.jsonl", "metrics/ran-kpis.jsonl", "events/control-plane.jsonl", "events/ran-ue.jsonl"}:
        return "parser"
    return "direct"


def native_for(path, field):
    if path == "report/v3_timeseries.csv":
        return "1 s export grid; source-native cadence differs"
    if path in {"metrics/host-resource.jsonl", "metrics/interface-resource.jsonl"}:
        return "approximately 5 s host-collector samples (D01 timing sample)"
    if path in {"metrics/nf-resource.jsonl", "metrics/nf-state.jsonl", "metrics/k8s-pod-resource.jsonl", "metrics/k8s-pod-state.jsonl"}:
        return "approximately 8.7-10.4 s K8s samples (D01 timing sample)"
    if path == "metrics/control-plane-kpis.jsonl":
        return "approximately 2 s parser-state snapshots (D01 timing sample)"
    if path == "metrics/ran-workloads.jsonl":
        return "approximately 5.4 s K3s workload samples (D01 timing sample)"
    if path == "metrics/ran-kpis.jsonl":
        return "10 s log-derived buckets plus final snapshot; sparse retained-event support"
    if path == "derived/ran-ue-map.jsonl":
        return "final per-UE parser map; not a periodic per-UE stream"
    if path == "derived/session_map.jsonl":
        return "parsed session mapping observation"
    if path == "derived/session-state.jsonl":
        return "parser state snapshot by UE/session key"
    if "_flows.jsonl" in path:
        return "completed captured flow; offline"
    if "_timeseries.csv" in path or "_ts.csv" in path:
        return "packet-time bucket; parser direction convention"
    if path == "run_manifest.json":
        return "run configuration"
    if path.startswith("events/"):
        return "recorded event/action"
    return "source-native record; see source artifact"


def scope_for(row, path):
    cid = row["canonical_id"]
    limits = ["W1 accepted D01-D07 only; field definitions are not independent measurement dimensions."]
    if path == "report/v3_timeseries.csv":
        limits.append("The 1 s export grid can hold, repeat or retrospectively project source observations.")
    if row["field_role"] in {"label", "configuration"} or cid.startswith(("fault.", "pair.", "recovery.", "gate.", "dataset.")):
        limits.append("Keep planned/actual labels and post-event outcomes separate from prospective model inputs.")
    if cid.startswith(("cp.", "session.", "v3.cp_", "v3.registration_")):
        limits.append("Parsed log/state evidence can be incomplete or stale; keep freshness and last-event timestamps.")
    if cid.startswith("access.") and not cid.startswith("access.workload."):
        limits.append("Retained UE log fragments support limited intervals, not 24 h continuous per-UE ground truth.")
    if cid.startswith(("flow.", "link.", "per_nf.traffic", "per_nf.throughput")) or cid in {"v3.jitter_ms", "v3.n6_bitrate_bps", "model.per_ue_ul_mbps", "model.per_ue_dl_mbps"}:
        limits.append("Offline derived product; later flow packets can affect earlier buckets. Preserve capture/source attribution and avoid duplicate observation points.")
    if cid.startswith(("flow.", "pcap.")) or cid in {"v3.n3_uplink_bitrate_bps", "v3.n3_downlink_bitrate_bps", "v3.n4_bitrate_bps"}:
        limits.append("Byte totals use parsed IP length when available, with captured-buffer length as fallback; they are not the number of bytes saved after snaplen truncation.")
    if cid.startswith(("traffic.",)) or cid == "v3.business_completion_rate":
        limits.append("Representative sender UE per gold/silver tier; live and rotated snapshots overlap and require terminal-record deduplication.")
    if cid.startswith("k8s_nf_network."):
        limits.append("W1 private-Pod network rates exist for seven NF instances; both AMFs, both UPFs and smf-gold have no attributed network-rate samples.")
    if cid in {"k8s.cpu_millicores", "k8s.memory_bytes", "v3.perf_upf_cpu_millicores", "v3.perf_upf_memory_bytes"}:
        limits.append("Pod metrics do not include complete gtp5g kernel forwarding cost; retain missing-sample status and Pod lifetime.")
    if cid.startswith(("host.", "host_interface.", "interface.", "v3.host_")):
        limits.append("Monitored core-host/interface scope; this is not independently sampled telemetry for all three machines or private NF traffic.")
    return " ".join(limits)


def raw_candidates(row):
    cid = row["canonical_id"]
    if cid == "cp.event_type":
        return [("events/control-plane.jsonl", "event_type")]
    if cid in {"pair.paired_required", "pair.v3_label"}:
        return [("events/fault_timeline.jsonl", row["source_field"])]
    if cid == "context.runtime":
        return [("metrics/nf-resource.jsonl", "runtime")]
    if cid == "context.core_mode":
        return [("run_manifest.json", "core_mode")]
    if cid == "fault.fault_label_source":
        return []
    return [
        (path, row["source_field"])
        for path in row["source_artifact"].split(";")
        if path != "fault plan" and "*" not in path and "<" not in path
    ]


def verify_raw(row, inventory):
    candidates = []
    for path, field in raw_candidates(row):
        if path == "run_manifest.json":
            slots = [r["slot"] for r in inventory if r.get("manifest", {}).get(field) is not None]
            count = len(slots)
            level = "full_small_manifest_scan"
        else:
            slots, count = [], 0
            for run in inventory:
                record = run.get("files", {}).get(path, {})
                n = record.get("sample_nonempty_counts", record.get("sample_nonnull_counts", {})).get(field, 0)
                if n:
                    slots.append(run["slot"])
                    count += n
            level = "sample_up_to_1000_records_per_run"
        if count:
            candidates.append((len(slots), count, path, field, level, slots))
    if not candidates:
        return None
    # Prefer the declared first artifact when coverage is equal. Counts describe
    # this chosen source only, never a sum of duplicate source representations.
    best = max(enumerate(candidates), key=lambda item: (item[1][0], -item[0]))[1]
    _, count, path, field, level, slots = best
    return {
        "evidence_artifact": path,
        "evidence_field": field,
        "verification_level": level,
        "verified_runs": ";".join(slots),
        "verified_nonempty_count": count,
        "evidence_class": classify_evidence(path, row),
        "native_granularity": native_for(path, field),
    }


def verify_v3(row, scan):
    field = row["field_name"]
    values = [(r["slot"], r["fields"][field]["actual_present_count"]) for r in scan["runs"]]
    return {
        "evidence_artifact": "report/v3_timeseries.csv",
        "evidence_field": field,
        "verification_level": "full_export_scan",
        "verified_runs": ";".join(slot for slot, count in values if count),
        "verified_nonempty_count": sum(count for _, count in values),
        "evidence_class": "report",
        "native_granularity": native_for("report/v3_timeseries.csv", field),
    }


def prepare_inputs(legacy, base, inventory, scan, extra, target):
    """Write a privacy-minimized reproducibility bundle; never include values."""
    target.mkdir(parents=True, exist_ok=True)
    write_csv(target / "legacy_400.csv", legacy, LEGACY_COLUMNS)
    write_csv(target / "legacy_81.csv", base, list(base[0]))
    minimized = []
    for run in inventory:
        minimized.append({
            "slot": run["slot"],
            "manifest": {key: True for key, value in run.get("manifest", {}).items() if value is not None},
            "files": {
                path: {key: obj[key] for key in ("lines", "keys", "sample_nonnull_counts", "sample_nonempty_counts") if key in obj}
                for path, obj in run.get("files", {}).items()
            },
        })
    minimal_scan = {"runs": [{
        "slot": run["slot"], "actual_rows": run["actual_rows"],
        "column_count": run["column_count"],
        "ot_n3_exact_string_mismatches": run["ot_n3_exact_string_mismatches"],
        "fields": {field: {key: values[key] for key in (
            "actual_present_count", "actual_coverage_ratio", "status", "source_file", "source_column", "missing_reason"
        ) if key in values} for field, values in run["fields"].items()},
    } for run in scan["runs"]]}
    for name, data in [("raw_inventory.json", minimized), ("v3_scan_summary.json", minimal_scan), ("nonv3_evidence.json", extra)]:
        (target / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_extra(extra):
    if "fields" in extra:
        extra = extra["fields"]
    if isinstance(extra, list):
        return {r["canonical_id"]: r for r in extra}
    return extra


def build(legacy, base, inventory, scan, extra):
    assert len(legacy) == 400, "The screening input must contain the historical 400 rows"
    assert len(base) == 81, "The compatibility schema must contain exactly 81 rows"
    assert len({r["canonical_id"] for r in legacy}) == 400
    screening = []
    overlays = normalize_extra(extra)
    for index, old in enumerate(legacy, 1):
        row = {**old, **{key: "" for key in W1_COLUMNS}}
        cid = row["canonical_id"]
        row["schema_version"] = "w1-field-dictionary/v1"
        row["original_index"] = index
        row["canonical_signal"] = ALIASES.get(cid, cid)
        row["definition_en"] = DEFINITIONS.get(cid, old["caveat"].rstrip(".") + ".")
        evidence = verify_v3(row, scan) if cid.startswith("v3.") else verify_raw(row, inventory)
        overlay = overlays.get(cid, {})
        if evidence:
            row.update(evidence)
        evidence_keys = {"evidence_artifact", "evidence_field", "verification_level", "verified_runs", "verified_nonempty_count", "evidence_class", "native_granularity"}
        for key in W1_COLUMNS + ["unit", "value_type", "field_role"]:
            if key in overlay:
                if key == "canonical_signal" or (key == "definition_en" and cid in DEFINITIONS):
                    continue
                if evidence and key in evidence_keys:
                    continue
                value = overlay[key]
                if key == "verified_runs" and isinstance(value, list):
                    value = ";".join(value)
                row[key] = value
        row["evidence_class"] = {"raw_observation": "direct", "log_parser": "parser", "configuration": "config"}.get(row["evidence_class"], row["evidence_class"])
        if row["evidence_artifact"]:
            row["evidence_class"] = classify_evidence(row["evidence_artifact"].split(";")[0], row)
        path = row["evidence_artifact"]
        row["scope_limit"] = " ".join(filter(None, [scope_for(row, path), row["scope_limit"]]))
        if cid in {"v3.cp_pdu_session_success_rate", "v3.registration_success_rate"}:
            row["unit"] = "percent"
        if cid == "access.tun_up_time":
            row.update(unit="ISO-8601", value_type="datetime", field_role="event", collection_mode="parsed")
        if cid == "gate.field_coverage":
            row.update(unit="", value_type="object")
        if cid in {"per_nf.traffic_bytes", "per_nf.traffic_packets"}:
            row["value_type"] = "float"
        if cid == "fault.fault_active":
            row["evidence_artifact"] = "report/model_timeseries.csv;report/per_nf_timeseries.csv"
            row["evidence_class"] = "report"
        if cid == "dimension.capture_type":
            row["evidence_artifact"] = "derived/*_flows.jsonl"
        if cid in {"v3.perf_upf_cpu_millicores", "v3.perf_upf_memory_bytes"}:
            row["collection_mode"] = "aggregate"
        if cid in {"recovery.affected_session_count", "recovery.rebuilt_session_count", "recovery.unobserved_session_count", "recovery.recovery_success_rate"}:
            row["entity"] = "run"
            row["native_granularity"] = "post-run session-recovery summary"
        if cid.startswith("v3.planned_"):
            suffix = cid.removeprefix("v3.planned_")
            labels = {
                "treatment_type": "treatment label, including the historical timeline fallback",
                "fault_family": "fault-family label, including the historical timeline fallback",
                "target_interface": "target interface", "target_ne": "target network element",
                "peer": "peer endpoint", "instance": "target instance",
                "fault_duration_sec": "fault duration in seconds", "fault_active": "fault-active interval indicator",
                "start_offset_sec": "intervention start offset from experiment start",
                "delay_ms": "netem delay in milliseconds", "loss_pct": "netem loss percentage",
            }
            row["definition_en"] = "Planned " + labels.get(suffix, suffix.replace("_", " ")) + "; this is schedule metadata rather than observed execution or measured impairment."
        if cid.startswith("bp."):
            decision, support, reason = "exclude", "later_capability", "Later business-prevalidation capability, outside the frozen W1 K8s collection."
        elif old["availability"] == "baremetal_only":
            decision, support, reason = "exclude", "wrong_runtime", "Bare-metal-only field; accepted W1 runs use K8s and the process-resource files are empty."
        elif cid.startswith("model.family.") or cid == "model.user_level_session_count":
            decision, support, reason = "exclude", "field_family_template", "Dynamic field-family template rather than one concrete, source-verified field definition."
        elif cid in EXCLUSIONS:
            support, reason = EXCLUSIONS[cid]
            decision = "exclude"
        elif cid in LEGACY_PROXIES:
            decision, support, reason = "exclude", "legacy_proxy", "Historical proxy has no validated physical meaning as the named RTT/loss/link-delay measurement; retained only in the compatibility/crosswalk documentation."
        elif cid in ALIASES:
            decision, support, reason = "merge_alias", "alias", "Same source definition and scope as " + ALIASES[cid] + "; not counted as an additional canonical definition."
        elif overlay.get("decision") in {"exclude", "unverified", "merge_alias"}:
            decision = overlay["decision"]
            support = overlay.get("w1_support", "unverified" if decision == "unverified" else "not_supported")
            reason = overlay.get("decision_reason", overlay.get("reason", "Targeted evidence audit did not establish a supported W1 field."))
            if decision == "merge_alias":
                row["canonical_signal"] = overlay["canonical_signal"]
        elif row["verified_nonempty_count"] not in {"", None, 0, "0"} and row["verified_runs"]:
            decision, support = "retain", "observed"
            reason = "Nonempty values verified in accepted W1 artifacts; verification scope is recorded separately and does not claim full source-stream coverage."
            if cid.startswith("v3.") and cid in {"v3.perf_upf_cpu_millicores", "v3.perf_upf_memory_bytes"}:
                support = "observed_metadata_bug"
                reason = "Full export scan and raw UPF observations confirm values; historical coverage metadata omitted the gold/silver aggregation source."
            elif cid == "v3.ran_pdu_active_count":
                support = "observed_sparse_snapshot"
            elif cid in {"v3.ready_gnb_count", "v3.observed_ue_count"}:
                support = "observed_workload_projection"
                reason = "Full export scan verifies values. Historical snapshot_only coverage metadata does not distinguish that periodic workload Ready snapshots overwrite the log-KPI source and are held on the export grid."
        else:
            raw_keys = {field for run in inventory for record in run.get("files", {}).values() for field in record.get("keys", [])}
            if cid.startswith("v3."):
                decision, support, reason = "exclude", "all_empty", "Full scan of all seven W1 export tables finds this compatibility field entirely empty."
            elif old["source_field"] in raw_keys:
                decision, support, reason = "unverified", "unverified_source", "A same-named field exists somewhere, but its declared source/scope has no verified nonempty W1 value."
            else:
                decision, support, reason = "unverified", "unverified_source", "No verified nonempty value in the inspected W1 source records; schema declarations or current producer capability alone are insufficient."
        row.update(decision=decision, decision_reason=reason, w1_support=support)
        if decision == "retain":
            row["source_artifact"] = row["evidence_artifact"]
            row["source_field"] = row["evidence_field"]
            row["availability"] = "w1_observed;see_verification_level"
            row["granularity"] = row["native_granularity"]
            row["caveat"] = row["scope_limit"]
        screening.append(row)

    retained = {r["canonical_id"]: r for r in screening if r["decision"] == "retain"}
    for row in screening:
        if row["decision"] == "merge_alias":
            target = row["canonical_signal"]
            if target not in retained:
                row.update(decision="unverified", w1_support="alias_target_unverified", decision_reason="Proposed alias target has no retained W1 source definition: " + target)
            else:
                old_aliases = retained[target]["alias_ids"]
                retained[target]["alias_ids"] = ";".join(filter(None, [old_aliases, row["canonical_id"]]))
    main = [r for r in screening if r["decision"] == "retain"]
    by_id = {r["canonical_id"]: r for r in screening}
    compatibility = []
    for old in base:
        row = {**old, **{key: by_id[old["canonical_id"]][key] for key in W1_COLUMNS + SCREEN_COLUMNS}}
        reviewed = by_id[old["canonical_id"]]
        row.update(unit=reviewed["unit"], value_type=reviewed["value_type"], field_role=reviewed["field_role"], collection_mode=reviewed["collection_mode"])
        row["definition"] = reviewed["definition_en"]
        row["definition_scope"] = "W1 observed evidence and compatibility status; see w1_support and verification_level"
        row["source_caveat_reference"] = "W1_FIELD_SCREENING_400.csv#" + old["canonical_id"]
        compatibility.append(row)

    assert len(screening) == 400
    assert {r["canonical_id"] for r in screening} == {r["canonical_id"] for r in legacy}
    assert len(compatibility) == 81
    assert [r["field_name"] for r in compatibility] == [r["field_name"] for r in base]
    for row in main:
        assert row["definition_en"] and row["evidence_class"]
        assert row["evidence_class"] in {"direct", "parser", "derived", "config", "report"}
        assert row["evidence_artifact"] and row["evidence_field"]
        assert row["verification_level"] and row["verified_runs"]
        assert row["native_granularity"] and row["scope_limit"]
        assert not row["canonical_id"].startswith("bp.")
    assert "v3.OT" not in retained
    assert retained["v3.n3_uplink_bitrate_bps"]["alias_ids"].find("v3.OT") >= 0
    assert retained["v3.cp_pdu_session_success_rate"]["unit"] == "percent"
    assert retained["v3.registration_success_rate"]["unit"] == "percent"
    assert retained["access.tun_up_time"]["unit"] == "ISO-8601"
    summary = {
        "schema_version": "w1-field-dictionary/v1",
        "scope": "accepted W1 D01-D07; frozen original-run artifacts only",
        "counting_unit": "canonical field definition across source artifacts/entities/granularities; not independent measured numeric dimensions",
        "legacy_screened_rows": len(screening),
        "retained_field_definitions": len(main),
        "retained_by_role": dict(sorted(Counter(r["field_role"] for r in main).items())),
        "retained_by_evidence_class": dict(sorted(Counter(r["evidence_class"] for r in main).items())),
        "retained_by_verification_level": dict(sorted(Counter(r["verification_level"] for r in main).items())),
        "screening_decisions": dict(sorted(Counter(r["decision"] for r in screening).items())),
        "screening_support": dict(sorted(Counter(r["w1_support"] for r in screening).items())),
        "compatibility_columns": len(compatibility),
        "compatibility_nonempty_columns_per_run": {run["slot"]: sum(f["actual_present_count"] > 0 for f in run["fields"].values()) for run in scan["runs"]},
        "export_rows_per_run": {run["slot"]: run["actual_rows"] for run in scan["runs"]},
        "export_rows_total": sum(run["actual_rows"] for run in scan["runs"]),
        "evidence_count_note": "verified_nonempty_count counts listed evidence source records under verification_level, potentially across several stated representations. Zero, false and empty structured lists can be recorded values; nonempty is not independent validity. Sample counts must not be presented as full-stream coverage or distinct physical events.",
        "known_limits": [
            "Retained definitions include configuration, identifiers, labels, states, evidence and quality as well as metrics.",
            "A source field and its exported aggregation can both be retained because their entity/granularity differ; never sum their counts as independent signals.",
            "The historical 81-column CSV schema is preserved, including empty fields, legacy proxies and aliases.",
            "N3 uplink-labelled field contains total captured traffic in both directions; OT is its exact alias.",
            "CP rates are percentages; request/success/failure counters are cumulative parser counts.",
            "UPF CPU/memory exist despite historical missing-source coverage metadata; Pod cost is not complete kernel forwarding cost.",
            "Sparse RAN log snapshots do not establish continuous full-day per-UE state.",
            "Retrospective flow-derived metrics can use future packets and are not online-safe at their assigned first-seen buckets.",
            "Business observations come from representative sender UEs per tier, not all 40 UEs.",
        ],
        "validation": {"legacy_rows_accounted_for": True, "compatibility_schema_preserved": True, "required_evidence_metadata_present": True, "original_run_data_modified": False},
    }
    return main, screening, compatibility, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    inputs = root / "platform_data/evidence/w1_dictionary_inputs"
    parser.add_argument("--legacy-dictionary", type=Path, default=inputs / "legacy_400.csv")
    parser.add_argument("--legacy-base-table", type=Path, default=inputs / "legacy_81.csv")
    parser.add_argument("--raw-inventory", type=Path, default=inputs / "raw_inventory.json")
    parser.add_argument("--v3-summary", type=Path, default=inputs / "v3_scan_summary.json")
    parser.add_argument("--nonv3-evidence", type=Path, default=inputs / "nonv3_evidence.json")
    parser.add_argument("--output-root", type=Path, default=root)
    parser.add_argument("--write-input-bundle", type=Path, help="Optional privacy-minimized evidence bundle destination")
    parser.add_argument("--check", action="store_true", help="Rebuild in memory and compare published outputs without writing files")
    args = parser.parse_args()
    legacy = read_csv(args.legacy_dictionary)
    base = read_csv(args.legacy_base_table)
    inventory = load_json(args.raw_inventory)
    scan = load_json(args.v3_summary)
    extra = load_json(args.nonv3_evidence)
    main_rows, screening, compatibility, summary = build(legacy, base, inventory, scan, extra)
    if args.write_input_bundle and args.check:
        parser.error("--check cannot be combined with --write-input-bundle")
    if args.write_input_bundle:
        prepare_inputs(legacy, base, inventory, scan, extra, args.write_input_bundle)
    dictionary_dir = args.output_root / "platform_data/dictionaries"
    columns = LEGACY_COLUMNS + W1_COLUMNS
    outputs = {
        dictionary_dir / "W1_FIELD_DICTIONARY.csv": csv_text(main_rows, columns),
        args.output_root / "manuscript_supplement/data/field_dictionary.csv": csv_text(main_rows, columns),
        dictionary_dir / "W1_FIELD_SCREENING_400.csv": csv_text(screening, LEGACY_COLUMNS + W1_COLUMNS + SCREEN_COLUMNS),
        dictionary_dir / "BASE_TABLE_81.csv": csv_text(compatibility, list(base[0]) + W1_COLUMNS + SCREEN_COLUMNS),
        dictionary_dir / "W1_DICTIONARY_SUMMARY.json": json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
    }
    if args.check:
        differences = [str(path.relative_to(args.output_root)) for path, expected in outputs.items() if not path.exists() or path.read_text(encoding="utf-8") != expected]
        if differences:
            raise SystemExit("W1 dictionary outputs differ from offline rebuild: " + ", ".join(differences))
    else:
        for path, content in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
    print(json.dumps({key: summary[key] for key in ("retained_field_definitions", "retained_by_role", "screening_decisions", "export_rows_total")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
