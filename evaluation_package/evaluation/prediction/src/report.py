"""Metric recomputation and integrity checks for the repaired paper-scoped run."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score,roc_auc_score,f1_score,precision_score,recall_score
from . import data as d,engine as e

def regression(y,p):
    err=p-y;ss=float(np.square(y-y.mean()).sum());den=float(np.abs(y).sum())
    return dict(MAE=float(np.abs(err).mean()),RMSE=float(np.sqrt(np.square(err).mean())),
        WAPE=100*float(np.abs(err).sum())/den if den>0 else None,R2=1-float(np.square(err).sum())/ss if ss>0 else None)

def detection(frame):
    y=frame.label.to_numpy(dtype=int);s=frame.score.to_numpy();p=frame.decision.to_numpy(dtype=bool)
    both=len(np.unique(y))==2;clean=(y==0)&frame.window_all_clean.to_numpy(dtype=bool)
    fp=int(p[clean].sum());hours=int(clean.sum())*5/3600
    events=pd.read_parquet(e.OUT/f'indices/events_{frame.slot.iloc[0]}.parquet')
    all_groups=set(events.overlap_group.astype(str));eligible=set(frame.loc[y==1,'overlap_group'].astype(str))&all_groups
    hit=set(frame.loc[(y==1)&p,'overlap_group'].astype(str))&eligible
    return dict(AP=float(average_precision_score(y,s)) if both else None,AUROC=float(roc_auc_score(y,s)) if both else None,
        F1=float(f1_score(y,p,zero_division=0)) if both else None,
        precision=float(precision_score(y,p,zero_division=0)),recall=float(recall_score(y,p,zero_division=0)),
        eligible_event_coverage=len(hit)/len(eligible) if eligible else None,eligible_events=len(eligible),total_registered_events=len(all_groups),
        events_without_eligible_positive_anchors=len(all_groups-eligible),detected_eligible_events=len(hit),
        clean_false_positive_window_decisions_per_eligible_hour=fp/hours if hours>0 else None,
        clean_false_positive_window_decisions=fp,all_clean_negative_windows=int(clean.sum()),eligible_clean_hours=hours,
        positives=int(y.sum()),prevalence=float(y.mean()),threshold=float(frame.threshold.iloc[0]))

def collect(c):
    records=[];receipts=[];counts=pd.read_csv(e.OUT/'sample_counts.csv');target_cfg={t['id']:t for t in c['data']['targets']}
    for file in sorted((e.OUT/'predictions').glob('*.parquet')):
        f=pd.read_parquet(file);task=f.task.iloc[0];target=f.target.iloc[0];slot=f.slot.iloc[0]
        index=pd.read_parquet(e.OUT/f'indices/{task}_{target}_{slot}.parquet')
        assert f.sample_id.tolist()==index.sample_id.tolist(),f'Prediction bijection mismatch {file}'
        np.testing.assert_allclose(f.label,index.label,rtol=0,atol=0)
        receipt=json.loads(file.with_suffix('.json').read_text())
        assert receipt['prediction_sha256']==d.digest(file) and receipt['index_hash']==d.index_hash(index)
        receipts.append(receipt)
        base=dict(data_version=c['resolved']['data_version'],view_id=c['resolved']['view_id'],
            observation_support_status=c['resolved']['observation_support_status'],purpose=c['resolved']['purpose'],task=task,target=target,
            model=f.model.iloc[0],input_panel=receipt['input_panel'],history_s=60,gap_s=60 if task=='T1' else 0,
            run_id=f.run_id.iloc[0],slot=slot,split=f.split.iloc[0],seed=int(f.seed.iloc[0]),config_hash=f.config_hash.iloc[0],
            index_hash=d.index_hash(index),test_status='previously_accessed_post_hoc',prediction_file=str(file.relative_to(d.ROOT)))
        rowcount=counts[(counts.task==task)&(counts.target==target)&(counts.slot==slot)].iloc[0]
        subsets=['all_eligible','complete_10_of_10'] if task=='T1' else ['all_eligible']
        for subset in subsets:
            mask=np.ones(len(f),dtype=bool) if subset=='all_eligible' else f.valid_target_buckets.eq(10).to_numpy()
            z=f.loc[mask];n=len(z)
            if not n:continue
            if task=='T1':
                t=target_cfg[target];scale=t.get('scale_from_bps',1.);values=regression(z.label.to_numpy()*scale,z.prediction.to_numpy()*scale)
                values.update(eligible_window_coverage=n/int(rowcount.candidates));unit=t['report_unit']
            else:values=detection(z);unit='score'
            for metric,value in values.items():
                metric_unit=unit if metric in ['MAE','RMSE'] else ('percent' if metric=='WAPE' else 'dimensionless')
                records.append(dict(**base,subset=subset,metric=metric,value=value,n_samples=n,unit=metric_unit,
                    n_candidate_windows=int(rowcount.candidates),undefined_reason='zero_denominator_or_single_class' if value is None else ''))
    frame=pd.DataFrame(records)
    if len(frame):frame.to_csv(e.OUT/'metrics_long.csv',index=False)
    pd.DataFrame(receipts).to_csv(e.OUT/'inference_timing.csv',index=False)
    return frame

def markdown(headers,rows):
    return '| '+' | '.join(headers)+' |\n| '+' | '.join(['---']*len(headers))+' |\n'+''.join('| '+' | '.join(str(x) for x in row)+' |\n' for row in rows)

def validate(c):
    issues=[]
    for r in json.loads((e.OUT/'data_receipts.json').read_text()):
        p=Path(r['path']);st=p.stat()
        if st.st_size!=r['size'] or st.st_mtime_ns!=r['mtime_ns'] or d.digest(p)!=r['sha256']:issues.append('Original input changed: '+str(p))
    source=json.loads((e.OUT/'TRAINING_SOURCE_LOCK.json').read_text())
    for rel,sha in source.items():
        if d.digest(d.ROOT/rel)!=sha:issues.append('Training source changed: '+rel)
    derived=e.OUT/'derived_data_manifest.json'
    if derived.exists():
        for r in json.loads(derived.read_text()):
            if d.digest(d.ROOT/r['path'])!=r['sha256']:issues.append('Derived input/index changed: '+r['path'])
    d.json_write(e.OUT/'final_integrity.json',dict(original_input_hashes_unchanged=not any(x.startswith('Original') for x in issues),
        training_source_lock_unchanged=not any(x.startswith('Training') for x in issues),
        derived_input_index_hashes_unchanged=not any(x.startswith('Derived') for x in issues),issues=issues))
    if issues:raise RuntimeError('; '.join(issues))
