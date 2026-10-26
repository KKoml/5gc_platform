#!/usr/bin/env python3
"""Assemble W1 platform-quality metrics from published evidence summaries."""
import argparse
import csv
import io
import json
from pathlib import Path


def build(root):
    quality = root / 'platform_data/quality'
    def read(path):
        return json.loads((quality / path).read_text())
    clock = read('clock/clock_summary.json')
    direct = read('direct_fields/evidence_counts.json')
    assoc = read('association/association_summary.json')['totals']
    coverage = read('coverage/SUMMARY.json')
    rows = []
    def add(metric, scope, status, source, interpretation, numerator=None, denominator=None,
            value=None, unit='fraction', median=None, p95=None, maximum=None):
        rows.append(dict(metric=metric, scope=scope, status=status, numerator=numerator,
                         denominator=denominator, value=value, unit=unit, median=median,
                         p95=p95, maximum=maximum, source=source, interpretation=interpretation))
    def fraction(metric, scope, numerator, denominator, source, interpretation, status='measured'):
        add(metric, scope, status, source, interpretation, numerator, denominator,
            numerator/denominator if denominator else None)
    pooled = next(g for g in clock['groups'] if g['run']=='ALL_W1' and g['host_role']=='remote_combined')
    source = 'clock/clock_summary.json'
    fraction('remote_probe_available', 'all remote probes; core reference excluded',
             pooled['available_n'], pooled['probe_rows'], source, 'Availability flag, not clock accuracy.')
    fraction('remote_probe_structurally_valid', 'all remote probes; no magnitude trimming',
             pooled['valid_interval_n'], pooled['probe_rows'], source, 'Finite, forward interval and producer-formula agreement.')
    for metric, key, limit in (
        ('absolute_midpoint_clock_offset', 'abs_midpoint_offset_ms_all_finite', 'SSH midpoint estimate, not matched-event alignment error.'),
        ('clock_probe_half_interval_uncertainty', 'half_interval_uncertainty_ms_all_finite', 'Half coordinator wall-clock interval around SSH; not pure network latency.'),
        ('clock_probe_maximum_absolute_compatible_endpoint', 'abs_raw_plus_uncertainty_ms_all_finite', 'Conditional single-probe interval endpoint under stable-clock assumptions; no unconditional timestamp guarantee.'),
        ('absolute_clock_interval_residual', 'abs_interval_residual_ms_all_finite', 'Closest compatible interval point to zero; not midpoint offset or event error.'),
    ):
        stats = pooled['metrics'][key]
        add(metric, 'all finite remote probes', 'measured', source, limit, denominator=stats['n'], unit='ms',
            median=stats['median'], p95=stats['p95'], maximum=stats['max'])
    stats = clock['record_clock_skew_ms_all_finite']
    add('producer_residual_clock_skew', 'once per health record', 'producer_measurement', source,
        'Range of residual offsets with core zero; not measured event alignment error.', denominator=stats['n'],
        unit='ms', median=stats['median'], p95=stats['p95'], maximum=stats['max'])
    stats = pooled['health_interval_seconds']
    add('observed_health_record_interval', 'within observed runs only; no between-run interval', 'measured', source,
        'No completeness assumed outside observed first/last timestamps.', denominator=stats['n'], unit='s',
        median=stats['median'], p95=stats['p95'], maximum=stats['max'])
    add('observed_health_intervals_over_60s', 'within observed run spans', 'measured', source,
        '60 s is descriptive, not a new acceptance gate.', denominator=stats['n'],
        value=pooled['health_interval_gt_60s_n'], unit='intervals')
    source = 'direct_fields/evidence_counts.json'
    counts = direct['aggregate']['rows']
    assert counts['mapping_rows'] == assoc['session_map']['row_count']
    fraction('raw_log_exact_context_share_all_mapping_rows', 'all retained mapping rows',
             counts['exact_context_rows'], counts['mapping_rows'], source,
             'Source basename, normalized timestamp, SUPI and PDU are matching keys, not independent truth.')
    fraction('raw_log_exact_context_share_inspected_source_scope', 'mapping rows in inspected SMF source scope',
             counts['exact_context_rows'], counts['mapping_rows']-counts['source_outside_audited_log_scope_rows'], source,
             'Outside-scope aggregate-log rows excluded explicitly, not repaired or counted as mismatches.')
    fields = [direct['aggregate']['exact_body_fields'][f] for f in direct['nonkey_body_fields']]
    agree = sum(f['exact_body_corroborated'] for f in fields)
    mismatch = sum(f['exact_body_mismatch'] for f in fields)
    fraction('nonkey_body_field_agreement_among_compared_values', 'record x non-key body field comparisons',
             agree, agree+mismatch, source, 'Nine non-key fields; independent identity precision/recall is not assessed.')
    add('nonkey_body_field_outside_source_scope', 'record x non-key body field opportunities', 'outside_audited_scope', source,
        'Unknown comparison results, not a fallback or error count.', denominator=counts['mapping_rows']*len(fields),
        value=sum(f['source_outside_audited_log_scope'] for f in fields), unit='comparisons')
    source = 'association/association_summary.json'
    session = assoc['session_map']
    for label, number in sorted(session['producer_route_counts'].items()):
        fraction('session_route:'+label, 'all retained session-map records', number, session['row_count'], source,
                 'Producer row route includes temporal/path/configuration inference; not direct field fraction.', 'producer_metadata')
    fraction('session_explicit_ran_n3_fallback_route', 'all retained session-map records',
             session['explicit_ran_n3_fallback_route_rows'], session['row_count'], source,
             'Separate producer fallback row route; zero does not imply zero field-level inference.', 'producer_metadata')
    fraction('run_wide_ip_key_multiple_identity_exposure', 'run-qualified UE-IP keys in retained session maps',
             session['ue_ip_keys_with_multiple_supi_pdu_identities'], session['ue_ip_keys'], source,
             'Run-wide reuse, not simultaneous conflict, wrong DNN/UPF label or observed error rate.')
    for family, group in sorted(assoc['flow_artifacts_by_capture_family'].items()):
        scope = family+'; deterministic every-12th-file sample plus final file; all selected rows'
        n = group['sampled_flow_artifact_record_count']
        for label, number in sorted(group['producer_route_counts'].items()):
            fraction('flow_route:'+label, scope, number, n, source,
                     'Sampled flow-record label share only; no population, packet, or accuracy estimate.', 'sample_producer_metadata')
        # Explicit zeros distinguish an unobserved sample route from an unrecorded field-level decision.
        for label in ('inferred:interface', 'inferred:subnet'):
            if label not in group['producer_route_counts']:
                fraction('flow_route:'+label, scope, 0, n, source,
                         'No rows with this literal route in the sample; field-level fallback remains unmeasured.', 'sample_producer_metadata')
        add('retained_capture_flow_rows', family+'; all canonical capture summaries', 'producer_reported', source,
            'Artifact-row count; observation points may duplicate communications; logical N6 excluded.',
            denominator=group['all_capture_file_count'], value=group['all_retained_flow_record_count'], unit='flow_records')
    source = 'coverage/SUMMARY.json'
    for metric, key in (('export_ever_nonempty_columns', 'ever_nonempty_columns_per_run'),
                        ('export_entirely_empty_columns', 'entirely_empty_columns_per_run')):
        add(metric, 'each accepted W1 run', 'measured_availability', source,
            'Includes identifiers and context; not a valid numerical-feature count.', denominator=81, value=coverage[key], unit='columns')
    add('source_age_nonempty_cells', 'all five source-age columns across seven runs', 'measured_availability', source,
        'Empty values prevent bucket-level freshness reconstruction from these columns.',
        denominator=coverage['export_rows']*coverage['source_age_columns_per_run'], value=0, unit='cells')
    for metric, why in (
        ('same_event_cross_host_alignment_error', 'No independent same-event timestamp reference; VM/container/decoder and ingest timing not calibrated.'),
        ('field_level_direct_observation_fraction', 'Historical per-field match routes and decisions not retained; body corroboration is source consistency.'),
        ('field_level_fallback_fraction', 'A row producer route does not encode every inferred attribute.'),
        ('association_precision', 'No independent adjudicated truth labels or complete rejected candidates.'),
        ('association_recall', 'No independently measured population of true associations.'),
        ('actual_misassociation_rate', 'IP reuse exposure is not an observed error rate.'),
    ):
        add(metric, 'historical W1', 'unmeasured', 'README.md', why)
    buf=io.StringIO(newline='')
    writer=csv.DictWriter(buf, fieldnames=list(rows[0]), lineterminator='\n')
    writer.writeheader();writer.writerows(rows)
    summary={'schema':'w1-platform-quality/v1','scope':'seven accepted W1 runs',
             'model_scores_used':False, 'metrics':rows,
             'null_policy':'null numeric values paired with status=unmeasured mean not measured, never zero.'}
    return {quality/'PLATFORM_QUALITY_METRICS.csv':buf.getvalue(),
            quality/'PLATFORM_QUALITY_METRICS.json':json.dumps(summary,indent=2)+'\n'}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1])
    p.add_argument('--check',action='store_true')
    args=p.parse_args(); outputs=build(args.root)
    for path,value in outputs.items():
        if args.check:
            if not path.exists() or path.read_text()!=value:
                raise SystemExit('Quality metrics differ: '+str(path))
        else:
            path.write_text(value)
    print('PASS: W1 platform-quality headline metrics; measured and unmeasured scopes remain separate')


if __name__=='__main__':
    main()
