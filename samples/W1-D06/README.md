# W1-D06 Configuration and Data Examples

These files illustrate the configuration, execution records, and collected data from W1-D06. Observation times and operation/session identifiers are retained. Site addresses, hostnames, usernames, and simulated subscriber identifiers are anonymized consistently across files.

## Directory guide

| Materials | Files | Scope |
| --- | --- | --- |
| Run and network configuration | [Run manifest](run_manifest.json), [topology](config/runtime/k8s-topology.json), and [traffic scenario](traffic/config/scenario_vali1.json) | Complete configuration files |
| Planned and executed operations | [Fault plan](config/runtime/fault-plan.json), [scenario plan](report/scenario_one_plan.json), and [execution report](report/fault_timeline_execution.json) | Complete files |
| Recovery checks | [Checkpoint records](events/recovery_checkpoints.jsonl) | Complete checkpoint stream for this run |
| Metrics and events | [Metrics](metrics/) and [events](events/) | Native stream excerpts; checkpoint scope is listed above |
| Session association | [Session map](derived/session_map.jsonl) and [SMF log](nf/smf-gold-sessionmap.log) | Linked record excerpts |
| Base table | [1 s table](report/v3_timeseries.csv) | A contiguous interval around the first paired N3/silver-UE operation |
| Core24 data product | [5 s table](core24_candidate_5s.csv) | Twelve rows from a separate platform-side candidate |
| Packet-derived flows | [N3](derived/n3-gtpu-20260807_041929_flows.jsonl), [N4](derived/n4-pfcp-20260807_041929_flows.jsonl), [N6](derived/n6-uplink-20260807_041929_flows.jsonl), and [SBI](derived/sbi-http-20260807_041929_flows.jsonl) | Flow excerpts without raw packet payloads |
| Application transfers | [Transfer example](application_transfer_sample.json) | Sample transfer records |

The [provided-file catalog](../../manifests/PROVIDED_FILES.csv) lists the scope of each file. These examples are not a complete dataset and cannot reconstruct the full run. Full packet captures and other original data are listed in the [raw-file inventory](../../manifests/RAW_FILES.csv); download links are not currently provided. Anonymized network addresses must be replaced with local deployment settings before execution.

## Reading related records

Use `overlap_group=og_b01_p01_n3_block_silver` to relate the plan, execution report, and recovery checkpoints. Command identifiers additionally use `_core` or `_ran`. Row order is not a join key. The base-table `event_id` combines the exporter's label and interval rules, so it need not equal a raw `fault_id`.

The session map and SMF log show SUPI/PDU/DNN/UE-IP/UPF association at session-record granularity, distinct from the 1 s metrics. Unresolved values such as `selected_amf=null` remain unavailable. Initial resource observations may precede the first operation; use each record's timestamp.

The [Core24 field mapping](../../handoff/CORE24_SOURCE_MATCH.csv) describes the sources and conversions for the 5 s candidate. Its correspondence to the final AI inputs has not been established, and its rows are not a synchronized copy of the 1 s excerpt.

Packet-derived `first_seen` and `last_seen` strings without an offset require the original decoder's timezone context before alignment with UTC timestamps.
