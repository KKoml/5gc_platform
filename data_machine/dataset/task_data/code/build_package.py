#!/usr/bin/env python3
"""Build a new three-task data package from the sealed source transfer package.

This build-time tool needs the source package. Runtime loading/validation does not.
It projects existing values; it does not reconstruct raw telemetry or train models.
"""
import argparse
import hashlib
import json
import platform
import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def write_pair(frame, stem):
    stem.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(str(stem) + '.parquet', index=False)
    frame.to_csv(str(stem) + '.csv.gz', index=False, compression={'method': 'gzip', 'mtime': 0})


def seconds(values):
    return pd.DatetimeIndex(pd.to_datetime(values, utc=True)).as_unit('ns').asi8 / 1e9


def build(source, root):
    source, root = source.resolve(), root.resolve()
    if root == source or root.is_relative_to(source):
        raise ValueError('Destination must be independent of the sealed source')
    if (root / 'reports/BUILD_REPORT.json').exists():
        raise ValueError('A completed build exists; use a new versioned destination')
    root.mkdir(parents=True, exist_ok=True)
    original_seal = {}
    for line in (source / 'SHA256SUMS.txt').read_text().splitlines():
        expected, relative = line.split('  ', 1)
        path = (source / relative).resolve()
        if not path.is_relative_to(source) or digest(path) != expected:
            raise ValueError('Source seal mismatch: ' + relative)
        original_seal[relative] = expected

    old_sets = json.loads((source / 'metadata/feature_sets.json').read_text())
    sets = {
        'FD_detection_24': old_sets['T2_detection_24'],
        'FP_warning_16': old_sets['T3_warning_candidate_16'],
        'FL_primary_10': old_sets['T4_upf_localization_6'] + [
            'smf-silver__cpu_millicores', 'smf-silver__memory_bytes',
            'smf-gold__cpu_millicores', 'smf-gold__memory_bytes'],
        'FL_baseline_6': old_sets['T4_upf_localization_6'],
    }
    columns = sets['FD_detection_24']
    assert len(columns) == len(set(columns)) == 24
    assert all(set(v).issubset(columns) for v in sets.values())
    task_aliases = {'FD_detection': 'T2', 'FL_localization': 'T4_upf', 'FP_forewarning': 'T3'}
    task_sets = {'FD_detection': 'FD_detection_24', 'FL_localization': 'FL_primary_10', 'FP_forewarning': 'FP_warning_16'}
    (root / 'metadata').mkdir(exist_ok=True)
    provenance = []

    def record(src, dst, transform):
        provenance.append({'source_relative_path': str(src.relative_to(source)),
                           'package_relative_path': str(dst.relative_to(root)),
                           'source_sha256': digest(src), 'package_sha256': digest(dst),
                           'transform': transform})

    def copy(relative, destination=None):
        src = source / relative
        dst = root / (destination or relative)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        record(src, dst, 'byte_identical_copy')

    runs = pd.read_csv(source / 'metadata/runs.csv')
    copy('metadata/runs.csv')
    copy('metadata/ALL_CORE_EPISODES.csv')
    copy('metadata/EXTRACTED_KPI_DICTIONARY.csv', 'provenance/SOURCE_EXTRACTED_KPI_DICTIONARY.csv')
    copy('metadata/protocol.json', 'provenance/SOURCE_PROTOCOL.json')
    copy('metadata/FEATURE_SELECTION.json', 'provenance/SOURCE_FEATURE_SELECTION.json')
    copy('SHA256SUMS.txt', 'provenance/SOURCE_SHA256SUMS.txt')
    episodes = pd.read_csv(root / 'metadata/ALL_CORE_EPISODES.csv')
    assert not episodes.duplicated(['run_id', 'fault_id']).any()
    observations, coverage = {}, []
    age_columns = ['cutoff_time', 'core-host-local__host_age_sec',
                   *[f'{nf}__nf_age_sec' for nf in ['amf-a', 'amf-b', 'smf-silver', 'smf-gold', 'upf-silver', 'upf-gold']],
                   'upf-silver__state_age_sec', 'upf-gold__state_age_sec',
                   'core-if-upfgtp-silver__interface_age_sec']
    for run in runs.to_dict('records'):
        relative = Path(run['data_path'])
        inp, out = source / relative, root / relative
        frame = pd.read_parquet(inp / 'core_features_5s.parquet', columns=['run_id', 'cutoff_time'] + columns)
        assert frame.run_id.eq(run['run_id']).all()
        assert np.all(np.diff(seconds(frame.cutoff_time)) == 5)
        observations[run['run_id']] = frame
        write_pair(frame, out / 'core_features_5s')
        for suffix in ['.parquet', '.csv.gz']:
            record(inp / 'core_features_5s.parquet', out / ('core_features_5s' + suffix), 'exact_24_column_projection_no_imputation')
        age = pd.read_parquet(inp / 'source_age_5s.parquet')[age_columns]
        age.to_parquet(out / 'source_age_5s.parquet', index=False)
        record(inp / 'source_age_5s.parquet', out / 'source_age_5s.parquet', 'selected_source_age_columns_audit_only')
        copy(str(relative / 'task_index.csv.gz'), str(relative / 'source_context_index.csv.gz'))
        for name in ['episodes.csv', 'user_behavior_events.csv', 'recovery_audit.csv', 'excluded_episode_audit.csv', 'source_binding.json']:
            copy(str(relative / name))
        for name in columns:
            values = frame[name]
            coverage.append({'run_id': run['run_id'], 'slot': run['slot'], 'split': run['split'],
                             'feature': name, 'rows': len(values), 'finite': int(np.isfinite(values).sum()),
                             'observed_fraction': float(np.isfinite(values).mean()),
                             'finite_unique_values': int(values.dropna().nunique())})
    pd.DataFrame(coverage).to_csv(root / 'metadata/FEATURE_COVERAGE_BY_RUN.csv', index=False)

    indices = {}
    counts, group_counts = [], []
    for task, original in task_aliases.items():
        src = source / f'tasks/{original}/index.parquet'
        index = pd.read_parquet(src)
        index['source_sample_id'] = index.sample_id
        index['source_feature_set'] = index.feature_set
        index['sample_id'] = index.sample_id.str.replace(original + ':', task + ':', n=1, regex=False)
        index['feature_set'] = task_sets[task]
        if task == 'FL_localization':
            for col in ['observed_fraction', 'min_channel_observed_fraction', 'missing_channel_count']:
                index['source_' + col] = index[col]
            for run_id, group in index.groupby('run_id', sort=False):
                vals = observations[run_id][sets['FL_primary_10']].to_numpy(float)
                prefix = np.vstack([np.zeros((1, 10), dtype=np.int64), np.cumsum(np.isfinite(vals), axis=0)])
                obs = prefix[group.stop_row.to_numpy(int)] - prefix[group.start_row.to_numpy(int)]
                index.loc[group.index, 'observed_fraction'] = obs.sum(axis=1) / 120
                index.loc[group.index, 'min_channel_observed_fraction'] = obs.min(axis=1) / 12
                index.loc[group.index, 'missing_channel_count'] = (obs == 0).sum(axis=1)
            # Preserve the source case set for a paired 6-versus-10 comparison.
            if not index.loc[index.eligible, 'observed_fraction'].ge(0.5).all():
                raise ValueError('FL enhancement loses original cases; explicit protocol revision required')
        elif task == 'FP_forewarning':
            index['next_core_fault_id'] = ''
            index['next_core_onset_time'] = ''
            index['seconds_to_next_core_onset'] = np.nan
            index['next_core_episode_scope'] = ''
            for run_id, group in index.groupby('run_id', sort=False):
                ep = episodes.loc[episodes.run_id.eq(run_id)].sort_values('start_time').reset_index(drop=True)
                if ep.empty:
                    continue
                starts = seconds(ep.start_time)
                if len(np.unique(starts)) != len(starts):
                    raise ValueError('Simultaneous starts require explicit multi-event matching')
                anchor = seconds(group.anchor_time)
                pos = np.searchsorted(starts, anchor, side='right')
                valid = pos < len(starts)
                dest = group.index[valid]
                selected = ep.iloc[pos[valid]]
                index.loc[dest, 'next_core_fault_id'] = selected.fault_id.to_numpy()
                index.loc[dest, 'next_core_onset_time'] = selected.start_time.to_numpy()
                index.loc[dest, 'seconds_to_next_core_onset'] = starts[pos[valid]] - anchor[valid]
                index.loc[dest, 'next_core_episode_scope'] = selected.episode_scope.to_numpy()
        stem = root / f'tasks/{task}/index'
        write_pair(index, stem)
        for suffix in ['.parquet', '.csv.gz']:
            record(src, Path(str(stem) + suffix), 'task_alias_and_metadata_only; FL_coverage_recomputed; FP_future_event_link_added')
        indices[task] = index
        for run in runs.to_dict('records'):
            rows = index.loc[index.run_id.eq(run['run_id'])]
            kept = rows.loc[rows.eligible]
            counts.append({'task': task, 'run_id': run['run_id'], 'slot': run['slot'], 'family': run['family'],
                           'split': run['split'], 'candidates': len(rows), 'eligible': len(kept), 'excluded': len(rows) - len(kept),
                           'eligible_positive': int(kept.y.eq(1).sum()) if task != 'FL_localization' else None,
                           'normal_train_window': int(rows.normal_train_window.sum()) if task == 'FD_detection' else None})
        if task == 'FL_localization':
            for key, rows in index.groupby(['slot', 'split', 'fault_type', 'target_instance']):
                group_counts.append(dict(zip(['slot', 'split', 'fault_type', 'target_instance'], key)) |
                                    {'candidates': len(rows), 'eligible': int(rows.eligible.sum())})
    (root / 'reports').mkdir(exist_ok=True)
    pd.DataFrame(counts).to_csv(root / 'reports/TASK_COUNTS.csv', index=False)
    pd.DataFrame(group_counts).to_csv(root / 'reports/FL_COUNTS_BY_TYPE_TARGET.csv', index=False)
    fp = indices['FP_forewarning']
    fd = indices['FD_detection']
    event_counts = []
    for e in episodes.to_dict('records'):
        selected = fp.loc[fp.run_id.eq(e['run_id']) & fp.eligible & fp.y.eq(1) & fp.next_core_fault_id.eq(e['fault_id'])]
        detected = fd.loc[fd.run_id.eq(e['run_id']) & fd.eligible & fd.y.eq(1)]
        stamps = seconds(detected.anchor_time)
        fd_count = int(((stamps >= pd.Timestamp(e['start_time']).timestamp()) & (stamps < pd.Timestamp(e['end_time']).timestamp())).sum())
        event_counts.append({k: e[k] for k in ['run_id', 'slot', 'run_split', 'fault_id', 'fault_type', 'target_instance', 'episode_scope', 'start_time', 'end_time']} |
                            {'FP_eligible_positive_windows': len(selected), 'FP_has_eligible_pre_window': not selected.empty,
                             'FP_min_lead_seconds': float(selected.seconds_to_next_core_onset.min()) if len(selected) else None,
                             'FP_max_lead_seconds': float(selected.seconds_to_next_core_onset.max()) if len(selected) else None,
                             'FD_eligible_active_windows': fd_count})
    pd.DataFrame(event_counts).to_csv(root / 'metadata/EVENT_EVALUABILITY.csv', index=False)
    source_roles = []
    for col in ['run_id', 'cutoff_time'] + columns:
        source_roles.append({'file_group': 'observations', 'column': col, 'role': 'observation' if col in columns else 'identifier',
                             'model_input': col in columns})
    for task, index in indices.items():
        for col in index.columns:
            source_roles.append({'file_group': task + '_index', 'column': col, 'role': 'label' if col == 'y' else 'index_or_audit_metadata', 'model_input': False})
    pd.DataFrame(source_roles).to_csv(root / 'metadata/COLUMN_ROLES.csv', index=False)
    write_json(root / 'metadata/feature_sets.json', sets)
    write_json(root / 'metadata/TASK_ALIASES.json', task_aliases)
    protocol = {
        'version': 'core-fault-experiment-package-v1', 'created_utc': '2026-09-23T08:28:01Z',
        'delivery': 'portable_data_and_plan_only', 'training_executed': False,
        'grid_seconds': 5, 'history_steps': 12, 'task_feature_sets': task_sets,
        'observation_columns': columns, 'task_aliases': task_aliases,
        'coverage_policy': {'preserve_nan': True, 'minimum_observed_fraction_by_task':
                            {'FD_detection': 0.8, 'FL_localization': 0.5, 'FP_forewarning': 0.8},
                            'per_channel_floor': None, 'FL_case_set': 'same_source_cases_for_primary10_and_baseline6'},
        'FP_warning_min_seconds': 10, 'FP_warning_max_seconds': 60, 'FL_post_start_seconds': 60,
        'T3_warning_min_seconds': 10, 'T3_warning_max_seconds': 60, 'T4_post_start_seconds': 60,
        'FD_fit_rule': 'eligible AND split=train AND normal_train_window; preprocessing uses exactly the same clean subset',
        'expected_FD_normal_training_windows': 55196,
        'FP_history_rule': 'clean 60s history; no active/recovery/prelude; nearest future start >=10s; complete next60s',
        'FP_event_link': 'nearest strictly future actual start within same run; metadata never model input',
        'FP_onset_evidence_boundary': 's is the faults.jsonl start record timestamp, not independently certified first physical effect. A 10s lead does not rule out execution-to-log delay. Prediction claims are relative to the recorded onset until dispatch/effect evidence is audited.',
        'FL_scope': 'main Silver/Gold intervention targets or associated paths; known onset conditional localization',
        'label_scope': 'actual recorded Core interventions; not independent business-effect ground truth',
        'main_split': 'W1 D01-D04 train; D05 validation; D06-D07 previously used test; not calendar-forward',
        'access_scope': 'gNB/UE actions are user behavior; excluded from Core fault labels and model observation columns',
        'time_availability': 'frozen conservative source-time alignment; centralized arrival times not certified',
        'non_W1_coverage_basis': 'parsed_span_inferred; not lifecycle-certified complete collection',
        'source_context_index_role': 'audit only; legacy labels and eligibility are NOT the current task contract',
        'sample_unit': {'FD_detection': '12-step window', 'FP_forewarning': '12-step pre-onset window; evaluate per event too',
                        'FL_localization': 'one post60 case per event'},
        'expected_totals': {task: {'candidates': len(x), 'eligible': int(x.eligible.sum())} for task, x in indices.items()},
        'runtime_requires_source_paths': False,
    }
    write_json(root / 'metadata/protocol.json', protocol)
    write_json(root / 'metadata/BUILDER_ENVIRONMENT.json', {'python': platform.python_version(), 'numpy': np.__version__,
                                                         'pandas': pd.__version__, 'pyarrow': pyarrow.__version__})
    pd.DataFrame(provenance).to_csv(root / 'provenance/FILE_LINEAGE.csv', index=False)
    unchanged = all(digest(source / relative) == expected for relative, expected in original_seal.items())
    if not unchanged:
        raise ValueError('A sealed source file changed during package building')
    write_json(root / 'reports/SOURCE_IMMUTABILITY.json', {'passed': unchanged, 'sealed_source_files_checked': len(original_seal),
                                                        'source_package': source.name, 'verification': 'all source manifest hashes before and after build'})
    report = {'built': True, 'run_count': len(runs), 'observation_rows': sum(len(x) for x in observations.values()),
              'value_columns': len(columns), 'all_core_episodes': len(episodes),
              'main_core_episodes': int(episodes.episode_scope.eq('main').sum()),
              'tasks': protocol['expected_totals'], 'FD_normal_training_windows': int(fd.normal_train_window.sum()),
              'FP_eligible_positive_windows': int((fp.eligible & fp.y.eq(1)).sum()),
              'projected_values_unchanged': True, 'training_executed': False}
    write_json(root / 'reports/BUILD_REPORT.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--root', type=Path, required=True)
    a = p.parse_args()
    build(a.source, a.root)
