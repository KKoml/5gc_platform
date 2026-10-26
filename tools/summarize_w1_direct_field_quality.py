#!/usr/bin/env python3
"""Recompute anonymous W1 session-map/raw-SMF-log consistency counts."""
import argparse
import collections
import csv
import datetime as dt
import io
import json
import re
from pathlib import Path

FIELDS = ('supi', 'pdu_session_id', 'dnn', 'ue_ip', 'upf_id', 'upf_pfcp_addr',
          'teid_ul', 'teid_dl', 'local_dl_teid', 'ran_addr', 'ran_dl_teid')
NONKEY = tuple(field for field in FIELDS if field not in ('supi', 'pdu_session_id'))
NUMERIC = {'pdu_session_id', 'teid_ul', 'teid_dl', 'local_dl_teid', 'ran_dl_teid'}
LOGS = ('smf-gold.log', 'smf-silver.log')
STATES = ('denominator_mapping_rows', 'map_value_nonnull', 'map_value_null',
          'exact_body_corroborated', 'exact_body_mismatch', 'raw_context_value_null',
          'source_outside_audited_log_scope', 'source_log_unavailable',
          'no_exact_context', 'conflicting_exact_contexts')
ROW_STATES = ('mapping_rows', 'exact_context_rows', 'duplicate_identical_context_rows',
              'conflicting_exact_contexts_rows', 'no_exact_context_rows',
              'source_outside_audited_log_scope_rows', 'source_log_unavailable_rows')
NOT_BODY = ('selected_amf', 'snssai_sst', 'snssai_sd', 'pfcp_session_established')
SCOPE = 'W1 accepted D01-D07; retained session-map rows and the corresponding original smf-gold.log/smf-silver.log only.'
LIMIT = ('Retrospective raw-log corroboration, not independently adjudicated association '
         'accuracy or historical pipeline direct/fallback decisions. SUPI/PDU identifiers '
         'are matching keys, not independent validation. Selected SMF is producer/path '
         'binding. Aggregate-core-log rows are outside the two-SMF-log audit scope.')


def normalized(field, value):
    if value is None or value == '':
        return None
    if field in NUMERIC:
        number = int(value)
        return None if field != 'pdu_session_id' and number == 0 else number
    return str(value).strip() or None


def timestamp(value):
    parsed = dt.datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('Context matching requires an explicit timestamp UTC offset')
    return parsed.astimezone(dt.timezone.utc).isoformat(timespec='microseconds')


def aggregate(runs):
    result = {'run_count': len(runs)}
    for group in ('rows', 'selected_smf_producer_path_binding'):
        counts = collections.Counter()
        for run in runs:
            counts.update(run[group])
        result[group] = dict(counts)
    for group in ('exact_body_fields', 'not_explicit_in_sessionmap_body'):
        result[group] = {}
        for field in runs[0][group]:
            counts = collections.Counter()
            for run in runs:
                counts.update(run[group][field])
            result[group][field] = dict(counts)
    return result


