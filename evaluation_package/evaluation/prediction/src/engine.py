"""Training/selection on development slots only; final evaluation is separate."""
import os
for key in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS']: os.environ.setdefault(key,'8')
import copy
import gc
import hashlib
import json
import random
import time
import traceback
import warnings
import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score,roc_auc_score,precision_recall_curve,f1_score
from xgboost import XGBRegressor,XGBClassifier
from . import data as d
from . import models as m

OUT=d.ROOT/'outputs'
NEURAL={'DLinear','PatchTST','iTransformer','TimeMixer','LSTM','TCN','AE','LSTMAE','TranAD','AnomalyTransformer','TimesNet'}
NEURAL.update({'TimeFilter','WPMixer','KANAD','CCMTAD'})

def seed_all(seed):
    random.seed(seed);np.random.seed(seed);torch.manual_seed(seed)
    if torch.cuda.is_available():torch.cuda.manual_seed_all(seed)

def cfg_hash(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,default=str).encode()).hexdigest()

def threshold(y,s):
    assert np.isfinite(s).all() and set(np.unique(y))=={0,1}
    p,r,t=precision_recall_curve(y,s)
    f=2*p[:-1]*r[:-1]/np.maximum(p[:-1]+r[:-1],1e-15)
    i=np.flatnonzero(f==np.max(f))[-1]
    return float(t[i]),float(f[i])

def table(x,f,view='M',j=0):
    c=x.shape[-1]//2
    if view=='schedule_only':return d.schedule_table(f)
    if view=='missingness_only':return d.statistics(x[...,c:])
    if view=='target_history_and_mask':return d.statistics(x[...,[j,c+j]])
    return d.statistics(x)

def target_stats(c,target):
    j=c['resolved']['features'].index(next(t['legacy_field'] for t in c['data']['targets'] if t['id']==target))
    s=json.loads((OUT/'scalers.json').read_text())['T1']
    return j,float(s['mean'][j]),float(s['scale'][j])

def spec_for(c,task,name):return next(s for s in c[task.lower()]['models'] if s['id']==name)

def load_development(c,task,target,spec):
    key='TranAD' if spec['id']=='TranAD' else task
    x,f=d.load_samples(task,target,c['data']['split']['train'],key,fit_only=task=='T2')
    v,vf=d.load_samples(task,target,['D05'],key)
    j,mean,scale=target_stats(c,target) if task=='T1' else (0,0.,1.)
    if spec.get('panel')=='U':x=x[...,[j]];v=v[...,[j]];model_j=0
    else:model_j=j
    return x,f,v,vf,dict(target_index=j,model_target_index=model_j,target_mean=mean,target_scale=scale)

def torch_prediction(model,x,task,batch=128,device='cpu',checkpoint_metric=False):
    model.eval(); output=[]
    # Small singleton convolution/attention workloads are much faster without thread dispatch.
    old_threads=torch.get_num_threads()
    if model.name=='TimesNet':batch=1;torch.set_num_threads(1)
    try:
        with torch.inference_mode():
            for start in range(0,len(x),batch):
                b=torch.from_numpy(np.ascontiguousarray(x[start:start+batch])).to(device)
                if task=='T1':z=model(b)
                elif checkpoint_metric:
                    z=model(b)
                    if model.name=='TranAD':z=z[1]
                    elif model.name=='AnomalyTransformer':z=z[0]
                    err,mask=m.numeric_error(b,z)
                    # Return sums/counts to preserve numerical-position weighting.
                    z=torch.stack([err.sum((1,2)),mask.sum((1,2))],1)
                else:z=m.scores(model,b)
                output.append(z.cpu().numpy())
    finally:torch.set_num_threads(old_threads)
    result=np.concatenate(output)
    if not np.isfinite(result).all():raise FloatingPointError('nonfinite prediction; no sample dropped')
    return result

