# Dictionary scope

- [PLATFORM_FIELDS.csv](PLATFORM_FIELDS.csv): 400 cross-file definitions, 215 metric roles and 185 other roles. This is not a table with 400 simultaneously observed variables; historical-version identity remains separately documented.
- [BASE_TABLE_81.csv](BASE_TABLE_81.csv): 81 columns in the existing 1 s base product, including identifiers, state, time and quality fields. There are 611,777 rows across seven runs; availability is in FIELD_COVERAGE.csv.
- The 24-variable 5 s Core observations are a separate raw-stream-derived product. [Core-side source matching](../handoff/CORE24_SOURCE_MATCH.csv) is a source-stream mapping whose names/order match the provided final configurations; historical execution identity remains separate.
- The contributed prediction input has its own exact 18-variable XGBoost scope and cutoff/target contract; it is not certified as direct base-table selection or resampling.
- The earlier provisional 32-item subset is absent from this manuscript and from the current review index. No definition was changed to fit a count.

Units and source availability override misleading names: host-interface `rx_bps`/`tx_bps` are byte/s in the frozen collector; task bitrates require explicit conversion. Preserve missingness and provenance. Original caveats are in [source dictionary evidence](../evidence/PLATFORM_DICTIONARY_SOURCE.csv).
