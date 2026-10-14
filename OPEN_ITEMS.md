# Remaining evidence and delivery items

| Item | Present status | Required completion |
| --- | --- | --- |
| Cloud raw data | Inventoried; full raw files not included in Git | Owner uploads and provides URLs, anonymous-access policy and complete retrieval checksums. |
| Raw-file hashes not in historical transfer inventories | Explicit blanks with status in RAW_FILES.csv | Data owner computes missing digests before cloud delivery; no full multi-run PCAP rehash was performed during live-platform work. |
| Prepared AI inputs and labels | Uploaded on main: 518 data files and 489 input-contract entries | No repeat upload is needed. Consult main DATA_ACCESS.md and its manifests; unresolved raw-to-input lineage remains separate. |
| Prediction input lineage | Prepared prediction inputs and their contracts are uploaded on main; correspondence to this branch's Core-side repaired-view example remains unverified | Match source and processing hashes, cutoffs, and target windows; do not treat upload as proof of that relationship. |
| Historical 32-metric named scope | Historical candidate correspondence only; the current English manuscript no longer uses this subset count | Preserve the unresolved historical note. Do not change field roles or reintroduce the count to fit an older manuscript. |
| Historical 400-entry dictionary identity | Current count verified; historical version identity unverified | Match paper dictionary version/hash; optional later entries are not W1 runtime evidence. |
| Historical package/kernel/runtime versions | Source/image provenance available, some package versions absent | Original version records for K3s, OS/kernel, gtp5g, capture/decoder, Python and database/runtime where needed. |
| Current Figures 1–3 and editable sources | Current paper includes the physical photograph as Figure 3; latest image/PPT source files are not included in these branches | Optional separate artifact delivery; do not describe the paper's Figure 3 as a placeholder. |
| Anonymous mirror | Reachability and branch tracking not established | Configure mirror to the approved branch/default route and retrieve the appendix and a hashed sample through it. |
| Full runtime reproduction | Selected source/reference files and external-dependency citations provided | Restore omitted dependencies, site config and secrets in a private deployment; validate separately. |

Status synchronized with main on 2026-10-14. Core-side tables and appendices are delivered despite the remaining boundaries; prepared AI inputs already on main are not listed as missing raw records.
