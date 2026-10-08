"""Additional diagnostic only: does the known experiment clock predict onset?

Not a main model, never used to select telemetry candidates. Period is estimated
from training annotations only; each run origin is its first observed grid, not
its first fault. Written before any new held-out pilot evaluation.
"""
import sys
import time
import numpy as np
import pandas as pd
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier
from pilot import ROOT, PKG, CFG, Context, stamp, write_json, digest, log, scores_frame, calibrate, evaluate

NAME='schedule_phase_only_DIAGNOSTIC'
FOLDER=ROOT/'fits'/f'FP_forewarning__{NAME}__seed17'


def matrix(ctx,idx,period):
    elapsed=np.empty(len(idx),float)
    for run,positions in idx.groupby('run_id',sort=False).indices.items():
        t=pd.read_parquet(PKG/'data'/run/'core_features_5s.parquet',columns=['cutoff_time'])
        origin=pd.Timestamp(t.iloc[0,0])
        elapsed[positions]=(pd.to_datetime(idx.iloc[positions].anchor_time,utc=True)-origin).dt.total_seconds()
    phase=2*np.pi*(elapsed%period)/period
    return np.column_stack([np.sin(phase),np.cos(phase)])


def fit():
    assert not (ROOT/'metrics/HELDOUT_METRICS.csv').exists()
    ctx=Context();task='FP_forewarning';FOLDER.mkdir(exist_ok=True)
    tr=ctx.data.index(task,split='train');va=ctx.data.index(task,split='validation')
    events=ctx.data.episodes[(ctx.data.episodes.run_split=='train')&(ctx.data.episodes.episode_scope=='main')]
    diffs=[]
    for _,e in events.groupby('run_id'):
        s=pd.to_datetime(e.start_time,utc=True).sort_values().astype('int64').to_numpy()/1e9
        diffs.extend(np.diff(s))
    period=float(round(np.median(diffs)/5)*5)
    write_json(ROOT/'configs/TIMING_DIAGNOSTIC_ADDENDUM.json',{
        'created_at':stamp(),'status':'added_before_heldout_pilot_evaluation',
        'motivation':'Train/D05 event interval audit found about 900-second periodic injection.',
        'period_from':'training event intervals median rounded to five-second grid',
        'period_seconds':period,'origin':'own-run first observed cutoff timestamp, never first event',
        'features':['sin(2*pi*elapsed/period)','cos(2*pi*elapsed/period)'],
        'main_candidate_selection_affected':False,'seed':17,'diagnostic_only':True,
        'prohibition':'Do not count this as network telemetry warning capability or physical precursor evidence.'})
    m=HistGradientBoostingClassifier(**CFG['hgb_fixed'],max_depth=3,class_weight='balanced',random_state=17)
    start=time.perf_counter();m.fit(matrix(ctx,tr,period),tr.y.astype(int));elapsed=time.perf_counter()-start
    joblib.dump(m,FOLDER/'model.joblib')
    pred=scores_frame(va,m.predict_proba(matrix(ctx,va,period))[:,1])
    _,results=calibrate(ctx,task,NAME,17,pred,FOLDER)
    write_json(FOLDER/'fit_config.json',{'task':task,'seed':17,'candidate':{'name':NAME},
        'kind':'schedule_diagnostic','period':period,'created_at':stamp(),'fit_samples':len(tr),
        'fit_seconds':elapsed,'diagnostic_only':True,'test_or_external_used':False})
    tr[['sample_id','run_id','slot']].to_csv(FOLDER/'fit_sample_ids.csv.gz',index=False)
    write_json(FOLDER/'CONTROL_FREEZE.json',{'created_at':stamp(),
        'file_hashes':{n:digest(FOLDER/n) for n in ['model.joblib','fit_config.json','thresholds.json']},
        'addendum_sha256':digest(ROOT/'configs/TIMING_DIAGNOSTIC_ADDENDUM.json')})
    log('timing_diagnostic_frozen',D05=[{'budget':r['budget'],'recall':r['event_recall_all_main'],
        'FAR':r['false_alerts_per_hour'],'AP':r['auprc_unadjusted']} for r in results])


def assess():
    import json
    ctx=Context(allow_heldout=True)
    freeze=json.loads((FOLDER/'CONTROL_FREEZE.json').read_text())
    for n,h in freeze['file_hashes'].items():assert digest(FOLDER/n)==h
    config=json.loads((FOLDER/'fit_config.json').read_text());m=joblib.load(FOLDER/'model.joblib')
    th=json.loads((FOLDER/'thresholds.json').read_text())['operating_points']
    records=pd.read_csv(FOLDER/'evaluation/validation/metrics.csv').to_dict('records')
    for split in CFG['heldout_after_freeze']:
        idx=ctx.data.index('FP_forewarning',split=split)
        pred=scores_frame(idx,m.predict_proba(matrix(ctx,idx,config['period']))[:,1])
        pred.to_parquet(FOLDER/'predictions'/f'{split}.parquet',index=False)
        records.extend(evaluate(ctx,'FP_forewarning',NAME,17,split,pred,th,FOLDER))
    pd.DataFrame(records).to_csv(ROOT/'metrics/TIMING_DIAGNOSTIC_METRICS.csv',index=False)
    log('timing_diagnostic_evaluated')


if __name__=='__main__':
    {'fit':fit,'evaluate':assess}[sys.argv[1]]()
