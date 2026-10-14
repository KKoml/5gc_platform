# Platform implementation detail. Platform implementation and deployment

This appendix documents the Core/data-machine contribution against the supplied manuscript (`manifests/BUILD_CONTEXT.json` records its SHA-256). The collection implementation is pinned to `dffa0226d406235017f26a28c50ec59a304840ff`. It does not include model architecture, training hyperparameters, model weights or evaluation results produced by the separate experiment machine. Later UE ownership interfaces, new per-UE 1 s collectors and business prevalidation are not evidence for the historical W1 collection.

## A.1 Software and version evidence

| Component | Version or identifying evidence | Boundary |
| --- | --- | --- |
| Core network | free5GC v4.1.0 as reported by the manuscript; pinned collection source above | `samples/W1-D06/report/provenance_report.json` records the collection revision, clean-source status and per-component image digests. A source commit is distinct from a container image digest. |
| Access simulator | UERANSIM v3.2.7 as reported by the manuscript | The sample provenance retains the two collected access-image digests; the upstream simulator source is not mirrored here. |
| Core orchestration | K3s/Kubernetes, Core physical host plus VM worker | Exact historical K3s package version is not established by the available run provenance. Do not substitute today's installed version. |
| Access orchestration | Separate K3s runtime on the gNB/UE physical host | Host-side orchestration and in-pod client execution are separate roles. |
| Packet capture/decoding | Capture tools and tshark invoked by the archived scripts | Historical executable versions are not recorded in the provided version evidence; list them as unknown. |
| Traffic generator | `trace_play_scenario_v11.py`, pinned file hash in `manifests/IMPLEMENTATION_REFERENCES.csv` | Real newly generated transport bytes follow trace timing/size. This is not original-content replay. |
| Go build declaration | `go 1.24` in the pinned SMF module and `golang:1.24` Dockerfile | Build specification, not independent evidence of the historical binary toolchain. |
| Offline processing | Pinned per-program SHA-256; later repair program has its own source hash | The collection commit, current dictionary and later task builders have separate versions. |
| gtp5g and container/database runtime | Dependencies of UPF/K3s/MongoDB images | Historical kernel/module/package versions are not confirmed. Image digests are provided where recorded. |

No historical version is inferred from a current workstation command. Only version/hash references are provided; platform source and build/dependency files are withheld until acceptance, as stated in the latest manuscript. [License and attribution scope](../licenses/NOTICE.md) explains the selected snapshot and omitted upstream components.

## A.2 Physical machines, VM and workloads

The collection deployment has three physical host roles: a Core/data host, an access host and a DN traffic host. A Core VM is a worker on the Core physical host; it is not a fourth physical machine. The paper reports Core allocatable resources of 8 threads / 62.45 GiB and VM resources of 2 vCPUs / 5.79 GiB, access hardware of 32 threads / 128 GiB and traffic hardware of 20 threads / 64 GiB. Allocatable host and VM memory must not be summed as independent physical capacity. Hardware figures are manuscript values; this package does not claim a fresh historical hardware measurement.

The saved W1 topology places `amf-a`, `smf-silver` and `upf-silver` on Core-A and `amf-b`, `smf-gold` and `upf-gold` on Core-B. NRF, NSSF, UDM, UDR, AUSF, PCF and MongoDB reside on Core-A. This is nine NF types and twelve NF instances, plus MongoDB (thirteen deployment entries). The manuscript identifies Core-B as the VM; the topology itself proves two worker roles, not the virtualization technology.

AMF and UPF have `host_network=true`; SMF and the other saved NF/database workloads do not. UPF requires the host gtp5g interface. The access host runs UERANSIM workloads and UE-side traffic clients, while the DN server runs on the traffic host. The orchestration, major collectors, transfer verification and offline processing run as host-side tools. The entire platform must not be described as a single containerized application.

The initial access population is four gNBs and forty simulated UEs, divided into two DNN groups of twenty. Only one UE per DNN is selected to generate application traffic. `internet-silver` uses the `10.60.0.0/16` address pool and `internet-gold` the `10.61.0.0/16` pool; the selected configuration must establish this mapping. These DNN/UPF groups do not on their own establish fully independent network slices.

N2 joins gNB to AMF; N11 denotes AMF-SMF control; N4 joins SMF to UPF; N3 carries UE traffic from gNB to UPF; N6 joins UPF to the shared DN application server. The figure's logical path is distinct from physical placement. The same DN server is used by both groups.

Addresses in the publication copy are consistently mapped to documentation networks (for example Core-A `192.0.2.30`, Core-B `.31`, access `.40`, DN `.20`, and gNB `.140`–`.143). They are anonymized example addresses, not executable site configuration. Timestamps, measurement values, operation identities and tier semantics are retained. Private mapping records stay outside the Git repository.

## A.3 Development correspondence

The six-column [development correspondence table](../tables/PLATFORM_DEVELOPMENT_MAP.csv) specifies module, open-source basis, addition/adaptation, problem, inputs/outputs and exact implementation path. Open-source network protocols, Linux packet impairment and packet-capture facilities are distinguished from the platform's experiment lifecycle and data engineering. Implementation locations refer to the audited private platform checkout; no corresponding platform source files are distributed in this review directory. Figure 1 numbers the workflow as (1) business generation, (2) experiment control, (3) multi-source collection, (4) retrieval/verification/archiving and (5) data processing.

The SMF extension, not expanded in Figure 1, writes the `SessionMap PDU session context` record at establishment and modification. It includes stage, SUPI, PDU session ID, DNN, UE IP, UPF identity/PFCP address, uplink/downlink/local TEIDs and RAN address/downlink TEID. [Real log excerpts](../samples/W1-D06/nf/smf-gold-sessionmap.log) and [associated records](../samples/W1-D06/derived/session_map.jsonl) demonstrate the source and parser output with consistent anonymous identifiers. The parser does not create identity merely from a row number or IP address.

Repeated-session cleanup and PFCP response matching are stability adaptations. AMF, NRF, PCF and UPF guards support repeated experiments. Their presence in the pinned source does not prove every optional branch was exercised in every run, and does not establish seamless migration, state replication or a new 5G protocol. Static-IP mapping and UPF hash-size options are implementation capabilities, not automatically enabled W1 features.

## A.4 Evidence tiers and omitted material

Source existence, configured enablement, observed execution and formal run acceptance are separate facts. The run ledger identifies accepted members; the saved execution report/checkpoints establish what ran. Later model acceptance and external reviewer access have separate checks. The latest PDF contains architecture, deployment and physical-testbed figures. Existing figure artifacts are retained under the repository’s `paper_figures/`; this reorganization does not upload the author-bearing original PDF or invent a new photograph.
