"""RCA_joint12: immutable-package adapter, bounded fits, frozen evaluation."""
import os,sys,json,hashlib,time,random,copy,resource,argparse
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import f1_score,accuracy_score,balanced_accuracy_score,confusion_matrix
import joblib
from legacy_models import SequenceClassifier
from roles import resolve_role,tests as role_tests,CORE_RUN,CORE_SLOT,RULE
R=Path(__file__).resolve().parents[1]
P=Path(os.environ.get('DGATE_LOCALIZATION_DATA_PACKAGE','PATH_TO_REVIEWER_DATA_PACKAGE'))
OLD=R/'legacy_reference'
sys.path.insert(0,str(P/'code'))
import dataset as legacy
MECH=['n3-block','n3-delay','n3-loss','n4-block','n6-block','instance-stop']
TARGET=['upf-silver','upf-gold'];CLASSES=[f'{m}|{t}' for m in MECH for t in TARGET]
MODELS=['LSTM','TCN','RF_24','RF_FL10','ReadyMaskRF'];SEEDS=[17,29,43]
def now():return datetime.now(timezone.utc).isoformat()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):
 p=R/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,ensure_ascii=False,allow_nan=False))
def mechanism_label(ft,fid):
 if ft in {'n3-block','n4-block','n6-block','instance-stop'}:return ft
 if ft!='netem':raise ValueError(f'Unexpected type: {ft}')
 if '_n3_delay_loss_' in fid:return 'out_of_scope:n3-delay+loss'
 d='_n3_delay_' in fid;l='_n3_loss_' in fid
 if d==l:raise ValueError(f'Ambiguous netem label: {fid}')
 return 'n3-delay' if d else 'n3-loss'
