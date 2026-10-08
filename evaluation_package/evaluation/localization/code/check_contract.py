"""Pre-fit data/input/metric checks without additional formal fits."""
import numpy as np,pandas as pd,json
from pipeline import *
f,v,m,names=load();z=np.load(R/'cache/windows.npz');raw=z['raw'];tr=np.flatnonzero(f.effective_split.eq('train'));va=np.flatnonzero(f.effective_split.eq('validation'));pp=json.loads((R/'models/preprocessing.json').read_text())
assert len(tr)==288 and set(f.iloc[tr].slot)=={'D01','D02','D03','D04'} and len(va)==72 and set(f.iloc[va].slot)=={'D05'}
assert f.iloc[tr].sample_id.tolist()==pp['fit_sample_ids'];assert not set(f.iloc[tr].run_id)&set(f.iloc[va].run_id)
assert not f.iloc[tr].run_id.eq(CORE_RUN).any()
for k in MODELS:
 x=inputs(v,m,names,k);assert np.isfinite(x).all()
 if k=='RF_FL10':
  untouched=set(names)-set(legacy.FEATURE_SETS['FL_primary_10']);vv=v.copy();mm=m.copy()
  for n in untouched:vv[:,:,names.index(n)]=123456;mm[:,:,names.index(n)]=~mm[:,:,names.index(n)]
  assert np.array_equal(x,inputs(vv,mm,names,k))
for j,n in enumerate(names):
 obs=raw[tr,:,j];obs=obs[np.isfinite(obs)];assert np.median(obs)==pp['impute'][j]
 q=np.percentile(obs,[25,75]);s=q[1]-q[0];s=s if s>0 else (np.std(obs) if np.std(obs)>0 else 1)
 assert np.isclose(pp['scale'][j],1 if n.endswith('__ready') else s)
 assert pp['center'][j]==(0 if n.endswith('__ready') else np.median(obs))
# Check probability marginals can legitimately disagree with components of joint argmax.
p=np.zeros((1,12));p[0,:4]=[.30,.01,.29,.28];p[0,4:]=.12/8
assert np.isclose(p.sum(),1) and rank(p)[0,0]==0 and p.reshape(-1,6,2).sum(2).argmax()==1
# Known one-hot case + stable ties, including top3 and reciprocal rank.
p=np.eye(12);assert measures(np.arange(12),p)['macro_f1']==1 and measures(np.arange(12),p)['mrr']==1
p=np.ones((12,12))/12;r=measures(np.arange(12),p);assert np.isclose(r['top1'],1/12) and r['top3']==.25 and np.isclose(r['mrr'],sum(1/np.arange(1,13))/12)
# Output schema survives roundtrip without fitting a model.
p=pd.DataFrame({'sample_id':f.sample_id,'class_id':f.class_id});p.to_parquet(R/'cache/schema_smoke.parquet',index=False);assert p.equals(pd.read_parquet(R/'cache/schema_smoke.parquet'))
dump('audit/extended_contract_checks.json',{'status':'PASS','training_cases':288,'Core24h_fit_cases':0,'train_slots':['D01','D02','D03','D04'],'validation_slots':['D05'],'checks':['explicit_train_only_statistics_recompute','RF10_nonwhitelist_mutation_invariance','finite_model_inputs','marginal_vs_joint_disagreement_example','manual_perfect_and_uniform_ranking_examples','prediction_schema_roundtrip','run_separation']})
print('EXTENDED_CONTRACT_PASS')
