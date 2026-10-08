"""Replay the 15 packaged 12-class classifier artifacts."""
from pathlib import Path
import json, os, sys
import numpy as np
import pandas as pd
import torch, joblib
HERE=Path(__file__).resolve().parent; TOP=HERE.parents[2]
EVAL=TOP/'evaluation_package'/'evaluation'; R=EVAL/'localization'; DATA=TOP/'data_machine'/'dataset'/'task_data'
OUT=HERE/'results'/'localization';OUT.mkdir(parents=True,exist_ok=True)
os.environ['DGATE_LOCALIZATION_DATA_PACKAGE']=str(DATA)
sys.path.insert(0,str(R/'code'))
from pipeline import CLASSES, MECH, TARGET, MODELS, SEEDS, load, inputs, SequenceClassifier
from verify_results import independent
f,v,mask,names=load(); saved_metrics=pd.read_csv(R/'metrics/ALL_METRICS.csv'); paper_evidence=pd.read_csv(EVAL/'evidence/localization_metrics.csv')
checks=[];per_cell=[];max_probability=0.;max_metric=0.;pred_equal=0
for kind in MODELS:
    x=inputs(v,mask,names,kind)
    for seed in SEEDS:
        ident=f'{kind}__seed{seed}';d=pd.read_parquet(R/'predictions'/f'{ident}.parquet')
        assert len(d)==612 and d.sample_id.astype(str).tolist()==f.sample_id.astype(str).tolist()
        expected=d[[f'p_{j:02d}' for j in range(12)]].to_numpy(float)
        modelpath=R/'models'/ident/('checkpoint.pt' if kind in ('LSTM','TCN') else 'model.joblib')
        if kind in ('LSTM','TCN'):
            model=SequenceClassifier(kind,48,12).cuda();model.load_state_dict(torch.load(modelpath,map_location='cuda',weights_only=True));model.eval()
            with torch.inference_mode(): got=np.concatenate([model(torch.tensor(a,device='cuda')).softmax(1).cpu().numpy() for a in np.array_split(x,6)])
        else: got=joblib.load(modelpath).predict_proba(x)
        diff=np.abs(got-expected);md=float(diff.max());max_probability=max(max_probability,md)
        assert got.shape==(612,12) and np.isfinite(got).all() and np.all(got>=0) and np.allclose(got.sum(1),1,atol=1e-6)
        assert np.allclose(got,expected,rtol=1e-6,atol=2e-6),(ident,md)
        classmap={c:i for i,c in enumerate(CLASSES)};pred=got.argmax(1);stored=d.predicted_class.map(classmap).to_numpy();pred_equal+=int(np.sum(pred==stored))
        assert np.array_equal(pred,stored)
        for row in saved_metrics[(saved_metrics.model==kind)&(saved_metrics.seed==seed)].itertuples():
            ii=(d.effective_split.eq(row.role)|d.slot.eq(row.role))&d.class_id.ge(0)
            if row.stratum=='network': ii &= d.mechanism.ne('instance-stop')
            elif row.stratum!='all': ii &= d.mechanism.eq(row.stratum)
            ids=np.flatnonzero(ii.to_numpy());y=d.class_id.iloc[ids].to_numpy(int)
            val,_=independent(y,got[ids],json.loads(row.f1_labels))
            for key in ['top1','macro_f1','mechanism_accuracy','target_accuracy']:
                err=abs(float(val[key])-float(getattr(row,key)));max_metric=max(max_metric,err);assert err<1e-7,(ident,row.role,row.stratum,key,err)
            per_cell.append({'model':kind,'seed':seed,'role':row.role,'stratum':row.stratum,'n':len(ids),**{k:float(val[k]) for k in ['top1','macro_f1','mechanism_accuracy','target_accuracy']}})
        checks.append({'model':kind,'seed':seed,'rows':len(d),'max_abs_probability_difference':md})
paper=[]
for row in paper_evidence.to_dict('records'):
    kind=row.get('Model');seed=int(row.get('seed',-1));z=next((q for q in per_cell if q['model']==kind and q['seed']==seed and q['role']=='test' and q['stratum']=='all'),None)
    if z is None:continue
    for col,metric in [('Fault_type_accuracy','mechanism_accuracy'),('Location_accuracy','target_accuracy'),('Joint_accuracy','top1'),('Macro_F1','macro_f1')]:
        if col in row and pd.notna(row[col]):
            err=abs(float(row[col])/100.-float(z[metric]));assert err<1e-12,(kind,seed,col,err);paper.append(err)
report={'status':'PASS','scope':'checkpoint-only replay over all 612 fixed windows; 5 models x 3 seeds; no fitting','models':len(checks),'rows_replayed':sum(x['rows'] for x in checks),'probability_elements':sum(x['rows']*12 for x in checks),'class_predictions_equal_rows':pred_equal,'max_abs_probability_difference':max_probability,'max_metric_difference':max_metric,'paper_metric_cells_checked':len(paper),'paper_metric_max_difference':max(paper,default=None),'tolerance':{'probability_rtol':1e-6,'probability_atol':2e-6,'metrics_abs':1e-7,'paper_abs':1e-12}}
(OUT/'REPLAY.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps(report,ensure_ascii=False))
