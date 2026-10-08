"""Build reviewer inventories from package files; never train or infer."""
from pathlib import Path
import csv, hashlib, json, re
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'evaluation_package/evaluation'

def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024 * 1024), b''): h.update(b)
    return h.hexdigest()

def write_csv(name, rows):
    keys = list(dict.fromkeys(k for r in rows for k in r))
    with (ROOT / 'manifests' / name).open('w', newline='') as f:
        w = csv.DictWriter(f, keys); w.writeheader(); w.writerows(rows)

def processor(p):
    s = str(p.relative_to(ROOT))
    if s.startswith('prediction_inputs/'):
        return 'evaluation_package/evaluation/prediction/src/prepare_repaired.py', 'Bundled cutoff-conditioned history/target tables; original prefix repair provenance retained in prediction/spec and source locks; not derived from the packaged 81-column export.'
    if '/timeseries_1s/' in s:
        return 'data_machine/platform/source_snapshot/scripts/export_v3_timeseries.py', 'Current exported view; complete original report/derived inputs unavailable; historical export identity unconfirmed.'
    if '/task_data/' in s:
        return 'data_machine/dataset/task_data/code/build_package.py', 'Source transfer package projection to task package; original upstream raw-to-5 s construction inputs are not bundled. Loader is code/dataset.py; anonymization and independent hashes in core_handoff.csv.'
    if '/imputation/' in s:
        return 'evaluation_package/evaluation/imputation/code/experiment.py', '5 s task observations -> within-segment 60-step windows; training stride12, other stride60; artificial masks and NaN-validity kept separately.'
    if '/localization/' in s:
        return 'evaluation_package/evaluation/localization/code/pipeline.py', 'Known recorded onset -> (start,start+60s] twelve 5 s cutoff rows; 24 variables; training-only robust scaling.'
    return 'evaluation_package/evaluation/prediction/src/data.py', 'Frozen target-specific sample index; labels and metadata excluded from inputs.'

def describe(p):
    if p.suffix == '.npz':
        with np.load(p, allow_pickle=False) as a:
            shape = {k: {'shape': list(a[k].shape), 'dtype': str(a[k].dtype)} for k in a.files}
            times = a['time'] if 'time' in a.files else None
            return None, shape, ([] if times is None or not times.size else [str(pd.to_datetime(int(times.min()), unit='s', utc=True)), str(pd.to_datetime(int(times.max()), unit='s', utc=True))])
    if p.suffix == '.npy':
        a = np.load(p, mmap_mode='r', allow_pickle=False)
        return None, {'shape': list(a.shape), 'dtype': str(a.dtype)}, []
    d = pd.read_parquet(p) if p.suffix == '.parquet' else pd.read_csv(p, low_memory=False)
    bounds = []
    for col in ['cutoff_time', 'time', 'history_row_epoch', 'anchor_epoch', 'anchor_time', 'start_time', 'start', 'last', 'timestamp']:
        if col not in d or d[col].dropna().empty: continue
        vals = d[col].dropna()
        if pd.api.types.is_numeric_dtype(vals):
            t = pd.to_datetime(vals, unit='s', utc=True)
        else:
            t = pd.to_datetime(vals, utc=True, format='mixed', errors='raise')
        bounds.append({'field': col, 'min': str(t.min()), 'max': str(t.max())})
    runs = sorted(d.run_id.dropna().astype(str).unique().tolist()) if 'run_id' in d else []
    return len(d), {'columns': [{'name': c, 'dtype': str(d[c].dtype)} for c in d], 'run_ids': runs}, bounds

def main():
    if (ROOT / "manifests/omitted_files.csv").exists():
        missing = [row["path"] for row in csv.DictReader((ROOT / "manifests/input_manifest.csv").open()) if not (ROOT / row["path"]).exists()]
        if missing:
            raise SystemExit("Dataset inputs are not bundled in this publication. Restore and hash-check all required external inputs before rebuilding inventories; retain the published full input contract.")
    inputs = []
    for p in sorted(ROOT.rglob('*')):
        if not p.is_file(): continue
        s = str(p.relative_to(ROOT))
        selected = (s.startswith('prediction_inputs/') or s.startswith('data_machine/dataset/task_data/') or '/timeseries_1s/' in s or s.endswith('imputation/metadata/scales.npz') or any('/'+v+'/' in s for v in ['imputation/data','imputation/masks','localization/cache','localization/data_contract','prediction/outputs/indices']))
        if not selected or not (p.suffix in ['.npz','.npy','.parquet','.csv'] or p.name.endswith('.csv.gz')): continue
        rows, schema, bounds = describe(p)
        proc, rule = processor(p)
        slot = next((part for part in p.parts if re.fullmatch(r'D0[1-7]', part)), '')
        if not slot:
            slot = next((x for x in ['D01','D02','D03','D04','D05','D06','D07','supp_core24h','validation_v4r6','diagnostic5','development_excluded'] if x in p.name), 'multiple_or_global')
        inputs.append(dict(run_id=slot, path=s, bytes=p.stat().st_size, sha256=sha(p), rows=rows, schema_or_shapes=json.dumps(schema), time_bounds=json.dumps(bounds), processor=proc, processor_sha256=sha(ROOT/proc), conversion_rule=rule, historical_paper_identity='unconfirmed'))
    write_csv('input_manifest.csv', inputs)
    fits = []
    patterns = [('prediction','prediction/outputs/jobs/*/record.json'),('detection','detection/normal_only/fits/*/experiment_config.json'),('classification','localization/models/*/fit.json'),('imputation','imputation/logs/fit*.json')]
    for task, pattern in patterns:
        for p in sorted(E.glob(pattern)):
            o = json.loads(p.read_text())
            branches = ['M','H'] if task=='imputation' else [None]
            for branch in branches:
                fits.append({'task':task,'record_path':str(p.relative_to(ROOT)), 'record_sha256':sha(p), 'model':('SAITS-'+branch) if branch else o.get('model',p.stem), 'seed':o.get('seed',''), 'status':o.get('status','recorded'), 'epochs':o.get('epochs',o.get('epochs_run',o.get('epochs_executed',''))), 'selected_epoch':o.get('best_epochs',{}).get(branch,'') if branch else o.get('best_epoch',o.get('selected_epoch','')), 'parameter_count':o.get('parameter_count',o.get('trainable_parameters','')), 'record_json':json.dumps(o)})
    for p in sorted((E/'detection/supervised_rf/fits').rglob('*.json')):
        o=json.loads(p.read_text())
        if 'seed' in o and ('fit' in p.name or 'config' in p.name):
            fits.append({'task':'detection_supervised','record_path':str(p.relative_to(ROOT)),'record_sha256':sha(p),'model':o.get('candidate',o.get('model','RF')),'seed':o['seed'],'status':o.get('status','recorded'),'record_json':json.dumps(o)})
    write_csv('fit_records.csv', fits)
    allfiles = [{'path':str(p.relative_to(ROOT)), 'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(ROOT.rglob('*')) if p.is_file() and '.git' not in p.parts and '__pycache__' not in p.parts and p != ROOT / 'SHA256SUMS.txt' and str(p.relative_to(ROOT)) != 'manifests/file_inventory.csv']
    write_csv('file_inventory.csv', allfiles)
    print(json.dumps({'inputs':len(inputs),'fit_records':len(fits),'files':len(allfiles),'bytes':sum(x['bytes'] for x in allfiles)}))

if __name__ == '__main__': main()
