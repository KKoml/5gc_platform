"""Post-fit verification: independent confusion/ranking arithmetic and model replay."""
import json,sys
import numpy as np,pandas as pd,torch,joblib
from pipeline import R,P,CLASSES,MECH,TARGET,MODELS,SEEDS,load,inputs,sha,dump,SequenceClassifier

def independent(y,p,labels):
 y=np.asarray(y,int);r=np.argsort(-p,axis=1,kind='stable');pred=r[:,0];cm=np.zeros((12,12),int)
 for a,b in zip(y,pred):cm[a,b]+=1
 def f1(cm,ids):
  t=np.diag(cm).astype(float);den=cm.sum(0)+cm.sum(1);return np.divide(2*t,den,out=np.zeros_like(t),where=den>0)[ids].mean()
 mp=p.reshape(-1,6,2).sum(2);tp=p.reshape(-1,6,2).sum(1);mc=np.zeros((6,6),int)
 for a,b in zip(y//2,mp.argmax(1)):mc[a,b]+=1
 ranks=[list(z).index(a)+1 for z,a in zip(r,y)]
 mlabels=sorted(set(y//2)) if len(labels)<12 else list(range(6))
 return {'top1':np.trace(cm)/len(y),'macro_f1':f1(cm,labels),'top3':np.mean(np.array(ranks)<=3),'mrr':np.mean(1/np.array(ranks)),'balanced_accuracy':np.mean([cm[j,j]/cm[j].sum() for j in sorted(set(y))]),'mechanism_accuracy':np.trace(mc)/len(y),'mechanism_macro_f1':f1(mc,mlabels),'target_accuracy':np.mean(tp.argmax(1)==y%2)},cm

def main():
 f,v,mask,names=load();metrics=pd.read_csv(R/'metrics/ALL_METRICS.csv');replays=[];checked=0;maxerr=0.;maxmetric=0.
 freeze=json.loads((R/'audit/TEST_FREEZE.json').read_text());start=json.loads((R/'audit/FORMAL_START_FREEZE.json').read_text());assert sha(R/'config.json')==freeze['config_sha256']==start['config_sha256']
 for receipt in [freeze,start]:
  for n,h in receipt['code'].items():assert sha(R/n)==h,n
 for n,h in start['contract'].items():assert sha(R/n)==h,n
 for n,h in freeze['models'].items():assert sha(R/n)==h,n
 for kind in MODELS:
  for seed in SEEDS:
   ident=f'{kind}__seed{seed}';d=pd.read_parquet(R/'predictions'/f'{ident}.parquet');p=d[[f'p_{j:02d}' for j in range(12)]].to_numpy();rr=np.argsort(-p,axis=1,kind='stable')
   assert len(d)==612 and d.sample_id.tolist()==f.sample_id.tolist() and d.class_id.tolist()==f.class_id.tolist()
   assert np.isfinite(p).all() and (p>=0).all() and np.allclose(p.sum(1),1,atol=1e-6)
   assert np.array_equal(rr,d[[f'rank_{j+1:02d}' for j in range(12)]].to_numpy())
   assert d.predicted_class.tolist()==[CLASSES[j] for j in rr[:,0]]
   assert d.mechanism_marginal.tolist()==[MECH[j] for j in p.reshape(-1,6,2).sum(2).argmax(1)]
   assert d.target_marginal.tolist()==[TARGET[j] for j in p.reshape(-1,6,2).sum(1).argmax(1)]
   x=inputs(v,mask,names,kind);out=R/'models'/ident
   assert d.config_sha256.eq(sha(R/'config.json')).all()
   path=out/('checkpoint.pt' if kind in ['LSTM','TCN'] else 'model.joblib');assert d.model_sha256.eq(sha(path)).all()
   if kind in ['LSTM','TCN']:
    model=SequenceClassifier(kind,48,12).cuda();model.load_state_dict(torch.load(path,weights_only=True));model.eval()
    with torch.no_grad():p2=np.concatenate([model(torch.tensor(a,device='cuda')).softmax(1).cpu().numpy() for a in np.array_split(x,6)])
    logs=pd.read_csv(R/'logs'/f'{ident}.csv');best=logs.sort_values(['validation_macro_f1','validation_loss','epoch'],ascending=[False,True,True]).iloc[0]
    fit=json.loads((out/'fit.json').read_text());assert best.epoch==fit['selected_epoch'];assert len(logs)<=50
   else:p2=joblib.load(path).predict_proba(x)
   err=float(np.max(abs(p2-p)));maxerr=max(maxerr,err);assert np.allclose(p,p2,atol=2e-6,rtol=1e-6)
   replays.append({'model':kind,'seed':seed,'cases':612,'max_probability_error':err})
   for row in metrics[(metrics.model==kind)&(metrics.seed==seed)].itertuples():
    ii=(d.effective_split.eq(row.role)|d.slot.eq(row.role))&d.class_id.ge(0)
    if row.stratum=='network':ii &= d.mechanism.ne('instance-stop')
    elif row.stratum!='all':ii &= d.mechanism.eq(row.stratum)
    y=d.loc[ii,'class_id'].to_numpy(int);assert len(y)==row.n
    assert np.bincount(y,minlength=12).tolist()==json.loads(row.support)
    labels=json.loads(row.f1_labels);expected=sorted(set(y)) if row.role in ['diagnostic_holdout','diagnostic5'] or row.stratum!='all' else list(range(12));assert labels==expected
    vals,cm=independent(y,p[ii],labels)
    for k,value in vals.items():
     error=abs(value-getattr(row,k));maxmetric=max(maxmetric,error);assert error<1e-7,(ident,row.role,row.stratum,k,value,getattr(row,k))
    if row.stratum=='all':assert np.array_equal(cm,pd.read_csv(R/'metrics'/f'CM__{ident}__{row.role}.csv',index_col=0).to_numpy())
    checked+=1
 sums=pd.read_csv(R/'metrics/SUMMARY.csv')
 for row in sums.itertuples():
  g=metrics[(metrics.model==row.model)&(metrics.role==row.role)&(metrics.stratum==row.stratum)];assert len(g)==3
  for k in ['top1','macro_f1','top3','mrr','balanced_accuracy','mechanism_accuracy','mechanism_macro_f1','target_accuracy']:
   assert np.isclose(getattr(row,k+'_mean'),g[k].mean()) and np.isclose(getattr(row,k+'_std'),g[k].std(ddof=1))
 source=json.loads((R/'audit/package_hashes.json').read_text());assert len(source)==154 and all(sha(P/x['path'])==x['expected'] for x in source)
 prov=json.loads((R/'audit/code_reuse.json').read_text());assert sha(prov['old_models'])==prov['old_models_sha256'] and sha(prov['old_train'])==prov['old_train_sha256']
 tracker=json.loads((R/'tracker.json').read_text());assert len(tracker)==15 and all(t['status']=='success' for t in tracker)
 dump('audit/RESULT_VERIFICATION.json',{'status':'PASS','metric_rows_recomputed':checked,'max_metric_error':maxmetric,'max_replay_probability_error':maxerr,'replays':replays,'frozen_sources_unchanged':True,'package_154_hashes_match':True,'all15_success':True,'summary_mean_sample_std_recomputed':True,'checkpoint_selection_verified':True,'method':'independent numpy confusion matrix/rank arithmetic; same saved estimators replayed; no refitting'})
 print('VERIFICATION_PASS',checked,maxmetric,maxerr,flush=True)
if __name__=='__main__':torch.set_num_threads(4);main()
