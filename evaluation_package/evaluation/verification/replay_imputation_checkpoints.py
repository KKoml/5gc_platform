"""Replay imputation checkpoints in a temporary copy and compare all saved outputs."""
from pathlib import Path
import json, os, shutil, subprocess, sys, tempfile
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;TOP=HERE.parents[2]
EVAL=TOP/'evaluation_package'/'evaluation';SRC=EVAL/'imputation';DATA=TOP/'data_machine'/'dataset'/'task_data'
OUT=HERE/'results'/'imputation';OUT.mkdir(parents=True,exist_ok=True)
need=['code','third_party','data','masks','checkpoints','metadata','fit_evidence','predictions','results']
with tempfile.TemporaryDirectory(prefix='dgate-imp-replay-') as td:
    work=Path(td)/'imputation'
    work.mkdir()
    for rel in need:
        p=SRC/rel
        if p.exists():
            q=work/rel
            if p.is_dir():shutil.copytree(p,q,ignore=shutil.ignore_patterns('__pycache__'))
            else:shutil.copy2(p,q)
    env=os.environ.copy();env['DGATE_DATASET_ROOT']=str(DATA.resolve());env['PYTHONPATH']=str(work/'third_party'/'SAITS')+os.pathsep+env.get('PYTHONPATH','');env['MPLCONFIGDIR']=str(Path(td)/'.mplconfig');Path(env['MPLCONFIGDIR']).mkdir(parents=True,exist_ok=True)
    def run(name):
        subprocess.run([sys.executable,'code/evaluate.py',name],cwd=work,env=env,check=True)
    run('evaluate');run('metrics')
    outputs=[];maxdiff=0.
    generated=pd.read_csv(work/'predictions/manifest.csv')
    for row in generated.itertuples():
        pnew=pd.read_parquet(work/row.path);pold=pd.read_parquet(SRC/row.path)
        assert list(pnew.columns)==list(pold.columns) and len(pnew)==len(pold),(row.path,'shape')
        for col in pnew.columns:
            if pd.api.types.is_numeric_dtype(pnew[col]):
                a=pnew[col].to_numpy();b=pold[col].to_numpy();d=np.abs(a-b);m=float(np.nanmax(d)) if len(d) else 0.;maxdiff=max(maxdiff,m)
                assert np.array_equal(a,b,equal_nan=True),(row.path,col,m)
            else:assert pnew[col].astype(str).tolist()==pold[col].astype(str).tolist(),(row.path,col)
        outputs.append(dict(path=row.path,rows=len(pnew),columns=len(pnew.columns)))
    newm=pd.read_csv(work/'results/metrics.csv');oldm=pd.read_csv(SRC/'results/metrics.csv')
    assert list(newm.columns)==list(oldm.columns) and len(newm)==len(oldm)
    numeric=newm.select_dtypes(include=[np.number]).columns
    for col in numeric:
        a=newm[col].to_numpy(float);b=oldm[col].to_numpy(float);d=np.abs(a-b);m=float(np.nanmax(d)) if len(d) else 0.;maxdiff=max(maxdiff,m);assert np.array_equal(a,b,equal_nan=True),(col,m)
    receipt={'status':'PASS','scope':'all six non-training evaluation slots; original checkpoints/config/masks; fresh extraction inputs; run outputs in temporary copy; packaged saved outputs read only','prediction_files':len(outputs),'prediction_rows':sum(x['rows'] for x in outputs),'metric_rows':len(newm),'max_abs_numeric_difference':maxdiff,'numeric_policy':'bitwise array equality including NaNs; no relaxed tolerance'}
(OUT/'REPLAY.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n');print(json.dumps(receipt,ensure_ascii=False))
