# 5GC platform and data: Core-machine review materials

This branch provides the English platform/data appendices and checked publication copies accompanying the supplied manuscript. Start with the [appendix index](appendices/INDEX.md).

- [Platform implementation and deployment](appendices/APPENDIX_A.md), including [development correspondence](tables/PLATFORM_DEVELOPMENT_MAP.csv).
- [Configuration and execution control](appendices/APPENDIX_B.md), with saved plans, actual operations and recovery evidence.
- [Data formats, dictionary and coverage](appendices/APPENDIX_C.md); 400 dictionary definitions, 81 base columns, body metric scope and 24-variable candidates are explicitly distinguished.
- [Association/alignment/construction](appendices/APPENDIX_D.md), source/version/output lineage and separate prediction-repair provenance.
- [Real W1-D06 examples](samples/W1-D06/README.md), [provided-file manifest](manifests/PROVIDED_FILES.csv), [raw inventory](manifests/RAW_FILES.csv) and [handoff](handoff/README.md).
- [License and attribution](licenses/NOTICE.md), [release checks](CHECK_RESULTS.md) and [remaining items](OPEN_ITEMS.md).

The acquisition implementation is pinned to the historical W1 collection commit; source files are selected complete files with documented identity redaction and per-file before/after hashes. Examples preserve observed values and timestamps. No network experiment, fault injection, new collection, model training or manuscript-body edit was performed for this release.

## Delivery scope

**Complete files provided:** selected platform source/modules, saved sample-run configuration and evidence reports, field/source tables and publication manifests. **Samples provided:** bounded original observed records and base/Core24 excerpts. **Manifest only:** full original runs, packet captures and large logs. Cloud storage will be supplied by the data owner; no download availability is claimed until its links are verified. Model code, final input manifests, training settings and results will be uploaded separately by the experiment machine.

## Offline verification

Run `python3 processing/verify_release.py` from this repository. It verifies publication hashes, JSON/CSV shape, source syntax and anonymous sample linkage. The verification script does not start services or change laboratory state. Full data reconstruction additionally needs the manifest-listed off-site raw files and documented external dependencies. Runtime launch scripts under `platform/source/` are reference implementations and require a configured private deployment.

The manuscript's anonymous-review route is a separate reader entrance, not a Git remote. This branch upload does not by itself establish that an anonymous mirror tracks this branch or serves these files. See `OPEN_ITEMS.md` and the external checks before claiming reviewer access.
