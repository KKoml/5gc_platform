<h1 align="center">D-GATE</h1>

<p align="center">
  <strong>Operational Data Collection and AI Algorithm Performance<br>Validation Benchmark Platform for Core Network</strong><br>
  <sub>Paper appendix materials · Anonymous review</sub>
</p>

<p align="center">
  <a href="https://drive.google.com/drive/folders/1cQTv0CbireblU9055l0rPhgnDDDSwLyJ"><strong>Original data download</strong></a> ·
  <a href="manuscript_supplement/README.md">Appendices A–D</a> ·
  <a href="DATA_ACCESS.md">Datasets</a> ·
  <a href="PAPER_RESULT_MAP.md">Paper results</a> ·
  <a href="RUN_GUIDE.md">Reproduction</a>
</p>

> [!IMPORTANT]
> **[Download original experiment data — Google Drive](https://drive.google.com/drive/folders/1cQTv0CbireblU9055l0rPhgnDDDSwLyJ)**
>
> Public read-only access to the W1-D01–W1-D07 original non-PCAP records, derived data, and reports.
> **[Seven-run archives](https://drive.google.com/drive/folders/18-NN0UprWCM-R42Ng0YITkkxZnrGWN14) · [Download and restore instructions](https://drive.google.com/file/d/15TNAxdYwus_3pCS2KRWLzte3bO69S5WQ/view) · [Package index and checksums](https://drive.google.com/drive/folders/1ltfF2pHkPVJ3OV1Eb0Iml3Ir3Bicwaub)**
> PCAP/PCAPNG captures are excluded.

![D-GATE overview: controlled traffic and interventions in a 5G experimental network, multi-source collection and processing, and prepared inputs for four offline AI evaluation tasks.](assets/readme-overview.png)

*Overview adapted from Fig. 1 of the paper, with the four evaluation tasks added. Collection capabilities and released materials are distinguished below.*

The materials include platform descriptions, linked run examples, prepared datasets, evaluation code, model settings, and saved results.

D-GATE combines configurable traffic, network interventions, recovery checks, and multi-source observations in a 5G core testbed.

## Read the supplementary appendices

The supplement follows the paper’s **single A–D series**. Start with the section relevant to your review; expanded platform evidence is available in the same repository.

| Appendix | What it explains | Start reading |
| :--- | :--- | :--- |
| **A · Platform** | Implementation, deployment, traffic, interventions, and recovery | [Platform and configuration](manuscript_supplement/README.md#appendix-a-platform-implementation-and-configuration) |
| **B · Data** | Data products, field definitions, units, coverage, and examples | [Data organization and examples](manuscript_supplement/README.md#appendix-b-data-organization-fields-and-examples) |
| **C · Task construction** | Task-specific inputs, preprocessing, windows, and data splits | [Task construction](manuscript_supplement/README.md#appendix-c-task-construction) |
| **D · Evaluation** | Models, hyperparameters, seeds, results, and reproduction | [Evaluation settings and results](manuscript_supplement/README.md#appendix-d-evaluation-settings-and-results) |

[Detailed navigation](APPENDIX_NAVIGATION.md) · [Platform evidence index](platform_data/details/INDEX.md) · [Configuration and operation tables](platform_data/tables/README.md)

## Explore the data

The release includes **D01–D07** platform exports and prepared task inputs. The **W1-specific field dictionary contains 277 evidence-supported definitions** across observations and contextual records; this is not a count of independent numerical features. Each existing 1 s exported table retains **81 columns**. [Screening rules](platform_data/dictionaries/W1_DICTIONARY_GUIDE.md) and the [complete 400-entry crosswalk](platform_data/dictionaries/W1_FIELD_SCREENING_400.csv) explain retained, merged, excluded and unverified definitions.

| To inspect… | Open… |
| :--- | :--- |
| Original experiment records, derived data, and reports | **[Download W1-D01–W1-D07 archives](https://drive.google.com/drive/folders/18-NN0UprWCM-R42Ng0YITkkxZnrGWN14)** · [Archive index and checksums](https://drive.google.com/drive/folders/1ltfF2pHkPVJ3OV1Eb0Iml3Ir3Bicwaub) |
| Table formats and field meanings | [1 s sample](manuscript_supplement/data/timeseries_1s_sample.csv) · [5 s sample](manuscript_supplement/data/core_features_5s_sample.csv) · [Field dictionary](manuscript_supplement/data/field_dictionary.csv) |
| One run’s configuration, events, and recovery records | [Linked D06 examples](platform_data/samples/W1-D06/README.md) |
| Included exports and task inputs | [Platform exports and task data](data_machine/README.md) · [Prediction histories and targets](prediction_inputs/README.md) |
| Windows, indices, masks, and preprocessing scales | [Data access and file locations](DATA_ACCESS.md) |

The 1 s exports, 5 s observations, and prediction tables are separate products. Their construction and documented relationships are described in [Appendix C](manuscript_supplement/README.md#appendix-c-task-construction) and the [lineage record](appendix/LINEAGE.md).

To restore an original-data package, download every part listed for that package in `00_Readme_And_Manifests/DRIVE_PACKAGE_INDEX.json`. Large archives use ordered 90 MiB chunks. Follow the [archive instructions](https://drive.google.com/file/d/15TNAxdYwus_3pCS2KRWLzte3bO69S5WQ/view) to verify SHA-256 checksums and restore into a new empty directory; the supplied `restore_package.py` helper requires Python 3.12 or newer.

## Inspect the four evaluation tasks

| Task | Evaluation setting | Paper result | Code and settings |
| :--- | :--- | :---: | :--- |
| **Performance prediction** | Future network and host metrics from historical observations | Table II | [Prediction](evaluation_package/evaluation/prediction/README.md) |
| **Fault detection** | Offline evaluation of fault detection from collected observations | Table III | [Detection](evaluation_package/evaluation/detection/README.md) |
| **Fault classification** | Known injection start; 12 classes encoding fault type and associated target | Table IV | [Classification](evaluation_package/evaluation/localization/README.md) |
| **Metric imputation** | Reconstruction under fixed artificial missingness patterns | Table V | [Imputation](evaluation_package/evaluation/imputation/README.md) |

D01–D04 are used for training and D05 for selection or calibration; D06/D07 are post-hoc test runs. See the [paper result map](PAPER_RESULT_MAP.md) for supporting files and the [model settings](appendix/E1_models_hyperparameters.md) for task-specific details.

## Recompute, replay, or train

**Quick check — saved prediction and imputation tables.** From the downloaded repository root, run with Python 3:

```bash
python evaluation_package/evaluation/verify_paper_tables.py
```

This checks **9 prediction means and 60 imputation values** against the stored table values to three decimal places. It uses the Python standard library and runs no model inference or training.

For further checks, choose the corresponding workflow in the [run guide](RUN_GUIDE.md):

| Workflow | What it does |
| :--- | :--- |
| **Saved-result recomputation** | Recalculates aggregates or metrics from saved outputs |
| **Checkpoint replay** | Runs inference with supplied models and compares outputs |
| **Fresh training** | Fits new models in a separate run directory |

Dependencies, commands, and task-specific requirements are listed in the [reproduction instructions](appendix/E3_reproduction.md). Fresh runs are separate executions and do not replace the paper’s saved results.

## Release scope

**Included:** appendices, field dictionaries, configurations and linked samples, prepared task inputs, evaluation and offline task-data code, fitted models, and saved outputs.

**External original-data archive:** the [public Google Drive folder](https://drive.google.com/drive/folders/1cQTv0CbireblU9055l0rPhgnDDDSwLyJ) contains the seven-run non-PCAP records, derived products and reports, the current traffic-input corpus, and a separate review package. These archives are downloaded separately from this repository. Third-party traffic-corpus redistribution rights and exact historical W1 input identity remain unverified.

**Outside this repository:** collection-platform source code and PCAP files. Platform implementation paths and hashes are documentary references; platform source is reserved for release upon acceptance. Historical source archives and transfer-test files are retained separately in private storage.

[Data availability](DATA_ACCESS.md) · [Detailed delivery scope](platform_data/DELIVERY_STATUS.md) · [Validation records](CHECKS.md) · [Anonymous access status](PUBLICATION_STATUS.md)

All repository documentation and report text is provided in English. Legacy `_ZH` report filenames are retained for compatibility. See the [English revision record](manifests/english_documentation_revision.json) for translation scope and preserved historical hashes.
