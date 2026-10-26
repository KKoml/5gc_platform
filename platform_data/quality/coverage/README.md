# W1 export availability and source-evidence envelopes

`SUMMARY.csv` gives all seven runs; `SUMMARY.json` gives aggregate counts and limits. The input is the existing [567-row field coverage table](../../tables/FIELD_COVERAGE.csv), whose nonempty-cell counts were checked against all seven retained 81-column exports, plus `source_envelopes.json`, a sanitized count/timestamp projection of the retained raw-source inventory. No UE identifiers, site addresses or private run paths are included.

```bash
python3 tools/summarize_w1_export_quality.py --check
```

Run from the repository root. The command recalculates the availability summary from those published metadata inputs and compares deterministic text outputs; it does not rescan the complete exported tables or the original raw logs. Source evidence can be inspected in the separately distributed original-data packages.

Each run has 64 ever-nonempty columns and 17 wholly empty columns. The producer's coverage statuses are retained separately: 58 `ok`, 19 `capability_missing`, 3 `snapshot_only`, and 1 `replaced` per run. A producer status is not an independent accuracy check, and `ok` does not imply every cell is nonempty. Five source-age columns contain no values in any run, so their names cannot establish source freshness.

The envelope between first and last retained UE events spans 984.074–4,604.590 seconds per run. This describes the timestamps of observed events, **not** a continuous coverage interval, log-file completeness or a full-day per-UE state series. The separate RAN log-KPI and workload row counts make the distinction visible. Workload Ready counts do not establish successful registration, active sessions or actual business activity. Missing/unavailable observations remain missing; no zeros or forward-filled event evidence are introduced by this audit.
