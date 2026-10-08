# Local completion report

Status: local candidate, not externally published; no verified reviewer URL.

Added seven existing full platform time-series exports (D01-D07), totaling 611777 rows, with 81 columns on a continuous 1 s grid within each slot. Added seven source coverage reports, an index, and the current 400-entry platform dictionary (215 metrics). All source CSV cells were compared after the documented identity/address substitutions; numeric values and missing values were preserved. Source hashes and private mappings remain outside this package.

Each slot's source coverage summary is: 58 ok, 19 capability_missing, 1 replaced, 3 snapshot_only, 0 export_bug. This is coverage metadata, not a claim that all columns have physical observations or that the exports are causally safe for forecasting. Model input tables, labels, indices and masks remain unchanged. A duplicate imputation run-map's unused `original_raw_path` column was removed from this reviewer copy to eliminate source-host paths; its package hash manifests were refreshed.

The package-level manifests cover all payload files; SHA256SUMS.txt additionally covers the three manifest files. Run `sha256sum -c SHA256SUMS.txt` from the extracted package root. For a small reader check run `python3 dataset/samples/read_sample.py`.

Remaining blockers:
- Configure an anonymous reviewer-accessible location, then verify access without author credentials.
- Confirm that the current dictionary and added platform exports correspond to the historical paper materials; matching counts alone do not prove that identity.
- Verify historical evaluation-run provenance on the separate Evaluation machine. That package is unavailable on this machine.

D06-D07 remain previously accessed post-hoc evaluation. No model training, model replay, collection, or external upload was performed. Raw PCAP and private audit material are excluded.
