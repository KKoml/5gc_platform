# Platform code guide

## Source classes

| Class | Included material | Role |
|---|---|---|
| Upstream open source | LICENSE and the SMF source snapshot | free5GC network functions and required attribution; the SMF files also contain targeted platform changes. |
| Configuration integration | tiered, k8s, multi-UPF and UE configs; compose/deployment files | two-UPF topology, routing and deployment layout. Values that identify the private lab are represented by generic configuration values where redaction was needed; fill site-specific values before runtime use. |
| Tool adaptation | cross-host scenario/traffic/UE scripts and tracer tool | execution timeline, UE binding, workload control and experiment result collection. |
| Platform additions | collectors, session association, metric derivation/export, recovery evidence and dataset checks | collection lifecycle, normalized event records, derived tables and data integrity checks. |

The source tree contains no Git history. It is a selected source snapshot, not a public repository. Private platform addresses were mapped consistently, account/home-directory strings were generalized, and inline configuration keys were replaced with explicit placeholders in the candidate copy. These changes are recorded with before/after hashes in the private audit area. Site-specific configuration must be restored in a deployment copy before runtime use.

## Static/offline checks

From platform/source_snapshot, the recorded checks run Python syntax compilation in memory and bash -n on shell scripts. Dataset reading and sample validation are offline. These checks do not start network functions.

## Runtime operations not executed

Commands such as ./run.sh -tiered --quiet, scripts/scenario_one_preset.sh run, scripts/fault_inject.sh and scripts/nf_recovery.sh can start services, schedule traffic, apply network changes or recover network functions. They require a configured lab and are not part of this package validation.

## External services

No reviewer-accessible external endpoint was verified. External URL strings present in upstream references/comments remain unverified references, not access routes. Host-specific configuration and raw run directories are not supplied as URLs. Change generic values in a private deployment copy before running.
