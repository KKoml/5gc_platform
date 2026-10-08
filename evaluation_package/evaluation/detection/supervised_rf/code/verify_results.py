"""Recompute every saved evaluation and replay every fitted model on D05."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
import joblib
from pilot import (ROOT, CFG, Context, digest, stamp, write_json, subset,
                   score_marginal, frozen_or)
from baseline_runtime.evaluation import evaluate_binary
from timing_control import matrix as timing_matrix

ctx=Context(allow_heldout=True)
checks=[];inference=[]
execution=json.loads((ROOT/'configs/EXECUTION_FREEZE.json').read_text())
for name,h in execution['hashes'].items():
    assert digest(ROOT/name)==h, name
freeze=json.loads((ROOT/'configs/FINAL_FREEZE.json').read_text())
for name,h in freeze['file_hashes'].items():assert digest(ROOT/name)==h,name

for folder in sorted((ROOT/'fits').iterdir()):
    config=json.loads((folder/'fit_config.json').read_text())
    task=config['task'];thresholds=json.loads((folder/'thresholds.json').read_text())['operating_points']
    for pred_path in sorted((folder/'predictions').glob('*.parquet')):
        split=pred_path.stem;pred=pd.read_parquet(pred_path)
        idx=ctx.data.index(task,split=split)
        assert pred.sample_id.astype(str).tolist()==idx.sample_id.astype(str).tolist()
        assert np.array_equal(pred.y.to_numpy(),idx.y.to_numpy())
        events,eligible=ctx.events(split)
        original=pd.read_csv(folder/'evaluation'/split/'metrics.csv',float_precision='round_trip')
        for budget in CFG['budgets']:
            result=evaluate_binary(pred,events,thresholds[str(budget)]['threshold'],task,
                                   event_evaluability=eligible)
            want=original[original.budget==budget].iloc[0]
            for field in ['event_recall_all_main','false_alerts_per_hour','auprc_unadjusted',
                          'hit_event_count','false_alert_count','effective_normal_hours']:
                a=float(result['metrics'][field]);b=float(want[field])
                assert (np.isnan(a) and np.isnan(b)) or abs(a-b)<1e-12,(folder.name,split,budget,field,a,b)
            # Independent count checks against the serialized event and alert tables.
            suffix=str(budget).replace('.','p')
            ev=pd.read_parquet(folder/'evaluation'/split/f'events_{suffix}.parquet')
            al=pd.read_parquet(folder/'evaluation'/split/f'alerts_{suffix}.parquet')
            main=ev.episode_scope.eq('main')
            assert int(ev.loc[main,'matched'].sum())==int(want.hit_event_count)
            false=int(al.false_alert_clean_negative.sum()) if len(al) else 0
            assert false==int(want.false_alert_count)
            checks.append({'fit':folder.name,'split':split,'budget':budget,'match':True})
    idx,raw,x,_,numeric,state,pp=ctx.get(task,'validation')
    saved=pd.read_parquet(folder/'predictions/validation.parquet')
    if config.get('kind')=='frozen_or':score=frozen_or('validation').score.to_numpy()
    elif config.get('kind')=='marginal':
        score,_=score_marginal(raw,pp,joblib.load(folder/'reference.joblib'),config['topk'])
    elif config.get('kind')=='schedule_diagnostic':
        score=joblib.load(folder/'model.joblib').predict_proba(timing_matrix(ctx,idx,config['period']))[:,1]
    else:
        score=joblib.load(folder/'model.joblib').predict_proba(subset(x,config['candidate']['mode'],numeric,state))[:,1]
    err=float(np.max(np.abs(score-saved.score.to_numpy())))
    assert err<1e-12,(folder.name,err)
    inference.append({'fit':folder.name,'D05_rows':len(score),'max_abs_error':err})

access=[json.loads(line) for line in (ROOT/'logs/access_and_execution.jsonl').read_text().splitlines()]
freeze_time=json.loads((ROOT/'configs/FINAL_FREEZE.json').read_text())['created_at']
heldout_loads=[a for a in access if a['event']=='load_features' and a['split'] not in ['train','validation']]
assert heldout_loads and all(a['time']>freeze_time for a in heldout_loads)
receipt={'created_at':stamp(),'status':'pass','metric_rows_recomputed':len(checks),
         'D05_checkpoint_replays':len(inference),'D05_predictions_replayed':sum(x['D05_rows'] for x in inference),
         'max_inference_difference':max(x['max_abs_error'] for x in inference),
         'frozen_code_and_models_unchanged':True,'new_heldout_feature_loads_after_final_freeze':True,
         'checks':checks,'inference_checks':inference,
         'limits':'Same evaluation implementation for metric replay, plus independent serialized event/alert count checks. Not a physical-onset or causal audit.'}
write_json(ROOT/'metrics/VERIFICATION.json',receipt)
print(json.dumps({k:v for k,v in receipt.items() if k not in ['checks','inference_checks']},ensure_ascii=False))
