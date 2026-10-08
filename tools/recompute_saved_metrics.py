"""Recompute classification and imputation metrics from saved predictions only."""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from sklearn.metrics import f1_score

ROOT = Path(__file__).resolve().parents[1]
E = ROOT / 'evaluation_package/evaluation'
OUT = ROOT / 'checks/current'

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    lc = E / 'localization'
    expected = pd.read_csv(lc / 'metrics/ALL_METRICS.csv', float_precision='round_trip')
    rows = []
    for path in sorted((lc/'predictions').glob('*.parquet')):
        d = pd.read_parquet(path); d = d[d.effective_split.eq('test')]
        assert len(d) == 144 and d.sample_id.nunique() == 144
        p = d[[f'p_{i:02}' for i in range(12)]].to_numpy(float)
        y = d.class_id.to_numpy(int); pred = p.argmax(1)
        metrics = {'top1':float((pred==y).mean()), 'macro_f1':f1_score(y,pred,labels=list(range(12)),average='macro',zero_division=0), 'mechanism_accuracy':float((p.reshape(-1,6,2).sum(2).argmax(1)==y//2).mean()), 'target_accuracy':float((p.reshape(-1,6,2).sum(1).argmax(1)==y%2).mean())}
        model, seed = d.model.iloc[0], int(d.seed.iloc[0])
        ref = expected[(expected.model==model)&(expected.seed==seed)&expected.role.eq('test')&expected.stratum.eq('all')]
        assert len(ref)==1
        delta = max(abs(v-float(ref.iloc[0][k])) for k,v in metrics.items())
        assert delta < 1e-12
        rows.append(dict(model=model,seed=seed,max_abs_difference=delta,**metrics))
    pd.DataFrame(rows).to_csv(OUT/'classification_recomputed.csv',index=False)
    imp = E/'imputation'; manifest = pd.read_csv(imp/'predictions/manifest.csv')
    expected = pd.read_csv(imp/'results/metrics.csv',float_precision='round_trip')
    scales = np.load(imp/'metadata/scales.npz')['std'][[16,17,12]]
    counts=0; maxdiff=0.; table=[]
    for m in manifest.itertuples():
        truth=pd.read_parquet(imp/f'predictions/{m.slot}_truth.parquet'); pred=pd.read_parquet(imp/m.path)
        assert len(truth)==len(pred)==m.rows
        err=pred.prediction.to_numpy(float)-truth.truth.to_numpy(float)
        factors=np.array([1e6,1e6,1.])[truth.target]
        truth['mae']=np.abs(err)/factors;truth['mse']=(err/factors)**2
        truth['nmae']=np.abs(err)/scales[truth.target];truth['nmse']=(err/scales[truth.target])**2
        for strat,col in [('all',None),('phase','phase'),('change','change')]:
            keys=['target','condition','mask_seed']+([col] if col else [])
            got=truth.groupby(keys,observed=True).agg(n=('mae','size'),mae=('mae','mean'),mse=('mse','mean'),nmae=('nmae','mean'),nmse=('nmse','mean')).reset_index()
            got['stratum']=got[col].astype(str) if col else 'all'
            got['rmse']=np.sqrt(got.mse);got['nrmse']=np.sqrt(got.nmse)
            ref=expected[expected.slot.eq(m.slot)&expected.method.eq(m.method)&expected.model_seed.eq(m.seed)&expected.stratification.eq(strat)]
            z=got.merge(ref,on=['target','condition','mask_seed','stratum'],suffixes=('_got','_saved'),validate='one_to_one')
            assert len(z)==len(got)==len(ref)
            assert np.array_equal(z.n_got,z.n_saved)
            delta=max(float(np.abs(z[k+'_got']-z[k+'_saved']).max()) for k in ['mae','rmse','nmae','nrmse'])
            assert delta<1e-10,(m.path,strat,delta)
            maxdiff=max(maxdiff,delta);counts+=len(z)
        table.append(dict(path=m.path,slot=m.slot,method=m.method,seed=int(m.seed),rows=len(pred)))
    report={'status':'PASS','scope':'saved predictions only; no inference or training', 'classification_model_seed_rows':len(rows),'classification_metric_cells':4*len(rows),'imputation_prediction_files':len(table),'imputation_metric_rows':counts,'imputation_max_abs_difference':maxdiff}
    (OUT/'saved_metrics.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))

if __name__=='__main__': main()