def train_neural(c,task,target,spec,hp,seed,x,f,v,vf,info,path,smoke=False):
    seed_all(seed);device=c['resolved']['device'];model=m.build(spec,x.shape[-1],info['model_target_index'],task).to(device)
    if device=='cuda':torch.cuda.reset_peak_memory_stats()
    name=spec['id'];trainconf=c[task.lower()]['training'];lr=float(hp['lr'])
    if name in ['AnomalyTransformer','KANAD']:
        opt=torch.optim.Adam(model.parameters(),lr=lr)
        sched=torch.optim.lr_scheduler.StepLR(opt,5,.75) if name=='KANAD' else None
    else:
        opt=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=1e-5 if name=='TranAD' else 1e-4)
        sched=torch.optim.lr_scheduler.StepLR(opt,5,.9) if name=='TranAD' else None
    y=torch.from_numpy(((f.label.to_numpy()-info['target_mean'])/info['target_scale']).astype(np.float32)) if task=='T1' else None
    epochs=2 if smoke else trainconf['max_epochs'];batch=128;best=float('inf');best_state=None;stale=0;history=[];steps=0
    started=time.perf_counter();t_train=0.;t_val=0.;status='completed'
    for epoch in range(epochs):
        model.train();order=torch.randperm(len(x)).numpy();loss_sum=0.;weight=0;ep_start=time.perf_counter()
        for start in range(0,len(x),batch):
            if not smoke and (time.perf_counter()-started>c['resources']['max_fit_minutes']*60 or
                              time.time()>float(os.environ.get('SUPPLEMENT_TRAINING_DEADLINE','inf'))):
                status='budget_stopped';break
            ids=order[start:start+batch];b=torch.from_numpy(x[ids]).to(device);opt.zero_grad(set_to_none=True)
            if task=='T1':
                z=model(b);rec=torch.nn.functional.smooth_l1_loss(z,y[ids].to(device),beta=1.)
                ls=(rec + .05*model.auxiliary_loss,) if name=='TimeFilter' else (rec,)
            else:ls,rec=m.losses(model,b,epoch)
            if not all(torch.isfinite(a).all() for a in ls):raise FloatingPointError('nonfinite native loss')
            for i,a in enumerate(ls):a.backward(retain_graph=i<len(ls)-1)
            norm=torch.nn.utils.clip_grad_norm_(model.parameters(),5.,error_if_nonfinite=True)
            if steps==0 and not any(p.grad is not None and torch.any(p.grad!=0) for p in model.parameters()):raise RuntimeError('empty gradients')
            opt.step();steps+=1;loss_sum+=float(rec.detach())*len(ids);weight+=len(ids)
        if device=='cuda':torch.cuda.synchronize()
        epoch_train=time.perf_counter()-ep_start;t_train+=epoch_train
        vs=time.perf_counter()
        if task=='T1':
            pred=torch_prediction(model,v,task,device=device)*info['target_scale']+info['target_mean'];pred=np.maximum(pred,0)
            metric=float(np.abs(pred-vf.label.to_numpy()).mean())
        else:
            valid=vf.window_all_clean.to_numpy(dtype=bool)
            z=torch_prediction(model,v[valid],task,device=device,checkpoint_metric=True)
            metric=float(z[:,0].sum()/z[:,1].sum())
        elapsed_val=time.perf_counter()-vs;t_val+=elapsed_val
        row=dict(epoch=epoch+1,train_numeric_loss=loss_sum/max(weight,1),validation_checkpoint_metric=metric,train_seconds=epoch_train,
            validation_seconds=elapsed_val,steps=steps,lr=opt.param_groups[0]['lr'])
        history.append(row)
        if metric<best:
            best=metric;best_state={k:a.detach().cpu().clone() for k,a in model.state_dict().items()};stale=0;best_epoch=epoch+1
            if path is not None:
                torch.save(dict(state_dict=best_state,spec=spec,hp=hp,seed=seed,task=task,target=target,info=info,channels=x.shape[-1],best_epoch=best_epoch),path)
        else:stale+=1
        print(json.dumps(dict(event='epoch',task=task,target=target,model=name,seed=seed,**row)),flush=True)
        if sched:sched.step()
        if name=='AnomalyTransformer':
            # Native epoch-end schedule from author's solver.
            for g in opt.param_groups:g['lr']=lr*0.5**epoch
        if status!='completed' or stale>=trainconf['patience']:break
    if best_state is None:raise RuntimeError('No finite checkpoint')
    model.load_state_dict(best_state)
    if path is not None:
        torch.save(dict(state_dict=best_state,spec=spec,hp=hp,seed=seed,task=task,target=target,info=info,channels=x.shape[-1],best_epoch=best_epoch),path)
    timing=dict(total_fit_seconds=time.perf_counter()-started,train_seconds=t_train,checkpoint_validation_seconds=t_val,
        peak_gpu_allocated_bytes=int(torch.cuda.max_memory_allocated()) if device=='cuda' else 0,epochs=len(history),best_epoch=best_epoch,steps=steps,
        parameter_count=sum(p.numel() for p in model.parameters()),status=status,history=history)
    return model,timing

def native_pca_score(model,x,batch=256):
    output=[]
    for start in range(0,len(x),batch):
        b=x[start:start+batch];flat=b.reshape(len(b),-1);z=model.inverse_transform(model.transform(flat)).reshape(b.shape)
        ch=b.shape[-1]//2;valid=1-b[:,-1,ch:]
        output.append((((b[:,-1,:ch]-z[:,-1,:ch])**2)*valid).sum(1)/valid.sum(1))
    return np.concatenate(output)

