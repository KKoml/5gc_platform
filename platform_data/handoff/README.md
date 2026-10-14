# Core-to-experiment handoff

The authoritative final contributed materials are now in this same repository:

- [Prediction handoff](../../manifests/prediction_handoff.csv): uncompressed source hashes, provided gzip hashes, anonymization/conversion rules and versions.
- [Core handoff](../../manifests/core_handoff.csv): source/provided hashes, transformations and identity boundaries.
- [Final prediction input manifest](../../prediction_inputs/INPUT_MANIFEST.json) and [24-feature configuration](../../data_machine/dataset/task_data/metadata/feature_sets.json).
- [Current checks](../../checks/current/appendix_review_handoff.json) independently recompute provided-file hashes and match the 24 feature names.
- [Canonical task/evaluation appendices](../../manuscript_supplement/README.md) give actual split IDs, model parameters and seeds.

`CORE24_SOURCE_MATCH.csv` documents the source-stream/entity/unit mapping. Candidate and later Core-repair records remain labeled as such: feature-name agreement is not proof of exact historical experiment identity, and 5 s observations/prediction histories are not direct selections or resampling of the old 81-column table. `EXPERIMENT_MACHINE_MANIFEST_TEMPLATE.csv` is a contract for future lineage extensions, not a claim that current materials are absent.

Private Google Drive backup contains full seven non-PCAP runs and the retrieved current corpus. `CLOUD_DATA_INDEX.csv` distinguishes completed private backup from unverified anonymous delivery. No private links or identity mapping are published here.
