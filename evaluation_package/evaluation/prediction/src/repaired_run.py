"""Isolated paper-scoped rerun: smoke, development freeze, test, delivery."""
import os,json,time,copy,traceback,gc,fcntl,zipfile,argparse
from pathlib import Path
import numpy as np
import pandas as pd
import torch
from . import data as d,engine as e,baselines as b,report
OUT=d.ROOT/'outputs'

def status(stage,**kw):
 p=OUT/'pipeline_status.json';s=json.loads(p.read_text()) if p.exists() else {}
 s.update(stage=stage,updated_at=time.time(),pid=os.getpid(),**kw);d.json_write(p,s)

def fail(branch,ex):
 p=OUT/'branch_failures.json';rows=json.loads(p.read_text()) if p.exists() else []
 rows.append(dict(branch=branch,error=str(ex),traceback=traceback.format_exc(),time=time.time()));d.json_write(p,rows)
 print('BRANCH_FAILURE',branch,str(ex),flush=True)

def smoke(c):
 assert torch.cuda.is_available();torch.manual_seed(42)
 z=torch.randn(128,128,device='cuda');assert torch.isfinite(z@z).all();torch.cuda.synchronize()
 rows=[]
 for task,names in [('T1',['PatchTST','TimeFilter','XGBoost']),('T2',['PCA','IsolationForest','AE','TranAD','KANAD'])]:
  target='n6_aggregate' if task=='T1' else 'command_overlap'
  for name in names:
   started=time.perf_counter();row=dict(task=task,model=name,target=target)
   try:
    spec=e.spec_for(c,task,name);x,f,v,vf,info=e.load_development(c,task,target,spec)
    fulltrain=len(x);fullval=int(vf.window_all_clean.sum()) if task=='T2' else len(v)
    n=min(len(x),1024);nv=min(len(v),1024);x=x[:n];f=f.iloc[:n];v=v[:nv];vf=vf.iloc[:nv]
    hp=spec['search'][0];small=copy.deepcopy(spec)
    if name=='XGBoost':small['architecture']['n_estimators']=10
    if name=='IsolationForest':small['n_estimators']=10
    if name in e.NEURAL:model,timing=e.train_neural(c,task,target,small,hp,42,x,f,v,vf,info,None,smoke=True)
    else:model,timing=e.fit_estimator(c,task,small,hp,42,x,f,info,None,smoke=True)
    pred=e.validation_predict(c,task,small,model,v,vf,info)
    assert pred.shape==(len(vf),) and np.isfinite(pred).all()
    row.update(passed=True,smoke_fit_seconds=timing['total_fit_seconds'],peak_gpu_bytes=timing['peak_gpu_allocated_bytes'])
    if name in e.NEURAL:
     h=timing['history'];pertrain=np.mean([a['train_seconds'] for a in h])*fulltrain/n
     perval=np.mean([a['validation_seconds'] for a in h])*fullval/(int(vf.window_all_clean.sum()) if task=='T2' else len(v))
     row['estimated_full_epoch_seconds']=float(pertrain+perval);row['max_epoch_fit_seconds']=float((pertrain+perval)*c[task.lower()]['training']['max_epochs'])
    del model,x,v;gc.collect();torch.cuda.empty_cache()
   except Exception as ex:row.update(passed=False,error=str(ex),traceback=traceback.format_exc())
   row['wall_seconds']=time.perf_counter()-started;rows.append(row);d.json_write(OUT/'SMOKE.json',rows);print('SMOKE',json.dumps(row),flush=True)
 # Check every target's scale/inverse and the two supervised probe feature interfaces.
 for target in [t['id'] for t in c['data']['targets']]:
  j,mean,scale=e.target_stats(c,target);assert np.isfinite([mean,scale]).all() and scale>0
  x,f=d.load_samples('T1',target,['D05']);assert np.isfinite(x).all()
  for view in ['M','schedule_only','target_history_and_mask']:
   assert np.isfinite(e.table(x[:8],f.iloc[:8],view,j)).all()
  y=f.label.to_numpy();np.testing.assert_allclose(((y-mean)/scale)*scale+mean,y,rtol=1e-12,atol=1e-7)
 upper=sum(r.get('max_epoch_fit_seconds',0)*(16 if r['task']=='T1' else 4) for r in rows)
 d.json_write(OUT/'TIME_ESTIMATE.json',dict(neural_max_epoch_serial_hours=upper/3600,scope='linear extrapolation of two smoke epochs; 2 candidates plus 2 selected seeds, four T1 targets; excludes CPU ARIMA, tree fits, IO and final inference',not_completion_promise=True,measurements=rows))
 if not any(r['passed'] for r in rows):raise RuntimeError('All smoke branches failed')
 return {(r['task'],r['model']) for r in rows if r['passed']}

