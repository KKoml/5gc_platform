"""Run fresh T1 training from bundled windows only; never touches D06/D07."""
from pathlib import Path
import argparse,hashlib,json,shutil,time,sys
import numpy as np,pandas as pd
import torch
HERE=Path(__file__).resolve().parent;TOP=HERE.parents[2];SRC=TOP/'evaluation_package'/'evaluation'/'prediction';INPUT=TOP/'prediction_inputs'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run-dir',required=True);ap.add_argument('--target',default='host_cpu',choices=['host_cpu','n3_downlink','n6_aggregate']);ap.add_argument('--model',default='XGBoost',choices=['PatchTST','TimeFilter','XGBoost']);a=ap.parse_args()
 run=Path(a.run_dir).resolve();root=run/'prediction'
 if run.exists() and any(run.iterdir()):raise FileExistsError(f'Use a new empty run directory: {run}')
 root.mkdir(parents=True,exist_ok=True)
 for rel in ['src','third_party','spec']:
  shutil.copytree(SRC/rel,root/rel,ignore=shutil.ignore_patterns('__pycache__','.git'))
 shutil.copy2(SRC/'resolved_config.yaml',root/'resolved_config.yaml')
 (root/'outputs'/'indices').mkdir(parents=True)
 shutil.copy2(SRC/'outputs/scalers.json',root/'outputs/scalers.json')
 for slot in ['D01','D02','D03','D04','D05']:
  shutil.copy2(SRC/f'outputs/indices/T1_{a.target}_{slot}.parquet',root/f'outputs/indices/T1_{a.target}_{slot}.parquet')
 sys.path.insert(0,str(root))
 from src import data as d,engine as e
 c=d.config();features=c['resolved']['features'];scalers=json.loads((root/'outputs/scalers.json').read_text())['T1'];input_checks=[]
 for slot in ['D01','D02','D03','D04','D05']:
  hist=pd.read_csv(INPUT/slot/'T1_history.csv.gz');rawwins=[];window_ids=[]
  for wid,g in hist.groupby('window_id',sort=False):
   assert len(g)==60 and np.array_equal(g.history_position.to_numpy(),np.arange(60))
   raw=g[features].apply(pd.to_numeric,errors='coerce').to_numpy(float);miss=g[[x+'__missing' for x in features]].to_numpy(np.int8)
   assert np.array_equal(miss,~np.isfinite(raw));assert np.array_equal(g.history_row_epoch.to_numpy(np.int64),g.anchor_epoch.iloc[0]+np.arange(-60,0))
   rawwins.append(raw);window_ids.append(str(wid))
  raw=np.stack(rawwins);norm=d.transform(raw.reshape(-1,len(features)),scalers).reshape(len(raw),60,36)
  cache=root/f'cache/{slot}';cache.mkdir(parents=True,exist_ok=True);np.save(cache/'T1_raw_windows.npy',raw);np.save(cache/'T1.npy',norm)
  ix=pd.read_parquet(root/f'outputs/indices/T1_{a.target}_{slot}.parquet');mapping={wid:i for i,wid in enumerate(window_ids)}
  assert np.array_equal(ix.window_id.astype(str).map(mapping).to_numpy(),ix.tensor_row.to_numpy())
  targ=pd.read_csv(INPUT/slot/'T1_targets.csv.gz');targ=targ[(targ.target_id==a.target)&(targ.eligible==1)].reset_index(drop=True)
  assert targ.window_id.astype(str).tolist()==ix.window_id.astype(str).tolist()
  input_checks.append({'slot':slot,'history_windows':len(raw),'eligible_target_rows':len(ix),'only_train_or_D05':True})
 start=time.time();torch.set_num_threads(4)
 e.develop_model(c,'T1',a.target,a.model);e.develop_model(c,'T1',a.target,a.model,final_only=True)
 recs=e.selected_records(c);assert recs and all(x['target']==a.target and x['model']==a.model for x in recs)
 files=[]
 for p in sorted((root/'outputs/jobs').rglob('*')):
  if p.is_file():files.append({'path':str(p.relative_to(root)),'sha256':sha(p),'bytes':p.stat().st_size})
 manifest={'run_id':'DGATE_T1_BUNDLE_TRAIN_'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()),'status':'DONE','task':'T1 forecast','target':a.target,'model':a.model,'seeds':[int(r['seed']) for r in recs],'fit_records':recs,'input_source':'only package prediction_inputs D01-D05; fit=D01-D04; model selection=D05; D06/D07 not copied into run directory or read','input_manifest_sha256':sha(INPUT/'INPUT_MANIFEST.json'),'code_sha256':{str(p.relative_to(root)):sha(p) for p in sorted((root/'src').glob('*.py'))},'input_checks':input_checks,'outputs':files,'wall_seconds':time.time()-start,'device':torch.cuda.get_device_name() if torch.cuda.is_available() else 'cpu','torch':torch.__version__}
 (run/'NEW_RUN_MANIFEST.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False,default=str)+'\n');print(json.dumps({'status':manifest['status'],'run_id':manifest['run_id'],'fit_records':len(recs),'seeds':manifest['seeds'],'wall_seconds':manifest['wall_seconds'],'run_dir':str(run)},ensure_ascii=False))
if __name__=='__main__':main()
