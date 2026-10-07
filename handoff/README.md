# Core-to-experiment-machine handoff

The Core machine supplies acquisition/execution evidence, source and dictionary contracts, source-table checks and published examples. The experiment machine supplies the authoritative final task inputs, builders, model settings and evaluation artifacts. Keep the two responsibilities separate.

1. Fill `EXPERIMENT_MACHINE_MANIFEST_TEMPLATE.csv` for every final input/label/mask/index file. Use anonymous W1-D01..W1-D07 run IDs, relative paths, SHA-256, source time/grid range, field names, producer version and ordered transformations. Record source hashes and split identity.
2. Match source hashes against `manifests/PROVIDED_FILES.csv`, `tables/RUN_LEDGER.csv` and `manifests/RAW_FILES.csv`. Recorded transfer hashes require separate retrieval-time verification; blank hashes require the data owner to supply them. A slot label or row count alone is not a version match.
3. Match Core24 names against `CORE24_SOURCE_MATCH.csv` and record the actual builder's binning, as-of tolerance, masks, readiness formula, byte/bit conversions and reset policy. CPU percentages, millicores and host resource scopes are not interchangeable.
4. Match prediction inputs against `CORE_SIDE_REPAIRED_VIEW_MANIFEST.json` and `REPAIR_PROGRAM_PROVENANCE.json` if used, or declare a different builder. Retain source cutoff versus target window; do not claim direct old-base selection when prefix reconstruction was used.
5. Verify task windows never cross run/gap boundaries, masks preserve unavailable observations, training-only normalization is documented, and final published file hashes match actual experiment files. These checks do not rerun models.

`CLOUD_DATA_INDEX.csv` reserves raw-data links for the owner. It currently marks all full raw material `manifest_only` and cloud access `pending`. The complete original runs have not been uploaded by this task. Model code/settings/results are reserved under `experiment-machine/`, pending that machine's separate upload. Private original-ID/site mappings and local machine paths are excluded from Git.