def develop(c,passed):
 for task,names in [('T1',['XGBoost','PatchTST','TimeFilter']),('T2',['PCA','IsolationForest','AE','TranAD','KANAD'])]:
  for target in ([t['id'] for t in c['data']['targets']] if task=='T1' else ['command_overlap']):
   for name in names:
    if (task,name) not in passed:continue
    status('training',status='running',current=dict(task=task,target=target,model=name))
    try:e.develop_model(c,task,target,name);e.develop_model(c,task,target,name,final_only=True)
    except Exception as ex:fail(f'{task}:{target}:{name}',ex)
    gc.collect();torch.cuda.empty_cache()
 records=e.selected_records(c)
 for target in [t['id'] for t in c['data']['targets']]:
  try:
   q=e.selection_file('T1',target,'XGBoost')
   if not q.exists():continue
   winner=json.loads(q.read_text())['winner'];base=winner['spec'];x,f,v,vf,info=e.load_development(c,'T1',target,base)
   for view in ['target_history_and_mask','schedule_only']:
    spec={**base,'id':'XGBoost_'+view,'panel':'Supervised diagnostic','diagnostic_view':view}
    for seed in [42,43,44]:
     r=e.fit_one(c,'T1',target,spec,winner['hp'],seed,f'T1_{target}_{spec["id"]}_seed{seed}',x,f,v,vf,info)
     if r['status']=='completed':records.append(r)
   del x,v;gc.collect()
  except Exception as ex:fail(f'T1:{target}:diagnostics',ex)
 info=dict(target_index=0,target_mean=0.,target_scale=1.,model_target_index=0)
 for view in ['missingness_only','RAN_only']:
  try:
   key='RAN' if view=='RAN_only' else 'T2';x,f=d.load_samples('T2','command_overlap',c['data']['split']['train'],key);v,vf=d.load_samples('T2','command_overlap',['D05'],key)
   spec=dict(id='XGBoost_'+view,panel='Supervised diagnostic',diagnostic_view=view,architecture=dict(n_estimators=300,learning_rate=.04,max_depth=4,min_child_weight=3,subsample=.9,colsample_bytree=.9))
   for seed in [42,43,44]:
    r=e.fit_one(c,'T2','command_overlap',spec,{},seed,f'T2_command_overlap_{spec["id"]}_seed{seed}',x,f,v,vf,info)
    if r['status']=='completed':records.append(r)
   del x,v;gc.collect()
  except Exception as ex:fail('T2:'+view,ex)
 # Schedule lookup requires known training labels, never test labels.
 f=pd.concat([pd.read_parquet(OUT/f'indices/T2_command_overlap_{s}.parquet') for s in c['data']['split']['train']]);vf=pd.read_parquet(OUT/'indices/T2_command_overlap_D05.parquet')
 residue=f.anchor_row.to_numpy()%900;rate=float(f.label.mean());count=np.bincount(residue,minlength=900);positive=np.bincount(residue,weights=f.label,minlength=900);prob=(positive+rate)/(count+1.)
 thr,_=e.threshold(vf.label,prob[vf.anchor_row.to_numpy()%900]);spec=dict(id='ScheduleResidue900',panel='Supervised diagnostic')
 schedule=dict(task='T2',target='command_overlap',model='ScheduleResidue900',seed=42,spec=spec,threshold=thr,probability=prob.tolist(),config_hash=e.cfg_hash([prob.tolist(),thr]),status='completed',device='cpu')
 d.json_write(OUT/'diagnostics/schedule_residue.json',schedule)
 return records,schedule

def arima_develop(c):
 records=[]
 d.json_write(OUT/'ARIMA_BLOCKED.json',dict(targets=['n6_aggregate','flow_rtt_proxy'],status='blocked_missing_cutoff_valid_extended_context',other_methods_unblocked=True))
 for target in ['n3_downlink','host_cpu']:
  try:
   status('arima_development',current=dict(task='T1',target=target,model='ARIMA'))
   r=b.fit_arima(c,target);j,_,_=e.target_stats(c,target)
   raw=np.load(d.ROOT/'cache/D05/raw.npy');f=pd.read_parquet(OUT/f'indices/T1_{target}_D05.parquet')
   scores=[]
   for cand in r['candidates']:
    rr={**r,'selected':cand};pred=b.arima_prediction(raw,f,rr,j);cand['validation_MAE']=float(np.abs(pred-f.label.to_numpy()).mean());scores.append(cand)
   r['selected']=min(scores,key=lambda z:z['validation_MAE']);r['selection']='D05 raw MAE over four independent train-tail candidates';r['config_hash']=e.cfg_hash([r['order'],target,r['selected']]);r['device']='cpu'
   short=f.iloc[:1];cut=int(short.cutoff_row.iloc[0]);changed=raw.copy();changed[cut:,j]=123456.
   np.testing.assert_allclose(b.arima_prediction(raw,short,r,j),b.arima_prediction(changed,short,r,j),rtol=1e-8,atol=1e-8)
   r['future_suffix_invariance']='passed';d.json_write(OUT/f'baselines/ARIMA_{target}.json',r);records.append(r)
  except Exception as ex:fail('ARIMA:'+target,ex)
 return records

