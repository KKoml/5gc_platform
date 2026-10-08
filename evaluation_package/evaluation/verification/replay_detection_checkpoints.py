"""Replay packaged detection checkpoints into separate generated output."""
from pathlib import Path
import json, shutil, sys, time
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent; TOP=HERE.parents[2]
EVAL=TOP/'evaluation_package'/'evaluation'; DET=EVAL/'detection'; DATA=TOP/'data_machine'/'dataset'/'task_data'
OUT=HERE/'results'/'detection'; WORK=OUT/'work'; OUT.mkdir(parents=True,exist_ok=True)
normal=DET/'normal_only'; sys.path.insert(0,str(normal.parent))
from normal_only import train
records=[]
for cp in sorted(normal.glob('fits/*/experiment_config.json')):
    src=cp.parent; job=WORK/'normal_only'/src.name
    if job.exists(): shutil.rmtree(job)
    job.parent.mkdir(parents=True,exist_ok=True); shutil.copytree(src,job,ignore=shutil.ignore_patterns('__pycache__'))
    cfg=json.loads((job/'experiment_config.json').read_text());cfg['package_root']=str(DATA.resolve());(job/'experiment_config.json').write_text(json.dumps(cfg,indent=2)+'\n')
    for split in ['validation','test']:
        start=time.time();dest=train.predict_job(job,split,device='cuda');new=pd.read_parquet(dest)
        old=pd.read_parquet(src/'predictions'/f'{split}.parquet')
        assert new.sample_id.astype(str).tolist()==old.sample_id.astype(str).tolist(),(src.name,split,'ids')
        assert np.array_equal(new.y_true.to_numpy(),old.y_true.to_numpy()),(src.name,split,'labels')
        assert np.array_equal(new.prediction_valid.to_numpy(),old.prediction_valid.to_numpy()),(src.name,split,'validity')
        diff=np.abs(new.score.to_numpy(float)-old.score.to_numpy(float))
        assert np.allclose(new.score.to_numpy(float),old.score.to_numpy(float),rtol=1e-6,atol=2e-6),(src.name,split,float(diff.max()))
        records.append(dict(model=cfg['model'],seed=cfg['seed'],split=split,n=len(new),max_abs=float(diff.max()),seconds=time.time()-start))
        print(json.dumps(records[-1]),flush=True)
report={'status':'PASS','rows':records,'count':len(records),'max_score_abs_difference':max(x['max_abs'] for x in records),'tolerance':{'rtol':1e-6,'atol':2e-6},'scope':'normal-only FD models AE,KAN-AD,TranAD; seeds 17,29,43; D05,D06-D07 scores; no fitting; saved artifacts were read only'}
(OUT/'NORMAL_ONLY_REPLAY.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
shutil.rmtree(WORK,ignore_errors=True)
print(json.dumps(report,ensure_ascii=False))
