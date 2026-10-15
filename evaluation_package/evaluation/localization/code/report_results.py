"""Descriptive post-freeze reporting; never selects or retrains models."""
import json
import numpy as np,pandas as pd
from pipeline import R,CLASSES,MECH,TARGET,MODELS,SEEDS,load,dump
ROLES=['test','D06','D07','external_validation','supplementary_only','diagnostic_holdout']
f,v,mask,names=load();raw=np.load(R/'cache/windows.npz')['raw'];metrics=pd.read_csv(R/'metrics/ALL_METRICS.csv');summary=pd.read_csv(R/'metrics/SUMMARY.csv')
# Fixed seed17 case examples, not selected on score. All seeds retained in full exports.
case_rows=[];composites=[];confusions=[];deltas=[]
for model in MODELS:
 for seed in SEEDS:
  d=pd.read_parquet(R/'predictions'/f'{model}__seed{seed}.parquet');p=d[[f'p_{j:02d}' for j in range(12)]].to_numpy();r=np.argsort(-p,axis=1,kind='stable')
  for i in np.flatnonzero(d.class_id.lt(0)):
   row=d.iloc[i];composites.append({'model':model,'seed':seed,'sample_id':row.sample_id,'fault_id':row.fault_id,'target':row.target_instance,'true_interventions':'n3-delay+n3-loss','top3':'; '.join(f'{CLASSES[j]} ({p[i,j]:.6f})' for j in r[i,:3]),'closed_set_accuracy':'not_applicable'})
  for role in ['test','external_validation','supplementary_only','diagnostic_holdout']:
   ii=np.flatnonzero(d.effective_split.eq(role)&d.class_id.ge(0));cm=pd.crosstab(pd.Categorical(d.iloc[ii].mechanism,categories=MECH),pd.Categorical(d.iloc[ii].mechanism_marginal,categories=MECH),dropna=False)
   cm.index=MECH;cm.columns=MECH;cm.to_csv(R/'metrics'/f'MECHANISM_CM__{model}__seed{seed}__{role}.csv')
   for a in MECH:
    for b in MECH:
     if a!=b and cm.loc[a,b]>0:confusions.append({'model':model,'seed':seed,'role':role,'true_mechanism':a,'pred_mechanism':b,'count':int(cm.loc[a,b])})
  if seed==17:
   for role in ['test','external_validation','supplementary_only']:
    sub=d[d.effective_split.eq(role)&d.class_id.ge(0)&d.predicted_class.ne(d.class_name)]
    for true,g in sub.groupby('class_name',sort=True):
     i=int(g.index[0]);row=d.iloc[i];x=raw[i];mm=mask[i];rec={'model':model,'seed':seed,'role':role,'sample_id':row.sample_id,'true_class':true,'predicted_class':row.predicted_class,'top3':'; '.join(CLASSES[j] for j in r[i,:3]),'observed_fraction':float(mm.mean())}
     for j,n in enumerate(names):
      obs=x[:,j][mm[:,j]];rec[n+'__observed_mean']=float(obs.mean()) if len(obs) else None;rec[n+'__observed_fraction']=float(mm[:,j].mean())
     case_rows.append(rec)
pd.DataFrame(composites).to_csv(R/'reports/COMPOSITE_CASES.csv',index=False);pd.DataFrame(case_rows).to_csv(R/'reports/ERROR_CASE_OBSERVATIONS.csv',index=False)
c=pd.DataFrame(confusions).groupby(['model','role','true_mechanism','pred_mechanism'])['count'].sum().reset_index().sort_values(['model','role','count'],ascending=[True,True,False]);c.to_csv(R/'metrics/MECHANISM_CONFUSIONS_ALL_SEEDS.csv',index=False)
for a,b in [('RF_24','RF_FL10'),('RF_24','ReadyMaskRF'),('LSTM','ReadyMaskRF'),('TCN','ReadyMaskRF')]:
 for role in ROLES:
  aa=metrics[(metrics.model==a)&(metrics.role==role)&(metrics.stratum=='all')].set_index('seed');bb=metrics[(metrics.model==b)&(metrics.role==role)&(metrics.stratum=='all')].set_index('seed')
  for metric in ['top1','macro_f1','mechanism_accuracy','mechanism_macro_f1','target_accuracy']:
   delta=aa[metric]-bb[metric];base=float(bb[metric].mean());deltas.append({'model':a,'control':b,'role':role,'metric':metric,'absolute_delta_mean':delta.mean(),'paired_seed_delta_std':delta.std(ddof=1),'relative_change':float(delta.mean()/base) if base else None,'interpretation':'descriptive seed-paired difference, not physical replication significance'})
pd.DataFrame(deltas).to_csv(R/'metrics/CONTROL_COMPARISONS.csv',index=False)
# Full tables are generated mechanically; interpretation lives in the final report.
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','|'+'|'.join(['---']*len(headers))+'|']+['| '+' | '.join(str(x) for x in row)+' |' for row in rows])
def pm(row,metric,pct=True):
 scale=100 if pct else 1;return f'{getattr(row,metric+"_mean")*scale:.2f} ± {getattr(row,metric+"_std")*scale:.2f}'
parts=['# Full numerical tables','Mean ± sample standard deviation over three random seeds, not three independent physical collections. Metrics are percentages (%) except MRR.']
for role in ['validation']+ROLES:
 g=summary[(summary.role==role)&(summary.stratum=='all')].set_index('model').loc[MODELS].reset_index()
 parts += [f'## {role}',table(['Model','Joint Top1 %','Joint Macro-F1 %','Top3 %','MRR','Balanced Acc %','Mechanism Acc %','Mechanism Macro-F1 %','Associated-target Acc %'],[[r.model,pm(r,'top1'),pm(r,'macro_f1'),pm(r,'top3'),pm(r,'mrr',False),pm(r,'balanced_accuracy'),pm(r,'mechanism_accuracy'),pm(r,'mechanism_macro_f1'),pm(r,'target_accuracy')] for r in g.itertuples()])]
for role in ['test','external_validation','supplementary_only','diagnostic_holdout']:
 g=summary[(summary.role==role)&summary.stratum.isin(['network','instance-stop']+MECH[:-1])]
 parts += [f'## {role}: network/shutdown and per-mechanism results', 'All rankings consider the full 12 classes. Stratified macro-F1 averages only classes supported by ground truth; predictions into other classes still count as misses.',table(['Model','Ground-truth subset','Joint Top1 %','Joint Macro-F1 %','Mechanism Acc %','Associated-target Acc %'],[[r.model,r.stratum,pm(r,'top1'),pm(r,'macro_f1'),pm(r,'mechanism_accuracy'),pm(r,'target_accuracy')] for r in g.itertuples()])]
(R/'reports/FULL_TABLES_ZH.md').write_text('\n\n'.join(parts))
print('REPORT_TABLES_WRITTEN')