def extract(run_map):
    expected = {'W1-D%02d' % day for day in range(1, 8)}
    if set(run_map) != expected or len({str(Path(path).expanduser().resolve()) for path in run_map.values()}) != 7:
        raise ValueError('Run map must name seven unique directories as W1-D01 through W1-D07')
    runs = []
    for public_run, directory in sorted(run_map.items()):
        root = Path(directory).expanduser().resolve()
        with (root / 'derived/session_map.jsonl').open() as handle:
            maps = [json.loads(line) for line in handle if line.strip()]
        index, available = collections.defaultdict(list), set()
        for name in LOGS:
            path = root / 'nf' / name
            if not path.is_file():
                continue
            available.add(name)
            with path.open(errors='replace') as handle:
                for line in handle:
                    if 'SessionMap PDU session context:' not in line:
                        continue
                    time_match = re.search(r'time="([^"]+)"', line)
                    body = dict(re.findall(r'(\w+)\[([^\]]*)\]', line.split('SessionMap PDU session context:', 1)[1]))
                    if time_match is None or any(field not in body for field in FIELDS):
                        raise ValueError('Unparseable SessionMap context in ' + public_run)
                    body = {field: normalized(field, body[field]) for field in FIELDS}
                    key = (name, timestamp(time_match[1]), body['supi'], body['pdu_session_id'])
                    index[key].append(body)
        rows = collections.Counter()
        fields = {field: collections.Counter() for field in FIELDS}
        binding = collections.Counter()
        other = {field: collections.Counter() for field in NOT_BODY}
        for mapping in maps:
            rows['mapping_rows'] += 1
            source = Path(str(mapping.get('source_file') or '')).name
            key = (source, timestamp(mapping['timestamp']), normalized('supi', mapping.get('supi')),
                   normalized('pdu_session_id', mapping.get('pdu_session_id')))
            candidates = index.get(key, [])
            distinct = {tuple(item[field] for field in FIELDS) for item in candidates}
            state = ('source_outside_audited_log_scope' if source not in LOGS else
                     'source_log_unavailable' if source not in available else
                     'no_exact_context' if not candidates else
                     'conflicting_exact_contexts' if len(distinct) > 1 else 'exact_context')
            rows[state + '_rows'] += 1
            if state == 'exact_context' and len(candidates) > 1:
                rows['duplicate_identical_context_rows'] += 1
            for field, counts in fields.items():
                counts['denominator_mapping_rows'] += 1
                value = normalized(field, mapping.get(field))
                counts['map_value_null' if value is None else 'map_value_nonnull'] += 1
                if value is not None:
                    counts[state if state != 'exact_context' else
                           'raw_context_value_null' if candidates[0][field] is None else
                           'exact_body_corroborated' if candidates[0][field] == value else 'exact_body_mismatch'] += 1
            binding['denominator_mapping_rows'] += 1
            binding['map_value_null' if not mapping.get('selected_smf') else
                    'source_outside_audited_log_scope' if source not in LOGS else
                    'source_log_unavailable' if source not in available else
                    'producer_path_identity_agrees' if mapping['selected_smf'] == Path(source).stem else
                    'producer_path_identity_disagrees'] += 1
            for field, counts in other.items():
                counts['denominator_mapping_rows'] += 1
                counts['map_value_null' if mapping.get(field) is None or mapping.get(field) == '' else 'map_value_nonnull'] += 1
                counts['not_a_sessionmap_body_field'] += 1
        runs.append({'slot': public_run[3:], 'rows': {name: rows[name] for name in ROW_STATES},
                     'exact_body_fields': {field: {name: counts[name] for name in STATES} for field, counts in fields.items()},
                     'selected_smf_producer_path_binding': dict(binding),
                     'not_explicit_in_sessionmap_body': {field: dict(counts) for field, counts in other.items()}})
    return {'schema': 'w1-session-map-raw-log-corroboration/v1', 'scope': SCOPE,
            'matching_keys': ['source_log_basename', 'timestamp_utc_microseconds', 'supi', 'pdu_session_id'],
            'nonkey_body_fields': list(NONKEY), 'interpretation': LIMIT, 'runs': runs, 'aggregate': aggregate(runs)}


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def csv_text(rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def summarize(evidence):
    runs = evidence['runs']
    if {run['slot'] for run in runs} != {'D%02d' % day for day in range(1, 8)} or len(runs) != 7:
        raise ValueError('Evidence must contain exactly seven unique D01-D07 slots')
    summed = aggregate(runs)
    if summed != evidence['aggregate']:
        raise ValueError('Recorded aggregate does not equal the per-run counts')
    records, fields, bindings = [], [], []
    for run in runs + [dict(summed, slot='ALL')]:
        label = 'ALL' if run['slot'] == 'ALL' else 'W1-' + run['slot']
        rows = {name: run['rows'].get(name, 0) for name in ROW_STATES}
        if rows['mapping_rows'] != sum(rows[name] for name in ROW_STATES if name not in ('mapping_rows', 'duplicate_identical_context_rows')):
            raise ValueError('Record denominator mismatch: ' + label)
        scoped = rows['mapping_rows'] - rows['source_outside_audited_log_scope_rows'] - rows['source_log_unavailable_rows']
        record = dict(run=label, **rows,
                      exact_context_fraction_all_mapping_rows=ratio(rows['exact_context_rows'], rows['mapping_rows']),
                      exact_context_fraction_audited_available_source_rows=ratio(rows['exact_context_rows'], scoped))
        for name in ('denominator_mapping_rows', 'exact_body_corroborated', 'exact_body_mismatch', 'map_value_null', 'source_outside_audited_log_scope'):
            record['nonkey_pairs_' + name] = sum(run['exact_body_fields'][field].get(name, 0) for field in NONKEY)
        records.append(record)
        for field in FIELDS:
            counts = {name: run['exact_body_fields'][field].get(name, 0) for name in STATES}
            if counts['denominator_mapping_rows'] != rows['mapping_rows'] or counts['map_value_null'] + counts['map_value_nonnull'] != rows['mapping_rows'] or counts['map_value_nonnull'] != sum(counts[name] for name in STATES[3:]):
                raise ValueError('Field denominator mismatch: ' + label + '/' + field)
            compared = counts['exact_body_corroborated'] + counts['exact_body_mismatch']
            fields.append(dict(run=label, field=field, role='matching_key' if field in ('supi', 'pdu_session_id') else 'nonkey_body_attribute', **counts,
                               compared_value_pairs=compared,
                               corroborated_fraction_all_mapping_rows=ratio(counts['exact_body_corroborated'], rows['mapping_rows']),
                               corroborated_fraction_compared_values=ratio(counts['exact_body_corroborated'], compared)))
        smf = run['selected_smf_producer_path_binding']
        bindings.append(dict(run=label, field='selected_smf', evidence_kind='producer_path_binding', denominator_mapping_rows=rows['mapping_rows'],
                             agrees=smf.get('producer_path_identity_agrees', 0), disagrees=smf.get('producer_path_identity_disagrees', 0),
                             map_null=smf.get('map_value_null', 0), map_nonnull=rows['mapping_rows'] - smf.get('map_value_null', 0),
                             outside_scope=smf.get('source_outside_audited_log_scope', 0), source_unavailable=smf.get('source_log_unavailable', 0)))
        if sum(bindings[-1][name] for name in ('agrees', 'disagrees', 'map_null', 'outside_scope', 'source_unavailable')) != rows['mapping_rows']:
            raise ValueError('Producer-path binding denominator mismatch: ' + label)
        for field in NOT_BODY:
            counts = run['not_explicit_in_sessionmap_body'][field]
            if counts.get('map_value_null', 0) + counts.get('map_value_nonnull', 0) != rows['mapping_rows'] or counts.get('not_a_sessionmap_body_field') != rows['mapping_rows']:
                raise ValueError('Non-body field denominator mismatch: ' + label + '/' + field)
            bindings.append(dict(run=label, field=field, evidence_kind='not_explicit_in_sessionmap_body', denominator_mapping_rows=rows['mapping_rows'],
                                 agrees='', disagrees='', map_null=counts.get('map_value_null', 0), map_nonnull=counts.get('map_value_nonnull', 0), outside_scope='', source_unavailable=''))
    summary = {'schema': 'w1-direct-field-summary/v1', 'scope': evidence['scope'], 'interpretation': LIMIT,
               'record_summary': records, 'field_summary': fields, 'other_provenance': bindings}
    return {'record_summary.csv': csv_text(records), 'field_summary.csv': csv_text(fields), 'other_provenance.csv': csv_text(bindings),
            'direct_field_summary.json': json.dumps(summary, indent=2, sort_keys=True) + '\n'}


def main():
    directory = Path(__file__).resolve().parents[1] / 'platform_data/quality/direct_fields'
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path, default=directory / 'evidence_counts.json')
    parser.add_argument('--output-dir', type=Path, default=directory)
    parser.add_argument('--run-map', type=Path, help='Optional owner-supplied JSON mapping W1-D01..W1-D07 to original run directories')
    parser.add_argument('--check', action='store_true', help='Recompute summaries in memory and compare their full text with saved files')
    args = parser.parse_args()
    evidence = extract(json.loads(args.run_map.read_text())) if args.run_map else json.loads(args.evidence.read_text())
    outputs = summarize(evidence)
    if args.check:
        for name, text in outputs.items():
            if (args.output_dir / name).read_text() != text:
                raise ValueError('Saved summary text differs: ' + name)
        print('PASS: exact summary text, aggregate counts and denominator conservation')
    else:
        args.output_dir.mkdir(parents=True, exist_ok=True)
        if args.run_map:
            (args.output_dir / 'evidence_counts.json').write_text(json.dumps(evidence, indent=2, sort_keys=True) + '\n')
        for name, text in outputs.items():
            (args.output_dir / name).write_text(text)
        print('Wrote anonymous summaries to ' + str(args.output_dir))


if __name__ == '__main__':
    main()
