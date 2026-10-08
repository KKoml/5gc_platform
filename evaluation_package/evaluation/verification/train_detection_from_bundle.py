"""Fresh normal-only FD fit, D05 calibration, then optional frozen-threshold test."""
from pathlib import Path
import argparse,hashlib,json,os,sys,time
import numpy as np,pandas as pd
HERE=Path(__file__).resolve().parent;TOP=HERE.parents[2];EVAL=TOP/'evaluation_package'/'evaluation';DET=EVAL/'detection';DATA=TOP/'data_machine'/'dataset'/'task_data'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--run-dir',required=True);ap.add_argument('--model',default='AE',choices=['AE','KAN-AD','TranAD_adapted_v2']);ap.add_argument('--seed',type=int,default=17,choices=[17,29,43]);ap.add_argument('--skip-test',action='store_true');ap.add_argument('--reuse-completed-fit',action='store_true',help='continue only post-fit validation/test after a completed fit in this new run directory');a=ap.parse_args()
 run=Path(a.run_dir).resolve();out=run/'fit'
 if run.exists() and any(run.iterdir()) and not a.reuse_completed_fit:raise FileExistsError(f'Use a new empty run directory: {run}')
 out.mkdir(parents=True,exist_ok=a.reuse_completed_fit);sys.path.insert(0,str(DET))
 from normal_only import train
 from normal_only.data import PackageData
 from normal_only.evaluation import calibrate_thresholds,evaluate_binary
 src=DET/'normal_only'/'fits'/f'm2__FD_detection__FD_detection_24__{a.model.replace("-","_")}__seed{a.seed}'
 if not src.exists():
  candidates=sorted((DET/'normal_only'/'fits').glob(f'*__FD_detection__FD_detection_24__{a.model}__seed{a.seed}'))
  if not candidates:raise FileNotFoundError(f'No bundled preprocessor for {a.model} seed {a.seed}')
  src=candidates[0]
 cfg=json.loads((src/'experiment_config.json').read_text());package=str(DATA.resolve());feature_set=cfg['feature_set'];pp=src/'preprocessing.json'
 start=time.time()
 new=out/'trained_fit'
 # Fit function uses only train_index and D05 selection_index, and saves the fresh checkpoint under this new directory.
 if a.reuse_completed_fit:
  if not (new/'checkpoint.pt').exists() and not (new/'checkpoint.pkl').exists():raise FileNotFoundError(f'No completed checkpoint under {new}')
  fit_stage='existing isolated fit reused after wrapper post-processing correction'
 else:
  # Fit function uses only train_index and D05 selection_index, and saves the fresh checkpoint under this new directory.
  train.fit_deep(package,cfg['task'],a.model,a.seed,feature_set,pp,new,device='cuda',max_epochs=int(cfg.get('max_epochs',50)),patience=int(cfg.get('early_stopping_patience',8)))
  fit_stage='trained by this invocation'
 runtime=json.loads((new/'experiment_config.json').read_text());runtime['package_root']=package;(new/'experiment_config.json').write_text(json.dumps(runtime,indent=2)+'\n')
 d=PackageData(DATA);val=pd.read_parquet(train.predict_job(new,'validation',device='cuda'))
 rids=d.runs.loc[d.runs.split.eq('validation'),'run_id'].astype(str);events=d.episodes[d.episodes.run_id.astype(str).isin(set(rids))];eligible=d.evaluability[d.evaluability.run_id.astype(str).isin(set(rids))]
 thresholds=calibrate_thresholds(val,events,cfg['task'],budgets=[0.1,1.0],event_evaluability=eligible);(new/'thresholds').mkdir(exist_ok=True);(new/'thresholds/D05_replay.json').write_text(json.dumps(thresholds,indent=2,ensure_ascii=False)+'\n')
 metrics=[]
 if not a.skip_test:
  rids=d.runs.loc[d.runs.split.eq('test'),'run_id'].astype(str);events=d.episodes[d.episodes.run_id.astype(str).isin(set(rids))];eligible=d.evaluability[d.evaluability.run_id.astype(str).isin(set(rids))];test=pd.read_parquet(train.predict_job(new,'test',device='cuda'))
  for budget in ['0.1','1.0']:
   score=evaluate_binary(test,events,float(thresholds[str(float(budget))]['threshold']),cfg['task'],event_evaluability=eligible)['metrics'];metrics.append({'budget':float(budget),'event_recall_all_main':score['event_recall_all_main'],'false_alerts_per_hour':score['false_alerts_per_hour'],'first_detection_delay_median_seconds':score['first_detection_delay_median_seconds']})
 runinfo={'run_id':f'DGATE_FD_BUNDLE_{a.model}_{a.seed}_{time.strftime("%Y%m%dT%H%M%SZ",time.gmtime())}','status':'DONE','model':a.model,'seed':a.seed,'fit_execution':fit_stage,'fit_split':'D01-D04','selection_split':'D05 only','threshold_split':'D05 only','test_evaluation':'skipped' if a.skip_test else 'post-hoc only; previously accessed D06-D07; no model/threshold selection','training_config':runtime,'training_config_sha256':sha(new/'experiment_config.json'),'checkpoint_sha256':sha(new/'checkpoint.pt') if (new/'checkpoint.pt').exists() else sha(new/'checkpoint.pkl'),'fit_seconds':runtime.get('fit_seconds',runtime.get('training_seconds')),'peak_gpu_allocated_bytes':runtime.get('peak_gpu_allocated_bytes'),'validation_thresholds':thresholds,'test_metrics':metrics,'input_task_manifest_sha256':sha(DATA/'SHA256SUMS.txt'),'package_code_sha256':{str(p.relative_to(DET/'normal_only')):sha(p) for p in sorted((DET/'normal_only').glob('*.py'))},'elapsed_seconds':time.time()-start}
 (run/'NEW_RUN_MANIFEST.json').write_text(json.dumps(runinfo,indent=2,ensure_ascii=False,default=str)+'\n');print(json.dumps({'status':runinfo['status'],'run_id':runinfo['run_id'],'model':a.model,'seed':a.seed,'elapsed_seconds':runinfo['elapsed_seconds'],'run_dir':str(run)},ensure_ascii=False))
if __name__=='__main__':main()
