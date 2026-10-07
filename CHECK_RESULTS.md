# Release check results

The Core-side publication passed all 22 read-only local checks. Validation parsed Python without importing platform programs, parsed Go without running services, and checked shell syntax without execution. No live-network validation, collection, fault operation or model training was performed.

- Payload manifest: 471 files with matching SHA-256; 395 selected source files and 33 declared original-data/configuration/report provisions.
- Base-table audit: seven existing tables, 611,777 rows, 81 columns each; no 1 s grid gaps; per-field recomputation matches recorded coverage within rounding.
- W1-D06 sample: 440 contiguous original 1 s rows; complete 144-entry paired plan, 288 successful start/end command results and 72 accepted checkpoints with matching run/group identities.
- 400 dictionary definitions / 215 metric roles verified; 32-metric mapping remains a disclosed candidate; Core24 has 24 explicit candidate names with final model-input binding pending.
- Seven saved runtime script snapshots match the pinned collection source byte for byte.
- Static Python/Go/shell, JSON/JSONL, CSV width, relative Markdown links, file sizes, source/publication hashes, known site identifiers, private-key/token patterns and subscriber secret checks passed.
- Original source/sample-source hashes were rechecked on the data machine; no changes found. The frozen source checkout is clean. Private mapping and source-protection audit records remain outside this repository.
- 59,773 raw files inventoried across seven runs, totaling 185.786 GiB; 26,773 files have no available/recomputed individual digest and are explicitly marked. No full multi-run large-PCAP rehash or raw-data upload was performed.

`SHA256SUMS.txt` covers the publication payload. The checksum file and validation/check reports are excluded from that list to avoid circular report/hash dependencies; Git commit identity covers the complete repository tree. `LOCAL_VALIDATION.json` gives individual local verdicts.

External state: cloud raw-data upload and final experiment-machine materials are pending their owners. Public Git retrieval and anonymous-mirror checks are recorded separately after pushing. Uploading this branch does not establish anonymous mirror tracking or full raw/model availability.

## Checks after upload

- The published payload commit is `782711568257e8e8d13ee8118b6e74ac6d5ad90a`; the remote branch head matched the local commit. An unauthenticated HTTPS Git read returned the same branch commit.
- Unauthenticated raw-GitHub retrieval returned HTTP 200 for the appendix index, 81-column dictionary, W1-D06 base-table example and SHA-256 list. Every downloaded byte stream matched its local publication copy.
- The anonymous review page (`5gc_platform-1FEA`) returned HTTP 200 when fetched with an explicit client identifier, but another automated request returned HTTP 403; the static page alone does not establish access to appendix/data files or tracking of this branch. Anonymous artifact retrieval remains **unverified**.
- A GitHub API request was rate-limited (HTTP 403). Public-file availability was checked through direct unauthenticated Git/raw retrieval instead.
- The default `main` branch was not overwritten or merged by this task. These materials are on the named `codex/` branch; anonymous mirror/default-branch integration requires a separate repository/mirror arrangement.

These checks establish delivery of the small Core-side publication, not cloud raw-data, final model-input identity or anonymous-mirror availability.
