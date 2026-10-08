"""Cutoff-conditioned repaired window access; legacy raw reads only for unchanged auxiliary views."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import yaml
ROOT=Path(__file__).resolve().parents[1]

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''): h.update(b)
    return h.hexdigest()

def json_write(path, obj):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=str, allow_nan=False) + '\n')
    tmp.replace(path)

def index_hash(frame):
    return hashlib.sha256('\n'.join(frame.sample_id.astype(str)).encode()).hexdigest()

def config(): return yaml.safe_load((ROOT/'resolved_config.yaml').read_text())

def load_slot(c, slot):
    base = Path(c['resolved']['dataset_root']); taskroot = Path(c['resolved']['task_root'])
    item = next(x for x in json.loads((base/'manifest.json').read_text())['data_files'] if x['slot']==slot)
    features = c['resolved']['features']; ran = c['resolved']['ran_features']
    raw = pd.read_csv(base/item['path'], usecols=['time']+features+ran)
    task = pd.read_parquet(taskroot/f'rows/{slot}.parquet')
    time = pd.to_datetime(raw.time, utc=True)
    assert len(raw)==len(task) and np.array_equal(time.to_numpy(), task.time.to_numpy())
    assert time.diff().iloc[1:].eq(pd.Timedelta(seconds=1)).all(), 'Nonphysical time grid'
    assert task.slot.eq(slot).all() and np.array_equal(task.row_index, np.arange(len(task)))
    a = raw[features].apply(pd.to_numeric, errors='coerce').to_numpy(dtype=np.float64)
    a[~np.isfinite(a)] = np.nan
    r = raw[ran].apply(pd.to_numeric, errors='coerce').to_numpy(dtype=np.float64)
    r[~np.isfinite(r)] = np.nan
    return dict(slot=slot, item=item, raw=a, ran=r, task=task)

def transform(a, scaler, minmax=False):
    valid=np.isfinite(a)
    filled=np.where(valid,a,np.asarray(scaler['median']))
    center=np.asarray(scaler['minimum' if minmax else 'mean']); scale=np.asarray(scaler['spread' if minmax else 'scale'])
    value=((filled-center)/scale).astype(np.float32)
    assert np.isfinite(value).all()
    return np.concatenate([value,(~valid).astype(np.float32)],1)

def load_samples(task,target,slots,scaler_key=None,fit_only=False):
    frames=[];xs=[]
    for slot in slots:
        f=pd.read_parquet(ROOT/f'outputs/indices/{task}_{target}_{slot}.parquet')
        if fit_only:f=f[f.window_all_clean].reset_index(drop=True)
        key=scaler_key or task
        a=np.load(ROOT/f'cache/{slot}/{key}.npy',mmap_mode='r')
        if key=='RAN':
            ids=f.cutoff_row.to_numpy()[:,None]+np.arange(-60,0)[None,:];xs.append(a[ids])
        else:xs.append(a[f.tensor_row.to_numpy()])
        frames.append(f)
    return np.concatenate(xs),pd.concat(frames,ignore_index=True)

def statistics(x):
    return np.concatenate([x.mean(1),x.std(1),x.min(1),x.max(1),x[:,-1],(x[:,-1]-x[:,0])/59.],1).astype(np.float32)

def schedule_table(frame):
    a=frame.anchor_row.to_numpy(dtype=np.float64); pieces=[a/86400.]
    for p in [600,900]: pieces.extend([np.sin(2*np.pi*(a%p)/p),np.cos(2*np.pi*(a%p)/p)])
    return np.column_stack(pieces).astype(np.float32)
