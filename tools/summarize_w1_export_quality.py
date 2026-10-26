#!/usr/bin/env python3
"""Summarize retained W1 export availability, not model quality or freshness."""
import argparse
import csv
import datetime as dt
import io
import json
from collections import Counter
from pathlib import Path


def build(root):
    quality = root / 'platform_data/quality/coverage'
    with (root / 'platform_data/tables/FIELD_COVERAGE.csv').open(encoding='utf-8-sig', newline='') as handle:
        coverage = list(csv.DictReader(handle))
    envelopes = json.loads((quality / 'source_envelopes.json').read_text())
    by_run = {}
    for item in coverage:
        by_run.setdefault(item['run_id'], []).append(item)
    assert len(by_run) == 7 and len(coverage) == 567
    rows = []
    for item in envelopes:
        fields = by_run[item['run_id']]
        counts = Counter(field['status'] for field in fields)
        row_counts = {int(field['rows']) for field in fields}
        assert len(fields) == 81 and len(row_counts) == 1
        source_age = [field for field in fields if field['field'].startswith('source_age_')]
        assert len(source_age) == 5
        first = dt.datetime.fromisoformat(item['ue_event_first_timestamp'])
        last = dt.datetime.fromisoformat(item['ue_event_last_timestamp'])
        rows.append({
            'run_id': item['run_id'],
            'export_rows': row_counts.pop(),
            'export_columns': len(fields),
            'ever_nonempty_columns': sum(int(field['present']) > 0 for field in fields),
            'entirely_empty_columns': sum(int(field['present']) == 0 for field in fields),
            'producer_ok_columns': counts['ok'],
            'producer_missing_columns': counts['capability_missing'],
            'producer_snapshot_columns': counts['snapshot_only'],
            'producer_replaced_columns': counts['replaced'],
            'source_age_columns': len(source_age),
            'source_age_nonempty_cells': sum(int(field['present']) for field in source_age),
            'retained_ue_event_rows': item['ue_event_rows'],
            'retained_ue_event_unique_supi_count': item['ue_event_unique_supi_count'],
            'ue_event_first_timestamp': item['ue_event_first_timestamp'],
            'ue_event_last_timestamp': item['ue_event_last_timestamp'],
            'ue_event_timestamp_envelope_seconds': round((last-first).total_seconds(), 6),
            'ran_log_kpi_rows': item['ran_log_kpi_rows'],
            'ran_workload_rows': item['ran_workload_rows'],
        })
    rows.sort(key=lambda row: row['run_id'])
    assert sum(row['export_rows'] for row in rows) == 611777
    assert all(row['ever_nonempty_columns'] == 64 and row['entirely_empty_columns'] == 17 for row in rows)
    assert all(row['source_age_nonempty_cells'] == 0 for row in rows)
    summary = {
        'scope': 'seven accepted W1 runs; retained export and source-evidence availability',
        'runs': len(rows), 'run_field_records': len(coverage),
        'export_rows': sum(row['export_rows'] for row in rows),
        'export_columns_per_run': 81, 'ever_nonempty_columns_per_run': 64,
        'entirely_empty_columns_per_run': 17,
        'source_age_columns_per_run': 5,
        'source_age_nonempty_cells_all_runs': 0,
        'retained_ue_event_rows': sum(row['retained_ue_event_rows'] for row in rows),
        'ue_event_timestamp_envelope_seconds_min': min(row['ue_event_timestamp_envelope_seconds'] for row in rows),
        'ue_event_timestamp_envelope_seconds_max': max(row['ue_event_timestamp_envelope_seconds'] for row in rows),
        'limitations': [
            'Ever-nonempty columns include identifiers, labels, configuration, state and quality; this is not a usable-feature count.',
            'Producer ok/missing/snapshot/replaced labels are preserved and do not independently certify accuracy.',
            'All five source-age export columns are empty; per-bucket source freshness cannot be reconstructed from these columns.',
            'UE event timestamp envelopes describe observed event times only, not continuous log completeness or full-day per-UE state coverage.',
            'K3s Ready workload rows are a different signal from registered UEs, sessions and business activity.',
            'No model score is used in these quality statistics.',
        ],
    }
    buf = io.StringIO(newline='')
    writer = csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    return {quality / 'SUMMARY.csv': buf.getvalue(), quality / 'SUMMARY.json': json.dumps(summary, indent=2)+'\n'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    outputs = build(args.root)
    if args.check:
        different = [str(path.relative_to(args.root)) for path, value in outputs.items() if not path.exists() or path.read_text() != value]
        if different:
            raise SystemExit('Export quality outputs differ: ' + ', '.join(different))
    else:
        for path, value in outputs.items():
            path.parent.mkdir(parents=True, exist_ok=True); path.write_text(value)
    print('W1 export availability: 7 runs, 611777 rows, 81 columns; metadata check passed')


if __name__ == '__main__':
    main()
