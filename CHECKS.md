# Review checks

## W1 dictionary screening, 2026-10-26

The current [W1 dictionary](manuscript_supplement/data/field_dictionary.csv) has 277 retained definitions. The [complete screening crosswalk](platform_data/dictionaries/W1_FIELD_SCREENING_400.csv) accounts for all 400 legacy IDs, and the [guide](platform_data/dictionaries/W1_DICTIONARY_GUIDE.md) distinguishes observations, context, offline products and unsupported historical columns. Full W1 base-table scans confirmed 611,777 rows, 81 columns and zero differences against the 567 published field-coverage records.

```bash
python tools/build_w1_dictionary.py --check
```

This check rebuilds dictionary metadata from sanitized evidence and compares the published outputs. It preserves the original 81-column data, coverage reports, task inputs, models and saved results. No collection or model execution forms part of the dictionary update.

## Earlier review receipts

The existing [handoff checks](checks/current/appendix_review_handoff.json), [review validation](checks/current/appendix_review_validation.json), [data-schema checks](checks/current/data_schema_verification.json), inventories and model/result receipts describe their recorded earlier versions. Their 400/215 counts refer to the archived platform catalog; they are not validation receipts for the new W1 dictionary. They have not been rewritten to match the new count. Historical-paper execution identity remains separate. See [publication status](PUBLICATION_STATUS.md) for access scope and remaining limits.