def predict_estimator(model,spec,x,f,info,task):
    if spec['id']=='PCA':return native_pca_score(model,x)
    if spec['id']=='IsolationForest':return -model.score_samples(table(x,f))
    view=spec.get('diagnostic_view','M');t=table(x,f,view,info['target_index'])
    if task=='T1':return np.maximum(model.predict(t)*info['target_scale']+info['target_mean'],0)
    return model.predict_proba(t)[:,1]

def fit_estimator(c,task,spec,hp,seed,x,f,info,path,smoke=False):
    t=time.perf_counter();name=spec['id'];a=spec.get('architecture',{});view=spec.get('diagnostic_view','M')
    if name=='PCA':
        model=PCA(n_components=min(hp['n_components'],len(x),x.shape[1]*x.shape[2]),svd_solver='randomized',random_state=seed)
        model.fit(x.reshape(len(x),-1))
    elif name=='IsolationForest':
        model=IsolationForest(n_estimators=spec['n_estimators'],max_samples=min(hp['max_samples'],len(x)),random_state=seed,n_jobs=8)
        model.fit(table(x,f))
    else:
        cls=XGBRegressor if task=='T1' else XGBClassifier
        model=cls(**a,**hp,random_state=seed,n_jobs=8,tree_method='hist',device=c['resolved']['device'],
            objective='reg:squarederror' if task=='T1' else 'binary:logistic')
        model.fit(table(x,f,view,info['target_index']),(f.label.to_numpy()-info['target_mean'])/info['target_scale'] if task=='T1' else f.label.to_numpy())
    if path:joblib.dump(model,path)
    return model,dict(total_fit_seconds=time.perf_counter()-t,train_seconds=time.perf_counter()-t,epochs=None,steps=None,peak_gpu_allocated_bytes=0,status='completed')

def validation_predict(c,task,spec,model,v,vf,info):
    if spec['id'] in NEURAL:
        p=torch_prediction(model,v,task,device=c['resolved']['device'])
        if task=='T1':p=np.maximum(p*info['target_scale']+info['target_mean'],0)
        return p
    return predict_estimator(model,spec,v,vf,info,task)

def fit_one(c,task,target,spec,hp,seed,tag,x,f,v,vf,info):
    directory=OUT/'jobs'/tag;directory.mkdir(parents=True,exist_ok=True);recordpath=directory/'record.json'
    if recordpath.exists():
        old=json.loads(recordpath.read_text())
        if old['status']=='completed':return old
        if old['status'] in ['failed','budget_stopped']:return old
    path=directory/('checkpoint.pt' if spec['id'] in NEURAL else 'estimator.joblib')
    record=dict(task=task,target=target,model=spec['id'],spec=spec,hp=hp,seed=seed,config_hash=cfg_hash([spec,hp,info,c[task.lower()]['training']]),
        checkpoint=str(path.relative_to(d.ROOT)),train_index_hash=d.index_hash(f),validation_index_hash=d.index_hash(vf),status='running',info=info,
        device='cpu' if spec['id'] in ['PCA','IsolationForest'] else c['resolved']['device'],precision=c['resolved']['precision'],started_at=time.time())
    d.json_write(recordpath,record)
    try:
        if spec['id'] in NEURAL:model,timing=train_neural(c,task,target,spec,hp,seed,x,f,v,vf,info,path)
        else:model,timing=fit_estimator(c,task,spec,hp,seed,x,f,info,path)
        record.update(timing);record['checkpoint_sha256']=d.digest(path)
        if record['status']=='completed':
            t=time.perf_counter();pred=validation_predict(c,task,spec,model,v,vf,info);record['selection_inference_seconds']=time.perf_counter()-t
            if not np.isfinite(pred).all() or len(pred)!=len(vf):raise FloatingPointError('prediction bijection/finite failure')
            if task=='T1':record['selection_metric']=float(np.abs(pred-vf.label.to_numpy()).mean())
            else:
                record['selection_metric']=float(average_precision_score(vf.label,pred));record['threshold'],record['validation_F1']=threshold(vf.label,pred)
            frame=vf.copy();frame['prediction' if task=='T1' else 'score']=pred;frame['seed']=seed
            frame.to_parquet(directory/'validation_predictions.parquet',index=False)
        del model;gc.collect()
    except Exception as e:
        record.update(status='failed',error=str(e),traceback=traceback.format_exc())
        print(record['traceback'],flush=True)
    d.json_write(recordpath,record)
    return record

def selection_file(task,target,name):return OUT/'selection'/f'{task}_{target}_{name}.json'

