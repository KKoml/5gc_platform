"""New V2 rule and native ARIMA predictions, never imported historical scores."""
import json
import time
import warnings
import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from . import data as d,engine as e

def rules(raw,frame,j,median):
    output={k:[] for k in ['Persistence','RecentMean10','Seasonal600','Seasonal900']}
    for cutoff in frame.cutoff_row:
        hist=raw[cutoff-60:cutoff,j];finite=hist[np.isfinite(hist)]
        last=float(finite[-1]) if len(finite) else median;output['Persistence'].append(last)
        short=hist[-10:];short=short[np.isfinite(short)];output['RecentMean10'].append(float(short.mean()) if len(short) else last)
        for lag in [600,900]:
            start=cutoff+60-lag
            past=raw[start:start+10,j] if start>=0 else np.array([])
            valid=past[np.isfinite(past)];output[f'Seasonal{lag}'].append(float(valid.mean()) if len(valid) else last)
    return {k:np.array(v) for k,v in output.items()}

def causal_log(raw,fallback):
    return pd.Series(np.log1p(raw)).replace([np.inf,-np.inf],np.nan).ffill().fillna(fallback).to_numpy()

def fit_arima(c,target,smoke=False):
    path=e.OUT/'baselines'/f'ARIMA_{target}.json'
    if path.exists() and not smoke:return json.loads(path.read_text())
    j,_,_=e.target_stats(c,target);all_train=[np.load(d.ROOT/f'cache/{s}/raw.npy',mmap_mode='r')[:,j] for s in ['D01','D02','D03','D04']]
    finite=np.concatenate(all_train);fallback=float(np.nanmedian(np.log1p(finite[np.isfinite(finite)])))
    native=c['resolved']['arima_native'];order=native['order'];candidates=[];start=time.perf_counter()
    for slot,raw in zip(['D01','D02','D03','D04'],all_train):
        if smoke and slot!='D01':break
        series=causal_log(raw,fallback)[-min(native['training_tail_rows'],2000 if smoke else native['training_tail_rows']):]
        t=time.perf_counter()
        with warnings.catch_warnings(record=True) as ws:
            result=ARIMA(series,order=order,trend='t',enforce_stationarity=False,enforce_invertibility=False).fit()
        candidates.append(dict(slot=slot,aic=float(result.aic),params=result.params.tolist(),fit_seconds=time.perf_counter()-t,
            optimizer_converged=bool(result.mle_retvals.get('converged',False)),warnings=[str(w.message) for w in ws]))
    selected=min(candidates,key=lambda a:a['aic'])
    r=dict(target=target,model='ARIMA',seed=42,task='T1',status='completed',spec=dict(id='ARIMA',panel='U_extended_access'),
        native_transform='causal log1p forward fill; stepwise expm1 then mean; no z-score',order=order,trend='t',fallback=fallback,
        selected=selected,candidates=candidates,selection='minimum training AIC among four independent train-tail fits; native exception',
        total_fit_seconds=time.perf_counter()-start,config_hash=e.cfg_hash([native,target,selected]),test_status='post_hoc')
    if not smoke:d.json_write(path,r)
    return r

def arima_prediction(raw,frame,r,j):
    # Fixed-parameter forward filter is causal; use no smoother or parameter update.
    # Dynamic predictions start exactly at cutoff, before any target/gap truth is assimilated.
    series=causal_log(raw[:,j],r['fallback'])
    result=ARIMA(series,order=r['order'],trend='t',enforce_stationarity=False,enforce_invertibility=False).filter(np.array(r['selected']['params']))
    output=[]
    for cutoff in frame.cutoff_row:
        p=np.asarray(result.get_prediction(start=int(cutoff),end=int(cutoff+69),dynamic=True).predicted_mean)
        output.append(float(np.maximum(np.expm1(p[60:70]),0).mean()))
    output=np.array(output)
    if not np.isfinite(output).all():raise FloatingPointError('ARIMA nonfinite; no sample drop')
    return output

def smoke(c):
    target='n3_downlink';j,_,_=e.target_stats(c,target);t=time.perf_counter();r=fit_arima(c,target,smoke=True)
    raw=np.load(d.ROOT/'cache/D05/raw.npy');f=pd.read_parquet(e.OUT/'indices/T1_n3_downlink_D05.parquet').iloc[:4]
    t2=time.perf_counter();p=arima_prediction(raw[:1000],f,r,j);seconds=time.perf_counter()-t2
    changed=raw[:1000].copy();changed[int(f.iloc[0].cutoff_row):]=1e6
    q=arima_prediction(changed,f.iloc[:1],r,j)
    np.testing.assert_allclose(p[:1],q,rtol=1e-8,atol=1e-8)
    sc=json.loads((e.OUT/'scalers.json').read_text())['T1'];out=rules(raw,f,j,sc['median'][j]);assert all(len(a)==len(f) for a in out.values())
    record=dict(native_arima_smoke_seconds=time.perf_counter()-t,fit_seconds=r['total_fit_seconds'],four_window_inference_seconds=seconds,
        causal_future_suffix_test='passed',native_convergence=r['selected']['optimizer_converged'])
    d.json_write(e.OUT/'baseline_smoke.json',record);print(record,flush=True)

def evaluate(c):
    assert (e.OUT/'SELECTION_FROZEN.json').exists()
    scalers=json.loads((e.OUT/'scalers.json').read_text())['T1']
    for target in [t['id'] for t in c['data']['targets']]:
        j,_,_=e.target_stats(c,target);ar=fit_arima(c,target)
        for slot in ['D05','D06','D07']:
            raw=np.load(d.ROOT/f'cache/{slot}/raw.npy');f=pd.read_parquet(e.OUT/f'indices/T1_{target}_{slot}.parquet')
            t=time.perf_counter();out=rules(raw,f,j,scalers['median'][j]);elapsed=time.perf_counter()-t
            for name,p in out.items():
                r=dict(task='T1',target=target,model=name,seed=42,config_hash=e.cfg_hash([name,target,60,60,10]),spec=e.spec_for(c,'T1',name))
                e.save_predictions(c,r,f,p,elapsed/len(out))
            path=e.OUT/'predictions'/f'T1_{target}_ARIMA_seed42_{slot}.parquet'
            if not path.exists():
                t=time.perf_counter();p=arima_prediction(raw,f,ar,j);e.save_predictions(c,ar,f,p,time.perf_counter()-t)
            print(json.dumps(dict(event='baseline_predictions_written',target=target,slot=slot)),flush=True)

if __name__=='__main__':smoke(d.config())