def test(c,records,schedule,arima):
 frozen=json.loads((OUT/'SELECTION_FROZEN.json').read_text());assert frozen['records_hash']==e.cfg_hash([records,schedule,arima])
 for r in records:
  try:
   status('test_inference',current=dict(task=r['task'],target=r['target'],model=r['model'],seed=r['seed']))
   model=e.load_record_model(c,r);task=r['task'];spec=r['spec']
   for slot in ['D06','D07']:
    key='RAN' if r['model']=='XGBoost_RAN_only' else ('TranAD' if r['model']=='TranAD' else task)
    x,f=d.load_samples(task,r['target'],[slot],key)
    if spec.get('panel')=='U':x=x[...,[r['info']['target_index']]]
    start=time.perf_counter();pred=e.validation_predict(c,task,spec,model,x,f,r['info']);e.save_predictions(c,r,f,pred,time.perf_counter()-start)
   del model,x;gc.collect();torch.cuda.empty_cache()
  except Exception as ex:fail('test:'+r['model']+':'+r['target']+':'+str(r['seed']),ex)
 for slot in ['D06','D07']:
  f=pd.read_parquet(OUT/f'indices/T2_command_overlap_{slot}.parquet');start=time.perf_counter();p=np.array(schedule['probability'])[f.anchor_row.to_numpy()%900];e.save_predictions(c,schedule,f,p,time.perf_counter()-start)
 for target in [t['id'] for t in c['data']['targets']]:
  j,_,_=e.target_stats(c,target);median=json.loads((OUT/'scalers.json').read_text())['T1']['median'][j]
  for slot in ['D06','D07']:
   f=pd.read_parquet(OUT/f'indices/T1_{target}_{slot}.parquet');raw=np.load(d.ROOT/f'cache/{slot}/T1_raw_windows.npy',mmap_mode='r');start=time.perf_counter();pred=[]
   for row in f.tensor_row:
    h=raw[row,:,j];valid=h[np.isfinite(h)];short=h[-10:];short=short[np.isfinite(short)];pred.append(float(short.mean()) if len(short) else float(valid[-1]) if len(valid) else median)
   r=dict(task='T1',target=target,model='RecentMean10',seed=42,spec=dict(id='RecentMean10',panel='U'),config_hash=e.cfg_hash(['RecentMean10',target,'cutoff_window']),device='cpu')
   e.save_predictions(c,r,f,np.array(pred),time.perf_counter()-start)
 for r in arima:
  j,_,_=e.target_stats(c,r['target'])
  for slot in ['D06','D07']:
   try:
    raw=np.load(d.ROOT/f'cache/{slot}/raw.npy');f=pd.read_parquet(OUT/f'indices/T1_{r["target"]}_{slot}.parquet');start=time.perf_counter();pred=b.arima_prediction(raw,f,r,j);e.save_predictions(c,r,f,pred,time.perf_counter()-start)
   except Exception as ex:fail('ARIMA_test:'+r['target']+':'+slot,ex)