def develop_model(c,task,target,name,final_only=False):
    spec=spec_for(c,task,name);selectpath=selection_file(task,target,name)
    if not spec.get('search'):return
    x,f,v,vf,info=load_development(c,task,target,spec)
    if not final_only:
        if selectpath.exists():return
        candidates=[]
        for k,hp in enumerate(spec['search']):
            tag=f'{task}_{target}_{name}_candidate{k}_seed42'
            candidates.append(fit_one(c,task,target,spec,hp,42,tag,x,f,v,vf,info))
        ok=[r for r in candidates if r['status']=='completed']
        if ok:
            winner=(min if task=='T1' else max)(ok,key=lambda r:r['selection_metric'])
            d.json_write(selectpath,dict(status='selected',selected_by='D05_raw_MAE' if task=='T1' else 'D05_AP',winner=winner,
                candidate_statuses=[dict(hp=r['hp'],status=r['status'],error=r.get('error')) for r in candidates],selected_at=time.time()))
    else:
        if not selectpath.exists():return
        winner=json.loads(selectpath.read_text())['winner']
        for seed in [43,44]:fit_one(c,task,target,spec,winner['hp'],seed,f'{task}_{target}_{name}_final_seed{seed}',x,f,v,vf,info)

def load_record_model(c,r):
    path=d.ROOT/r['checkpoint'];assert d.digest(path)==r['checkpoint_sha256']
    if r['model'] in NEURAL:
        ck=torch.load(path,map_location='cpu',weights_only=False)
        model=m.build(ck['spec'],ck['channels'],ck['info']['model_target_index'],ck['task']);model.load_state_dict(ck['state_dict'])
        return model.to(c['resolved']['device'])
    return joblib.load(path)

def selected_records(c):
    records=[]
    for p in sorted((OUT/'selection').glob('*.json')):
        s=json.loads(p.read_text());w=s['winner'];records.append(w)
        for seed in [43,44]:
            q=OUT/'jobs'/f'{w["task"]}_{w["target"]}_{w["model"]}_final_seed{seed}'/'record.json'
            if q.exists():
                r=json.loads(q.read_text())
                if r['status']=='completed':records.append(r)
    return records

def save_predictions(c,r,f,pred,inference_seconds):
    assert len(f)==len(pred) and f.sample_id.is_unique and np.isfinite(pred).all()
    frame=f.copy();task=r['task'];frame['prediction' if task=='T1' else 'score']=pred
    for key in ['model','seed','config_hash']:frame[key]=r[key]
    frame['data_version']=c['resolved']['data_version'];frame['view_id']=c['resolved']['view_id'];frame['purpose']=c['resolved']['purpose']
    frame['index_hash']=d.index_hash(f)
    if task=='T2':frame['threshold']=r['threshold'];frame['decision']=pred>=r['threshold']
    slot=f.slot.iloc[0];file=OUT/'predictions'/f'{task}_{r["target"]}_{r["model"]}_seed{r["seed"]}_{slot}.parquet'
    frame.to_parquet(file,index=False)
    d.json_write(file.with_suffix('.json'),dict(model=r['model'],task=task,target=r['target'],slot=slot,seed=r['seed'],
        n_samples=len(f),index_hash=d.index_hash(f),prediction_sha256=d.digest(file),inference_seconds=inference_seconds,
        seconds_per_window=inference_seconds/len(f),inference_scope='local offline model+adapter; excludes data IO; not live network latency',
        device=c['resolved']['device'] if r['model'] in NEURAL or r['model']=='Chronos2' else r.get('device','cpu'),input_panel=r.get('spec',{}).get('panel','M'),config_hash=r['config_hash']))

def evaluate(c):
    freeze=OUT/'SELECTION_FROZEN.json'
    if not freeze.exists():raise RuntimeError('Development selections must be frozen before test metrics')
    recs=selected_records(c)
    expected=json.loads(freeze.read_text())['records_hash']
    assert cfg_hash(recs)==expected,'Selection changed after freeze'
    for r in recs:
        spec=r['spec'];task=r['task'];model=None
        for slot in ['D06','D07']:
            path=OUT/'predictions'/f'{task}_{r["target"]}_{r["model"]}_seed{r["seed"]}_{slot}.parquet'
            if path.exists():continue
            if model is None:model=load_record_model(c,r)
            x,f=d.load_samples(task,r['target'],[slot],'TranAD' if r['model']=='TranAD' else task)
            if spec.get('panel')=='U':x=x[...,[r['info']['target_index']]]
            t=time.perf_counter();pred=validation_predict(c,task,spec,model,x,f,r['info']);elapsed=time.perf_counter()-t
            save_predictions(c,r,f,pred,elapsed)
            print(json.dumps(dict(event='test_predictions_written',model=r['model'],target=r['target'],seed=r['seed'],slot=slot,n=len(f),seconds=elapsed)),flush=True)
        del model;gc.collect()
