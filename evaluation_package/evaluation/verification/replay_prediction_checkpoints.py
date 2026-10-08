"""Replay packaged T1 checkpoints/estimators without overwriting saved outputs."""
from pathlib import Path
import atexit, json, shutil, sys
import numpy as np
import pandas as pd
import torch
HERE=Path(__file__).resolve().parent
TOP=HERE.parents[2]
EVAL=TOP/'evaluation_package'/'evaluation'
PKG=EVAL/'prediction'
INPUT=TOP/'prediction_inputs'
OUT=HERE/'results'/'prediction'
OUT.mkdir(parents=True,exist_ok=True)
CACHE=PKG/'cache'
if CACHE.exists(): raise RuntimeError(f'Remove pre-existing generated cache before replay: {CACHE}')
def cleanup_cache(): shutil.rmtree(CACHE,ignore_errors=True)
atexit.register(cleanup_cache)
sys.path.insert(0,str(PKG))
from src import data as d, engine as e
c=d.config(); features=c['resolved']['features']; saved_root=PKG/'outputs'
scalers=json.loads((saved_root/'scalers.json').read_text())['T1']
checks=[]
for slot in [f'D{i:02}' for i in range(1,8)]:
    hist=pd.read_csv(INPUT/slot/'T1_history.csv.gz')
    required=['window_id','history_position','history_row_epoch','anchor_epoch']+features+[x+'__missing' for x in features]
    assert set(required)<=set(hist.columns)
    grouped=[];ids=[]
    for wid,g in hist.groupby('window_id',sort=False):
        assert len(g)==60 and np.array_equal(g.history_position.to_numpy(),np.arange(60)),(slot,wid)
        ep=g.history_row_epoch.to_numpy(dtype=np.int64);anc=g.anchor_epoch.to_numpy(dtype=np.int64)
        assert np.array_equal(ep,anc[0]+np.arange(-60,0)) and np.all(anc==anc[0]),(slot,wid,'time')
        raw=g[features].apply(pd.to_numeric,errors='coerce').to_numpy(dtype=np.float64)
        missing=g[[x+'__missing' for x in features]].to_numpy(dtype=np.int8)
        assert np.array_equal(missing,~np.isfinite(raw)),(slot,wid,'mask')
        grouped.append(raw);ids.append(str(wid))
    raw_arr=np.stack(grouped)
    normalized=d.transform(raw_arr.reshape(-1,len(features)),scalers).reshape(len(ids),60,36)
    cache=PKG/'cache'/slot;cache.mkdir(parents=True,exist_ok=True)
    np.save(cache/'T1_raw_windows.npy',raw_arr);np.save(cache/'T1.npy',normalized)
    id_to_row={wid:i for i,wid in enumerate(ids)}
    targets=[]
    for target in [x['id'] for x in c['data']['targets']]:
        index_path=saved_root/f'indices/T1_{target}_{slot}.parquet'
        if not index_path.exists(): continue
        ix=pd.read_parquet(index_path)
        expect=ix.window_id.astype(str).map(id_to_row).to_numpy()
        assert np.array_equal(expect,ix.tensor_row.to_numpy()),(slot,target,'tensor row ordering')
        targ=pd.read_csv(INPUT/slot/'T1_targets.csv.gz')
        targ=targ[targ.target_id.eq(target)&targ.eligible.eq(1)].reset_index(drop=True)
        assert targ.window_id.astype(str).tolist()==ix.window_id.astype(str).tolist(),(slot,target,'target order')
        diff=np.abs(targ.target_mean.to_numpy(float)-ix.label.to_numpy(float))
        assert np.all(diff<=2e-8+2e-15*np.abs(ix.label.to_numpy(float))), (slot,target,float(diff.max()))
        targets.append(target)
    checks.append(dict(slot=slot,history_windows=len(ids),history_rows=len(hist),mask_and_time_check=True,targets=targets))
records=[]
for r in e.selected_records(c):
    if r['task']!='T1' or r['target'] not in {'host_cpu','n3_downlink','n6_aggregate'}: continue
    model=e.load_record_model(c,r)
    for slot in ['D06','D07']:
        x,f=d.load_samples(r['task'],r['target'],[slot])
        if r['spec'].get('panel')=='U': x=x[..., [r['info']['target_index']]]
        got=e.validation_predict(c,r['task'],r['spec'],model,x,f,r['info'])
        expected=pd.read_parquet(saved_root/f'predictions/T1_{r["target"]}_{r["model"]}_seed{r["seed"]}_{slot}.parquet')
        assert expected.sample_id.astype(str).tolist()==f.sample_id.astype(str).tolist()
        assert np.array_equal(expected.label.to_numpy(float),f.label.to_numpy(float))
        delta=np.abs(got-expected.prediction.to_numpy(float))
        assert np.allclose(got,expected.prediction.to_numpy(float),rtol=1e-6,atol=2e-6),(r['target'],r['model'],r['seed'],slot,float(delta.max()))
        mae=float(np.mean(np.abs(got-f.label.to_numpy(float))))
        saved_mae=float(np.mean(np.abs(expected.prediction.to_numpy(float)-expected.label.to_numpy(float))))
        records.append(dict(target=r['target'],model=r['model'],seed=r['seed'],slot=slot,n=len(f),max_abs=float(delta.max()),mae=mae,saved_mae=saved_mae,mae_abs_diff=abs(mae-saved_mae)))
    del model;torch.cuda.empty_cache()
report=dict(status='PASS',input_checks=checks,checkpoint_rows=records,checkpoint_row_count=len(records),max_prediction_abs_difference=max(x['max_abs'] for x in records),tolerance={'rtol':1e-6,'atol':2e-6},scope='three published T1 targets; PatchTST, TimeFilter, XGBoost; seeds 42,43,44; D06,D07; saved files read only')
(OUT/'REPLAY.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
cleanup_cache()
print(json.dumps(report,ensure_ascii=False))