def rank(p):return np.argsort(-p,axis=1,kind='stable')
def measures(y,p,supported=False):
 y=np.asarray(y,dtype=int);rr=rank(p);pred=rr[:,0];labels=[int(x) for x in sorted(set(y))] if supported else list(range(12))
 mp=p.reshape(-1,6,2).sum(2);tp=p.reshape(-1,6,2).sum(1)
 return dict(n=len(y),top1=float(np.mean(pred==y)),macro_f1=float(f1_score(y,pred,labels=labels,average='macro',zero_division=0)),top3=float(np.mean(np.any(rr[:,:3]==y[:,None],axis=1))),mrr=float(np.mean(1/(np.argmax(rr==y[:,None],axis=1)+1))),balanced_accuracy=float(balanced_accuracy_score(y,pred)),mechanism_accuracy=float(np.mean(mp.argmax(1)==y//2)),mechanism_macro_f1=float(f1_score(y//2,mp.argmax(1),labels=sorted(set(y//2)) if supported else list(range(6)),average='macro',zero_division=0)),target_accuracy=float(np.mean(tp.argmax(1)==y%2)),f1_labels=json.dumps(labels),support=json.dumps(np.bincount(y,minlength=12).tolist()))
def value_stats(v):return np.concatenate([v.mean(1),v.std(1),v.min(1),v.max(1),v[:,-1],v[:,-1]-v[:,0]],axis=1)
def inputs(values,mask,names,kind):
 if kind in ['LSTM','TCN']:return np.concatenate([values,mask.astype(np.float32)],2).astype(np.float32)
 if kind=='RF_24':idx=list(range(24))
 elif kind=='RF_FL10':idx=[names.index(x) for x in legacy.FEATURE_SETS['FL_primary_10']]
 elif kind=='ReadyMaskRF':
  idx=[names.index(t+'__ready') for t in TARGET]
  return np.concatenate([value_stats(values[:,:,idx]),mask.reshape(len(mask),-1),mask.mean(1)],1).astype(np.float32)
 else:raise ValueError(kind)
 return np.concatenate([value_stats(values[:,:,idx]),mask[:,:,idx].mean(1)],1).astype(np.float32)
def prep_fit(raw,train,names):
 assert len(train)==288
 flat=raw[train].reshape(-1,24).astype(float);med=np.nanmedian(flat,axis=0);q=np.nanpercentile(flat,[25,75],axis=0);iqr=q[1]-q[0];sd=np.nanstd(flat,axis=0);scale=np.where(iqr>0,iqr,np.where(sd>0,sd,1.));center=med.copy()
 for j,n in enumerate(names):
  if n.endswith('__ready'):center[j]=0;scale[j]=1
 assert np.isfinite(med).all() and np.isfinite(scale).all()
 return dict(impute=med.tolist(),center=center.tolist(),scale=scale.tolist(),iqr=iqr.tolist(),std=sd.tolist(),fit_event_count=288,fit_steps=3456)
def transform(raw,pp):
 mask=np.isfinite(raw);v=np.where(mask,raw,np.array(pp['impute']));v=(v-np.array(pp['center']))/np.array(pp['scale']);assert np.isfinite(v).all();return v.astype(np.float32),mask

def prepare():
 assert not any((R/'models').glob('*__seed*')), 'Existing fits: prepare must not overwrite'
 assert 'PREFLIGHT_PASS' in (R/'logs/preflight.log').read_text()
 idx=legacy.load_index(P,'FL_localization');ep=pd.read_csv(P/'metadata/ALL_CORE_EPISODES.csv',keep_default_na=False);runs=pd.read_csv(P/'metadata/runs.csv',keep_default_na=False)
 assert len(idx)==612 and len(ep)==621 and idx.eligible.all()
 assert not ep.duplicated(['run_id','fault_id']).any() and not idx.duplicated(['run_id','fault_id']).any()
 f=idx.merge(ep,on=['run_id','fault_id'],suffixes=('','_event'),validate='one_to_one',indicator=True)
 assert f['_merge'].eq('both').all()
 for a,b in [('fault_type','fault_type_event'),('target_instance','target_instance_event'),('slot','slot_event')]:assert f[a].eq(f[b]).all(),(a,b)
 assert f.episode_scope.eq('main').all() and f.target_instance.isin(TARGET).all() and f.y.eq(f.target_instance).all()
 for row in runs.itertuples():
  g=f[f.run_id==row.run_id];assert g.split.eq(row.split).all() and g.slot.eq(row.slot).all()
 assert f.groupby('run_id').split.nunique().max()==1
 f=f.rename(columns={'split':'index_split','run_split':'source_episode_run_split'})
 f['registry_split']=f.run_id.map(runs.set_index('run_id').split)
 # The review-package episode export omits the original per-event run_split column.
 # Derive that comparison field from its run registry; keep the documented
 # Core24h event_block_protocol exception explicit and bounded to that run.
 if 'source_episode_run_split' not in f:
  f['source_episode_run_split']=f['registry_split']
  f.loc[f.run_id.eq(CORE_RUN),'source_episode_run_split']='event_block_protocol'
 resolved=[resolve_role(r.run_id,r.slot,r.source_episode_run_split,r.registry_split,r.index_split) for r in f.itertuples()]
 f['effective_split']=[x[0] for x in resolved];f['role_resolution_rule']=[x[1] for x in resolved]
 ep=ep.rename(columns={'run_split':'source_episode_run_split'})
 ep['registry_split']=ep.run_id.map(runs.set_index('run_id').split)
 if 'source_episode_run_split' not in ep:
  ep['source_episode_run_split']=ep['registry_split']
  ep.loc[ep.run_id.eq(CORE_RUN),'source_episode_run_split']='event_block_protocol'
 ep['index_split']=[dict(zip(zip(f.run_id,f.fault_id),f.index_split)).get((r.run_id,r.fault_id),'') for r in ep.itertuples()]
 resolved=[resolve_role(r.run_id,r.slot,r.source_episode_run_split,r.registry_split,r.index_split or None) for r in ep.itertuples()]
 ep['effective_split']=[x[0] for x in resolved];ep['role_resolution_rule']=[x[1] for x in resolved]
 assert f.role_resolution_rule.eq(RULE).sum()==28 and ep.role_resolution_rule.eq(RULE).sum()==36
 assert not ((f.run_id==CORE_RUN)&(f.effective_split=='train')).any()
 package_hashes={line.split(maxsplit=1)[1].lstrip('*'):line.split(maxsplit=1)[0] for line in (P/'SHA256SUMS.txt').read_text().splitlines()}
 bound={n:package_hashes[n] for n in ['metadata/runs.csv','metadata/ALL_CORE_EPISODES.csv','tasks/FL_localization/index.csv.gz','tasks/FL_localization/index.parquet']}
 for n,h in bound.items():assert sha(P/n)==h,n
 dump('audit/role_tests.json',role_tests())
 dump('data_contract/role_resolution.json',{'version':RULE,'unique_run':CORE_RUN,'slot':CORE_SLOT,'source':'event_block_protocol','effective':'supplementary_only','index_registry_equality_required':True,'input_hashes':bound,'ledger_rows':36,'FL_rows':28,'Core24h_training_cases':0,'authority':'explicit user clarification received in this conversation','basis':['metadata/README.md:3','code/validate_package.py:112-116','code/build_package.py:87-89'],'all_other_mismatches':'error'})
 prior_blocker=R/'audit/BLOCKER.json'
 dump('audit/BLOCKER_RELEASE.json',{'time':now(),'prior_blocker':'audit/BLOCKER.json','prior_blocker_present':prior_blocker.exists(),'prior_blocker_sha256':sha(prior_blocker) if prior_blocker.exists() else None,'prior_report':'audit/history_blocked/FINAL_REPORT_ZH.md','resolution':'data_contract/role_resolution.json','status':'resolved_by_explicit_user_clarification','source_files_modified':False})
 f['mechanism']=[mechanism_label(t,i) for t,i in zip(f.fault_type,f.fault_id)]
 f['class_name']=[m+'|'+t if m in MECH else '' for m,t in zip(f.mechanism,f.target_instance)]
 f['class_id']=[CLASSES.index(c) if c else -1 for c in f.class_name]
 out=f[f.class_id<0];assert len(out)==4 and out.slot.eq(CORE_SLOT).all()
 assert set(out.fault_id)=={'r1_07_n3_delay_loss_silver','r1_08_n3_delay_loss_gold','r2_07_n3_delay_loss_silver','r2_08_n3_delay_loss_gold'}
 for role,n,each in [('train',288,24),('validation',72,6),('test',144,12),('external_validation',72,6),('supplementary_only',24,2)]:
  g=f[(f.effective_split==role)&(f.class_id>=0)];assert len(g)==n and g.class_id.value_counts().reindex(range(12),fill_value=0).eq(each).all(),role
 assert len(f[f.effective_split=='diagnostic_holdout'])==8
 for s in ['D06','D07']:assert f[f.slot==s].class_id.value_counts().reindex(range(12),fill_value=0).eq(6).all()
 names=legacy.feature_names(P,'FD_detection_24');raw=np.empty((612,12,24),dtype=np.float64);coverage=[];bounds=[]
 for run,g in f.groupby('run_id',sort=False):
  values=legacy.load_run(P,run,'FD_detection_24').to_numpy(float)
  rr=runs[runs.run_id==run].iloc[0];direct=pd.read_parquet(P/rr.data_path/'core_features_5s.parquet');times=pd.to_datetime(direct.cutoff_time,utc=True)
  assert np.array_equal(values,direct[names].to_numpy(float),equal_nan=True)
  old10=legacy.load_run(P,run,'FL_primary_10').to_numpy(float);j10=[names.index(n) for n in legacy.FEATURE_SETS['FL_primary_10']]
  for i,row in g.iterrows():
   a,b=int(row.start_row),int(row.stop_row);assert b-a==12 and 0<=a<b<=len(values)
   x=values[a:b];raw[i]=x;assert np.array_equal(x[:,j10],old10[a:b],equal_nan=True)
   ts=times.iloc[a:b];on=pd.Timestamp(row.start_time);anchor=pd.Timestamp(row.anchor_time)
   assert (ts>on).all() and (ts<=on+pd.Timedelta(seconds=60)).all() and (ts<=anchor).all()
   assert abs((anchor-on).total_seconds()-60)<1e-6 and np.all(np.diff(ts.astype('int64'))==5_000_000_000)
   mask=np.isfinite(x);assert mask.mean()>=.5
   coverage.append(dict(sample_id=row.sample_id,slot=row.slot,effective_split=row.effective_split,observed_fraction=float(mask.mean()),missing_channel_count=int((~mask.any(0)).sum()),**{n:float(z) for n,z in zip(names,mask.mean(0))}))
   bounds.append(dict(sample_id=row.sample_id,run_id=run,start_row=a,stop_row=b,event_start=row.start_time,anchor_time=row.anchor_time,first_cutoff=ts.iloc[0].isoformat(),last_cutoff=ts.iloc[-1].isoformat(),first_offset_s=(ts.iloc[0]-on).total_seconds(),last_offset_s=(ts.iloc[-1]-on).total_seconds()))
 train=np.flatnonzero(f.effective_split.eq('train'));pp=prep_fit(raw,train,names);pp['fit_sample_ids']=f.iloc[train].sample_id.tolist();pp['feature_names']=names
 dump('models/preprocessing.json',pp);v,mask=transform(raw,pp)
 # Explicit interfaces: arrays carry no label or metadata fields.
 np.savez_compressed(R/'cache/windows.npz',raw=raw,values=v,mask=mask)
 f.drop(columns='_merge').to_csv(R/'data_contract/sample_index.csv',index=False)
 pd.DataFrame(coverage).to_csv(R/'data_contract/coverage.csv',index=False);pd.DataFrame(bounds).to_csv(R/'data_contract/window_boundaries.csv',index=False)
 f.groupby(['effective_split','slot','class_id','class_name'],dropna=False).size().rename('n').reset_index().to_csv(R/'data_contract/class_counts.csv',index=False)
 disp=ep.merge(f[['run_id','fault_id','sample_id','class_id','mechanism']],on=['run_id','fault_id'],how='left',validate='one_to_one')
 disp['disposition']=np.where(disp.sample_id.isna(),np.where(disp.episode_scope.eq('main'),'excluded:AMF/SMF_stop_not_original_FL','excluded:V4_prelude'),np.where(disp.class_id.eq(-1),'case_only:composite_delay+loss','closed_set'))
 assert disp.disposition.value_counts().to_dict()=={'closed_set':608,'excluded:AMF/SMF_stop_not_original_FL':8,'case_only:composite_delay+loss':4,'excluded:V4_prelude':1}
 disp.to_csv(R/'data_contract/event_disposition_621.csv',index=False)
 dump('data_contract/classes.json',dict(mechanisms=MECH,targets=TARGET,classes=CLASSES));dump('data_contract/fit_sample_ids.json',pp['fit_sample_ids'])
 cols10=legacy.FEATURE_SETS['FL_primary_10'];ready=[t+'__ready' for t in TARGET]
 whitelist={'LSTM':{'values':names,'masks':names,'shape':[12,48]},'TCN':{'values':names,'masks':names,'shape':[12,48]},'RF_24':{'values':names,'mask_proportions':names,'width':168},'RF_FL10':{'values':cols10,'mask_proportions':cols10,'width':70},'ReadyMaskRF':{'values':ready,'mask_steps':names,'mask_proportions':names,'width':324},'rf_value_summaries':['mean','std_ddof0','min','max','last','last-first'],'forbidden':'all metadata, event IDs, timestamps, order, source age, context, recovery and future fields'}
 dump('data_contract/feature_whitelists.json',whitelist)
 unit_checks(raw,v,mask,f,pp,names)
 config={'task':'RCA_joint12','created_utc':now(),'package_root':str(P),'seeds':SEEDS,'models':MODELS,'formal_fits':15,'classes':CLASSES,'device':'cuda:0','threads':4,'deep':{'width':64,'dropout':.1,'LSTM_layers':2,'TCN_blocks':2,'TCN_dilations':[1,2],'kernel':3,'input_dim':48,'output_dim':12,'batch':32,'epochs':50,'patience':8,'optimizer':'AdamW','lr':.001,'weight_decay':.0001,'selection':'max D05 Macro-F1, then min D05 CE, then earliest epoch'},'RF':{'n_estimators':500,'min_samples_leaf':2,'max_features':'sqrt','max_depth':None,'n_jobs':4,'class_weight':None},'ranking_ties':'stable frozen class order','preprocess':'288 training cases observed-value median imputation; median/IQR scale except Ready; zero IQR -> std ->1; masks preserved','split_status':'fixed historical split additional non-blind reevaluation; externals never tune','metric_policy':'all12 for W1/main role macro-F1; diagnostic and mechanism-stratum macro-F1 supported true labels only; full12 ranking everywhere','composite_policy':'predict all12, no closed-set metrics','smoke':'one training event per class, 250 updates maximum, no formal score'}
 dump('config.json',config)
 provenance={'old_models':str(OLD/'code/models.py'),'old_models_sha256':sha(OLD/'code/models.py'),'copied_models_sha256':sha(R/'code/legacy_models.py'),'old_train':str(OLD/'code/train.py'),'old_train_sha256':sha(OLD/'code/train.py'),'old_config_sha256':sha(OLD/'configs/base_config.json'),'reuse':'exact SequenceClassifier architectures; sklearn RandomForestClassifier family reused; new 12-class head, 48 input, required summary RF input and updated fixed parameters; no checkpoint reuse'}
 dump('audit/code_reuse.json',provenance)
 dump('audit/EXECUTION_FREEZE.json',{'time':now(),'config_sha256':sha(R/'config.json'),'code':{str(p.relative_to(R)):sha(p) for p in sorted((R/'code').glob('*.py'))},'contract':{str(p.relative_to(R)):sha(p) for p in sorted((R/'data_contract').glob('*'))},'preprocess_sha256':sha(R/'models/preprocessing.json'),'heldout_model_inference_started':False})
 dump('tracker.json',[{'model':m,'seed':s,'status':'not_executed'} for m in MODELS for s in SEEDS]);print('PREPARE_PASS',f.groupby('effective_split').size().to_dict(),flush=True)
def unit_checks(raw,v,mask,f,pp,names):
 checks=[]
 def ok(n):checks.append(n)
 assert mechanism_label('netem','a_n3_delay_x')=='n3-delay' and mechanism_label('netem','a_n3_loss_x')=='n3-loss' and mechanism_label('netem','a_n3_delay_loss_x').startswith('out_of_scope');ok('label_single_and_composite')
 for ft,fi in [('bad','x'),('netem','x'),('netem','a_n3_delay_x_n3_loss_x')]:
  try:mechanism_label(ft,fi)
  except ValueError:pass
  else:raise AssertionError((ft,fi))
 ok('label_unknown_and_conflicting_rejected')
 p=np.full((2,12),1/12);m=measures([0,3],p);assert m['top1']==.5 and m['top3']==.5 and m['mrr']==.625;ok('manual_ties_topk_mrr')
 tr=np.flatnonzero(f.effective_split.eq('train'));perturbed=raw.copy();perturbed[~f.effective_split.eq('train').to_numpy()]=999999
 assert prep_fit(perturbed,tr,names)=={k:pp[k] for k in ['impute','center','scale','iqr','std','fit_event_count','fit_steps']};ok('heldout_perturbation_does_not_change_training_statistics')
 for model,width in [('RF_24',168),('RF_FL10',70),('ReadyMaskRF',324)]:assert inputs(v,mask,names,model).shape==(612,width)
 c=inputs(v,mask,names,'ReadyMaskRF');vp=v.copy();vp[:,:,:22]+=12345;assert np.array_equal(c,inputs(vp,mask,names,'ReadyMaskRF'));ok('ReadyMaskRF_excludes_nonReady_values')
 assert inputs(v,mask,names,'LSTM').shape==(612,12,48);ok('whitelist_shapes')
 for j,n in enumerate(names):
  if n.endswith('__ready'):assert np.isin(raw[:,:,j][mask[:,:,j]],[0,1]).all() and np.array_equal(v[:,:,j][mask[:,:,j]],raw[:,:,j][mask[:,:,j]])
 ok('Ready_observed_values_unchanged');ok('612_source_windows_and_FL10_equal_elementwise');ok('621_event_disposition_and_role_counts');ok('run_isolation_and_time_boundaries')
 dump('audit/unit_checks.json',{'status':'PASS','checks':checks})
def load():
 f=pd.read_csv(R/'data_contract/sample_index.csv',keep_default_na=False);z=np.load(R/'cache/windows.npz');pp=json.loads((R/'models/preprocessing.json').read_text());return f,z['values'],z['mask'],pp['feature_names']
def smoke():
 f,v,mask,names=load();x=inputs(v,mask,names,'LSTM');ids=[f[(f.effective_split=='train')&(f.class_id==c)].index[0] for c in range(12)]
 torch.manual_seed(170);torch.set_num_threads(4);a=torch.tensor(x[ids],device='cuda');y=torch.arange(12,device='cuda');results=[]
 for kind in ['LSTM','TCN']:
  model=SequenceClassifier(kind,48,12).cuda();optimizer=torch.optim.AdamW(model.parameters(),lr=.003);first=None
  for step in range(250):
   model.train();optimizer.zero_grad();logits=model(a);loss=torch.nn.functional.cross_entropy(logits,y)
   if first is None:first=float(loss.item())
   loss.backward();assert all(p.grad is not None and torch.isfinite(p.grad).all() for p in model.parameters());optimizer.step()
   model.eval()
   with torch.no_grad():acc=float((model(a).argmax(1)==y).float().mean().item())
   if acc==1 and loss.item()<.1:break
  assert acc==1 and loss.item()<first,(kind,acc,loss.item())
  results.append(dict(model=kind,updates=step+1,initial_loss=first,final_loss=loss.item(),train_smoke_accuracy=acc,formal_score=False))
 dump('audit/training_smoke.json',results);print('TRAINING_SMOKE_PASS',results,flush=True)
def fit_one(kind,seed,f,v,mask,names,cfg):
 random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed);torch.set_num_threads(4);torch.backends.cudnn.deterministic=True;torch.backends.cudnn.benchmark=False
 tr=np.flatnonzero(f.effective_split.eq('train'));va=np.flatnonzero(f.effective_split.eq('validation'));x=inputs(v,mask,names,kind);y=f.class_id.to_numpy(int);start=time.perf_counter();ident=f'{kind}__seed{seed}';out=R/'models'/ident;out.mkdir();logs=[];torch.cuda.reset_peak_memory_stats()
 if kind.startswith('RF') or kind=='ReadyMaskRF':
  model=RandomForestClassifier(**cfg['RF'],random_state=seed);model.fit(x[tr],y[tr]);assert list(model.classes_)==list(range(12));p=model.predict_proba(x[va]);joblib.dump(model,out/'model.joblib');best_epoch=None;score=measures(y[va],p);params=None
 else:
  model=SequenceClassifier(kind,48,12).cuda();params=sum(p.numel() for p in model.parameters());opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.0001)
  xt=torch.tensor(x[tr],device='cuda');yt=torch.tensor(y[tr],device='cuda');xv=torch.tensor(x[va],device='cuda');yv=torch.tensor(y[va],device='cuda');best=None;bad=0
  for epoch in range(1,51):
   es=time.perf_counter();model.train();order=torch.randperm(len(tr),device='cuda');total=0.
   for ix in order.split(32):
    opt.zero_grad();loss=torch.nn.functional.cross_entropy(model(xt[ix]),yt[ix]);assert torch.isfinite(loss);loss.backward();opt.step();total+=loss.item()*len(ix)
   model.eval()
   with torch.no_grad():logits=model(xv);vl=torch.nn.functional.cross_entropy(logits,yv).item();p=logits.softmax(1).cpu().numpy()
   score=measures(y[va],p);key=(score['macro_f1'],-vl)
   logs.append(dict(epoch=epoch,train_loss=total/len(tr),validation_loss=vl,validation_macro_f1=score['macro_f1'],seconds=time.perf_counter()-es))
   if best is None or key>best:best=key;state={k:t.detach().cpu().clone() for k,t in model.state_dict().items()};best_epoch=epoch;bad=0
   else:bad+=1
   if bad>=8:break
  torch.save(state,out/'checkpoint.pt');pd.DataFrame(logs).to_csv(R/'logs'/f'{ident}.csv',index=False)
  model.load_state_dict(state);model.eval()
  with torch.no_grad():p=model(xv).softmax(1).cpu().numpy()
  score=measures(y[va],p)
 elapsed=time.perf_counter()-start
 record={'model':kind,'seed':seed,'status':'success','seconds':elapsed,'epochs_run':len(logs),'selected_epoch':best_epoch,'validation':score,'trainable_parameters':params,'peak_cuda_allocated_bytes':torch.cuda.max_memory_allocated(),'process_peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'config_sha256':sha(R/'config.json'),'fit_sample_ids_sha256':sha(R/'data_contract/fit_sample_ids.json'),'input_shape':list(x[tr].shape),'completed_utc':now()}
 dump(f'models/{ident}/fit.json',record);return record

def train():
 freeze=json.loads((R/'audit/FORMAL_START_FREEZE.json').read_text())
 assert sha(R/'config.json')==freeze['config_sha256']
 for n,h in freeze['code'].items():assert sha(R/n)==h,n
 assert json.loads((R/'audit/unit_checks.json').read_text())['status']=='PASS';assert (R/'audit/training_smoke.json').exists();cfg=json.loads((R/'config.json').read_text());f,v,mask,names=load();tracker=json.loads((R/'tracker.json').read_text())
 for i,row in enumerate(tracker):
  assert row['status']=='not_executed';row['status']='running';row['started_utc']=now();dump('tracker.json',tracker)
  try:rec=fit_one(row['model'],row['seed'],f,v,mask,names,cfg);row.update(rec)
  except Exception as e:row.update(status='failed',error=repr(e));dump('tracker.json',tracker);raise
  dump('tracker.json',tracker);print('FIT_DONE',row['model'],row['seed'],'seconds',round(row['seconds'],2),'epochs',row['epochs_run'],'best',row['selected_epoch'],flush=True)
  if i==0:
   est={'basis':'first actual LSTM fit only; RF timing unknown','first_fit_seconds':row['seconds'],'remaining_deep_estimate_seconds':5*row['seconds'],'first_fit_epochs':row['epochs_run'],'peak_cuda_allocated_bytes':row['peak_cuda_allocated_bytes'],'process_peak_rss_kib':row['process_peak_rss_kib']};dump('audit/first_fit_timing.json',est);print('FIRST_FIT_ESTIMATE',est,flush=True)
 dump('audit/TEST_FREEZE.json',{'time':now(),'config_sha256':sha(R/'config.json'),'code':{str(p.relative_to(R)):sha(p) for p in sorted((R/'code').glob('*.py'))},'models':{str(p.relative_to(R)):sha(p) for p in sorted((R/'models').rglob('*')) if p.is_file()},'tracker_sha256':sha(R/'tracker.json'),'all15_success':all(t['status']=='success' for t in tracker),'heldout_model_inference_started':False})
 print('TRAIN_ALL15_COMPLETE_TEST_FROZEN',flush=True)
def evaluate():
 freeze=json.loads((R/'audit/TEST_FREEZE.json').read_text());assert freeze['all15_success']
 assert sha(R/'config.json')==freeze['config_sha256']
 for n,h in freeze['code'].items():assert sha(R/n)==h,n
 for n,h in freeze['models'].items():assert sha(R/n)==h,n
 f,v,mask,names=load();rows=[]
 for kind in MODELS:
  x=inputs(v,mask,names,kind)
  for seed in SEEDS:
   ident=f'{kind}__seed{seed}';out=R/'models'/ident
   if kind in ['LSTM','TCN']:
    model=SequenceClassifier(kind,48,12).cuda();model.load_state_dict(torch.load(out/'checkpoint.pt',weights_only=True));model.eval()
    with torch.no_grad():p=np.concatenate([model(torch.tensor(xx,device='cuda')).softmax(1).cpu().numpy() for xx in np.array_split(x,6)])
   else:p=joblib.load(out/'model.joblib').predict_proba(x)
   assert p.shape==(612,12) and np.isfinite(p).all() and (p>=0).all() and np.allclose(p.sum(1),1,atol=1e-6)
   rr=rank(p);d=f[['sample_id','run_id','slot','source_episode_run_split','registry_split','index_split','effective_split','role_resolution_rule','fault_id','fault_type','target_instance','mechanism','class_id','class_name','quality']].copy();d['model']=kind;d['seed']=seed;d['config_sha256']=sha(R/'config.json');d['model_sha256']=sha(out/('checkpoint.pt' if kind in ['LSTM','TCN'] else 'model.joblib'))
   for j,c in enumerate(CLASSES):d[f'p_{j:02d}']=p[:,j];d[f'rank_{j+1:02d}']=rr[:,j]
   d['predicted_class']=[CLASSES[j] for j in rr[:,0]];d['mechanism_marginal']=[MECH[j] for j in p.reshape(-1,6,2).sum(2).argmax(1)];d['target_marginal']=[TARGET[j] for j in p.reshape(-1,6,2).sum(1).argmax(1)]
   d.to_parquet(R/'predictions'/f'{ident}.parquet',index=False);d.to_csv(R/'predictions'/f'{ident}.csv.gz',index=False)
   groups={role:np.flatnonzero(f.effective_split.eq(role)&f.class_id.ge(0)) for role in f.effective_split.unique()}
   groups.update({slot:np.flatnonzero(f.slot.eq(slot)&f.class_id.ge(0)) for slot in f.slot.unique()})
   for role,ix in groups.items():
    for stratum,ii in [('all',ix),('network',ix[f.iloc[ix].mechanism.ne('instance-stop')]),('instance-stop',ix[f.iloc[ix].mechanism.eq('instance-stop')])]+[(m,ix[f.iloc[ix].mechanism.eq(m)]) for m in MECH[:-1]]:
     if len(ii)==0:continue
     y=f.iloc[ii].class_id.to_numpy(int);r=measures(y,p[ii],supported=role in ['diagnostic_holdout','diagnostic5'] or stratum!='all');rows.append(dict(model=kind,seed=seed,role=role,stratum=stratum,**r))
     if stratum=='all':
      cm=confusion_matrix(y,rr[ii,0],labels=list(range(12)));pd.DataFrame(cm,index=CLASSES,columns=CLASSES).to_csv(R/'metrics'/f'CM__{ident}__{role}.csv')
   d[d.class_id<0].to_csv(R/'predictions'/f'COMPOSITE__{ident}.csv',index=False)
 metrics=pd.DataFrame(rows);metrics.to_csv(R/'metrics/ALL_METRICS.csv',index=False)
 nums=['top1','macro_f1','top3','mrr','balanced_accuracy','mechanism_accuracy','mechanism_macro_f1','target_accuracy'];s=metrics.groupby(['model','role','stratum'])[nums].agg(['mean','std']);s.columns=['_'.join(c) for c in s.columns];s.reset_index().to_csv(R/'metrics/SUMMARY.csv',index=False)
 print('EVALUATION_COMPLETE',len(rows),'metric rows',flush=True)
if __name__=='__main__':
 torch.set_num_threads(4)
 mode=sys.argv[1]
 {'prepare':prepare,'smoke':smoke,'train':train,'evaluate':evaluate}[mode]()
