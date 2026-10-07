# Real W1-D06 examples

This directory uses one accepted historical run. Operation/session/tier identifiers and original observation times are preserved. Site addresses, usernames, hostnames and simulated subscriber identifiers are anonymized consistently across files. Documentation-network addresses require local configuration before any execution.

`manifests/PROVIDED_FILES.csv` is authoritative for complete files versus samples and their source/published hashes. Configurations, gates and the execution report are complete anonymized files. Native metric/event/session excerpts are bounded samples; the base-table CSV contains a contiguous interval around the first paired N3/silver-UE operation. The SMF text excerpt exposes the implementation fields actually emitted. The recovery-checkpoint stream is complete for this run. These excerpts do not reproduce all original observations or permit a full offline rebuild without off-site source files.

Join the plan, actual execution report and checkpoint on `overlap_group=og_b01_p01_n3_block_silver` (the command identity has `_core` or `_ran`). Do not join arbitrary rows by their order. The base-table `event_id` uses the exporter's combined label/interval contract, so it is not universally equal to a raw `fault_id`.

The session-map/log example shows a different record granularity from 1 s metrics and supports anonymous SUPI/PDU/DNN/UE-IP/UPF association. Null selected AMF remains null. The initial resource records can precede the first fault; use their own timestamps.

`core24_candidate_5s.csv` is twelve rows from an existing later Core-side candidate. Its manifest and semantic source mapping live under `handoff/`; identity with the experiment machine's final tensors is unverified. It must not be treated as a synchronized copy of the base-table excerpt.

Four packet-derived flow excerpts (N3/N4/N6/SBI) are copied from existing outputs without new decoding. They do not include raw payloads; original no-offset first/last-seen strings need their decoder timezone context for UTC alignment. Full packet captures remain manifest-only.