def finish(c):
 report.validate(c);metrics=report.collect(c)
 if len(metrics):
  main=metrics[metrics.subset.eq('all_eligible')]
  g=main.groupby(['task','target','model','input_panel','slot','metric','unit'],dropna=False).value.agg(['mean','std','count']).reset_index();g.to_csv(OUT/'tables/summary_by_run_seed.csv',index=False)
  for task,metric in [('T1','MAE'),('T2','AP')]:
   z=g[g.task.eq(task)&g.metric.eq(metric)].copy();z['value']=z.apply(lambda r:f'{r["mean"]:.6g} ± {r["std"]:.3g}' if r['count']>1 else f'{r["mean"]:.6g}',axis=1)
   tab=z.pivot(index=['target','model','input_panel'],columns='slot',values='value').reset_index();tab.to_csv(OUT/f'tables/{task}_paper.csv',index=False)
   text=report.markdown(tab.columns.tolist(),tab.fillna('NA').values.tolist())
   (OUT/f'tables/{task}_paper.md').write_text('Four-field prefix-repaired W1 rerun. D06/D07 previously accessed post-hoc. Mean ± sample SD across optimization seeds.\n\n'+text)
  z=main[main.task.eq('T1')&main.metric.isin(['MAE','R2'])];m=z[z.model.eq('XGBoost')];h=z[z.model.eq('XGBoost_target_history_and_mask')];paired=m.merge(h,on=['target','slot','seed','metric'],suffixes=('_M','_H'),validate='one_to_one');paired['M_relative_MAE_reduction_pct']=np.where(paired.metric.eq('MAE'),100*(paired.value_H-paired.value_M)/paired.value_H,np.nan);paired.to_csv(OUT/'tables/matched_input_H_M.csv',index=False)
 expected=[]
 for task in ['T1','T2']:
  targets=[t['id'] for t in c['data']['targets']] if task=='T1' else ['command_overlap']
  names=([s['id'] for s in c['t1']['models']]+['XGBoost_schedule_only','XGBoost_target_history_and_mask']) if task=='T1' else [s['id'] for s in c['t2']['models']]+['ScheduleResidue900','XGBoost_missingness_only','XGBoost_RAN_only']
  for target in targets:
   for name in names:
    for seed in ([42] if name in ['RecentMean10','ARIMA','ScheduleResidue900'] else [42,43,44]):
     complete=all((OUT/f'predictions/{task}_{target}_{name}_seed{seed}_{slot}.parquet').exists() for slot in ['D06','D07']);expected.append(dict(task=task,target=target,model=name,seed=seed,status='completed' if complete else 'incomplete'))
 pd.DataFrame(expected).to_csv(OUT/'completion_matrix.csv',index=False)
 summary=dict(completed=sum(x['status']=='completed' for x in expected),expected=len(expected),known_blocked=['ARIMA:n6_aggregate','ARIMA:flow_rtt_proxy'],training_from_scratch=True,source_integrity_pass=True)
 d.json_write(OUT/'COMPLETION.json',summary)
 (OUT/'RUN_SUMMARY.md').write_text(f'Repaired rerun completed {summary["completed"]}/{summary["expected"]} units. Each unit requires outputs for every D06/D07 sample. N6/flow-timing ARIMA lacks valid long context; other failures are in branch_failures.json and jobs. Four-field prefix repair does not establish real-time availability of all telemetry. Tests are previously accessed post hoc tests. English tables and per-sample outputs are saved; the manuscript was not modified.\n')
 with zipfile.ZipFile(d.ROOT/'PREFIXFIX_RESULTS_SMALL.zip','w',zipfile.ZIP_DEFLATED) as z:
  for folder in ['src','spec','outputs','third_party']:
   for p in (d.ROOT/folder).rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ['.pt','.npy','.joblib','.zip'] and p.name!='validation_predictions.parquet':z.write(p,p.relative_to(d.ROOT))
  for name in ['resolved_config.yaml','EXPERIMENT_PLAN.md','run_repaired.sh']:z.write(d.ROOT/name,name)
 with zipfile.ZipFile(d.ROOT/'PREFIXFIX_RESULTS_SMALL.zip') as z:assert z.testzip() is None
 return summary

def main(stage):
 lock=open(OUT/'pipeline.lock','a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 c=d.config();torch.set_num_threads(16)
 if stage=='smoke':status('smoke',status='running');smoke(c);status('smoke_passed',status='ready_for_training');return
 status('starting',status='running',started_at=time.time())
 assert json.loads((OUT/'WINDOW_VALIDATION.json').read_text())['passed']
 passed={(r['task'],r['model']) for r in json.loads((OUT/'SMOKE.json').read_text()) if r['passed']}
 try:
  records,schedule=develop(c,passed);arima=arima_develop(c)
  d.json_write(OUT/'SELECTION_FROZEN.json',dict(records_hash=e.cfg_hash([records,schedule,arima]),records=records,schedule=schedule,arima=arima,frozen_at=time.time(),test_predictions_started=False))
  test(c,records,schedule,arima);status('report',current=None);summary=finish(c);status('finished',status='completed' if summary['completed']==summary['expected'] else 'finished_with_incomplete_items',completion=summary,ended_at=time.time())
 except BaseException as ex:status('failed',status='interrupted_or_failed',error=str(ex),traceback=traceback.format_exc());raise
if __name__=='__main__':
 parser=argparse.ArgumentParser();parser.add_argument('--stage',choices=['smoke','train'],default='train');main(parser.parse_args().stage)
