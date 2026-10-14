# Appendix Navigation

The current six-page English manuscript cites **Supplementary Appendices C and D** for task construction and evaluation settings. Its appendix numbering refers to [the manuscript supplement](manuscript_supplement/README.md), not the separate platform-branch numbering.

| Current supplementary appendix | Contents | Detail entry |
| --- | --- | --- |
| A | Platform implementation, configuration, and recovery | [A.1–A.5](manuscript_supplement/README.md#appendix-a-platform-implementation-and-configuration) |
| B | Data organization, field definitions, and examples | [B.1–B.4](manuscript_supplement/README.md#appendix-b-data-organization-fields-and-examples) |
| C | Task inputs, preprocessing, windows, and splits | [C.1–C.3](manuscript_supplement/README.md#appendix-c-task-construction), with [detailed construction](appendix/D3_data_construction.md) |
| D | Model settings, hyperparameters, results, and reproduction | [D.1–D.3](manuscript_supplement/README.md#appendix-d-evaluation-settings-and-results), with [model details](appendix/E1_models_hyperparameters.md), [results](appendix/E2_results_correspondence.md), and [reproduction instructions](appendix/E3_reproduction.md) |

The detailed files retain their earlier D.3/E.1–E.3 headings for continuity. Detailed D.3 means task construction; manuscript-supplement D.3 means results and reproduction. The file path identifies which series is intended. There is no D.4 in the current English manuscript supplement.

## Expanded platform material

Select branch `codex/platform-data-appendices-20261007` in the repository branch menu, then open `readme.md` or `appendices/INDEX.md`.

| Platform-branch heading | Subject | Related current manuscript supplement |
| --- | --- | --- |
| A | Implementation and deployment | A |
| B | Configuration, operations, and recovery | A |
| C | Data organization, dictionaries, and examples | B |
| D.1–D.2 | Association, alignment, and processing | A.5 and C |

That branch also contains `samples/W1-D06/`, selected `platform/source/`, and raw-file inventories. These are expanded documentation and examples; they are not a complete raw-data archive. Return to `main` for the prepared AI datasets, input manifests, models, and evaluation code listed in [Data Access](DATA_ACCESS.md).

## Current paper displays

Figures 1–3 show architecture, deployment, and the physical testbed. Table I lists collected data; Tables II–V report prediction, detection, classification/localization, and imputation. Algorithm 1 describes collection. The experiment setup is Section III-B, rather than a separate Table II. [The result map](PAPER_RESULT_MAP.md) provides current labels and links to the existing outputs. Earlier detection/classification plots remain supplementary artifacts.

[The English manuscript fingerprint](manifests/english_manuscript.json) identifies this mapping. It does not replace the historical experiment provenance. Anonymous access to both branches must be checked separately; see [availability](PUBLICATION_STATUS.md).
