"""Isolated, bounded FD/FP pilot. All selection is train/D05 only."""
from pathlib import Path
import argparse
import datetime as dt
import hashlib
import json
import time
import warnings

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import average_precision_score

from baseline_runtime.data import PackageData, Preprocessor
from baseline_runtime.evaluation import calibrate_thresholds, evaluate_binary

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / 'configs/protocol.json').read_text())
PKG = Path(CFG['package_root'])
OLD = Path(CFG['baseline_root'])
TASKS = ['FD_detection', 'FP_forewarning']


def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2,
                                  default=lambda x: x.item() if isinstance(x, np.generic) else str(x)) + '\n')


def log(event, **kw):
    item = {'time': stamp(), 'event': event, **kw}
    print(json.dumps(item, ensure_ascii=False), flush=True)
    with (ROOT / 'logs/access_and_execution.jsonl').open('a') as f:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')


def pp_for(data, task):
    fs = data.default_feature_set(task)
    p = OLD / 'artifacts/preprocessors' / f'{task}__{fs}.json'
    pp = Preprocessor.load(p)
    assert pp.fit_split == 'train'
    return pp


def summarize(raw, pp):
    """Use only the contracted past/current 12 steps, no index metadata."""
    v, observed = pp.transform(raw)
    parts = [v[:, -1], v.mean(1), v.std(1), v[:, -1] - v[:, 0],
             v[:, -3:].mean(1) - v[:, :3].mean(1),
             observed.mean(1), observed[:, -1].astype(float)]
    labels = ['last', 'mean', 'std', 'last_minus_first', 'recent_minus_early',
              'observed_fraction', 'last_observed']
    names = [f'{c}::{s}' for s in labels for c in pp.columns]
    matrix = np.concatenate(parts, axis=1).astype(np.float32)
    n = len(pp.columns)
    numeric = np.array([k < 5*n and not pp.ready[k % n] for k in range(7*n)])
    state = np.array([k >= 5*n or pp.ready[k % n] for k in range(7*n)])
    assert matrix.shape[1] == len(names) and np.isfinite(matrix).all()
    return matrix, names, numeric, state


class Context:
    def __init__(self, allow_heldout=False):
        self.data = PackageData(PKG)
        self.allow_heldout = allow_heldout
        self.cache = {}

    def get(self, task, split):
        if split not in ['train', 'validation']:
            assert self.allow_heldout and (ROOT/'configs/FINAL_FREEZE.json').exists()
        key = (task, split)
        if key not in self.cache:
            pp = pp_for(self.data, task)
            idx = self.data.index(task, split=split)
            if task == 'FP_forewarning' and split == 'train':
                expected = self.data.index(task, fit=True)
                assert idx.sample_id.tolist() == expected.sample_id.tolist()
                assert len(idx) == 54572
            raw = self.data.raw_windows(idx, pp.feature_set)
            matrix, names, numeric, state = summarize(raw, pp)
            self.cache[key] = (idx, raw, matrix, names, numeric, state, pp)
            log('load_features', task=task, split=split, n=len(idx), feature_set=pp.feature_set)
        return self.cache[key]

    def events(self, split):
        runs = self.data.runs.loc[self.data.runs.split.eq(split), 'run_id']
        return (self.data.episodes[self.data.episodes.run_id.isin(runs)].copy(),
                self.data.evaluability[self.data.evaluability.run_id.isin(runs)].copy())


def scores_frame(idx, score, valid=None):
    frame = idx.copy()
    frame['score'] = np.asarray(score, dtype=float)
    frame['prediction_valid'] = np.isfinite(score) if valid is None else valid
    return frame


def evaluate(ctx, task, name, seed, split, pred, thresholds, folder):
    events, eligible = ctx.events(split)
    out = folder / 'evaluation' / split
    out.mkdir(parents=True, exist_ok=True)
    metrics = []
    for budget in CFG['budgets']:
        op = thresholds[str(budget)]
        assert op['threshold'] is not None
        result = evaluate_binary(pred, events, op['threshold'], task,
                                 event_evaluability=eligible)
        m = {'task': task, 'candidate': name, 'seed': seed, 'split': split,
             'budget': budget, **result['metrics']}
        m['frozen_threshold_status'] = op['status']
        metrics.append(m)
        suffix = str(budget).replace('.', 'p')
        result['event_results'].to_parquet(out/f'events_{suffix}.parquet', index=False)
        result['alerts'].to_parquet(out/f'alerts_{suffix}.parquet', index=False)
        result['event_metrics_by_group'].to_csv(out/f'strata_{suffix}.csv', index=False)
    pd.DataFrame(metrics).to_csv(out/'metrics.csv', index=False)
    return metrics


def calibrate(ctx, task, name, seed, pred, folder):
    assert pred.split.eq('validation').all() and pred.slot.eq('D05').all()
    events, eligible = ctx.events('validation')
    thresholds = calibrate_thresholds(pred, events, task, budgets=CFG['budgets'],
                                     event_evaluability=eligible)
    write_json(folder/'thresholds.json', {'created_at':stamp(), 'selection_split':'D05',
               'test_or_external_used':False, 'operating_points':thresholds})
    (folder/'predictions').mkdir(exist_ok=True)
    pred.to_parquet(folder/'predictions/validation.parquet', index=False)
    return thresholds, evaluate(ctx, task, name, seed, 'validation', pred, thresholds, folder)


def subset(x, mode, numeric, state):
    return x if mode == 'full' else x[:, numeric if mode == 'numeric' else state]


def fit_supervised(ctx, task, candidate, seed):
    name = candidate['name']
    folder = ROOT/'fits'/f'{task}__{name}__seed{seed}'
    if (folder/'completed.json').exists():
        return pd.read_csv(folder/'evaluation/validation/metrics.csv').to_dict('records')
    folder.mkdir(parents=True, exist_ok=True)
    train, raw, x, names, numeric, state, pp = ctx.get(task, 'train')
    val, _, vx, _, vn, vs, _ = ctx.get(task, 'validation')
    y = train.y.to_numpy(dtype=int)
    fitx = subset(x, candidate['mode'], numeric, state)
    valx = subset(vx, candidate['mode'], vn, vs)
    if candidate['kind'] == 'hgb':
        model = HistGradientBoostingClassifier(**CFG['hgb_fixed'],
                    max_depth=candidate['max_depth'], class_weight='balanced', random_state=seed)
    else:
        model = RandomForestClassifier(**CFG['rf_fixed'], max_depth=candidate['max_depth'],
                                       random_state=seed)
    log('fit_start',task=task,candidate=name,seed=seed,train_n=len(train),columns=fitx.shape[1])
    started=time.perf_counter()
    model.fit(fitx, y)
    seconds=time.perf_counter()-started
    score=model.predict_proba(valx)[:,1]
    joblib.dump(model,folder/'model.joblib')
    train[['sample_id','run_id','slot']].to_csv(folder/'fit_sample_ids.csv.gz',index=False)
    selected_names=np.asarray(names)[np.ones(len(names),bool) if candidate['mode']=='full'
                                     else numeric if candidate['mode']=='numeric' else state].tolist()
    write_json(folder/'fit_config.json',{'task':task,'candidate':candidate,'seed':seed,
        'fit_scope':'all eligible D01-D04; labeled supervision','fit_samples':len(train),
        'positive_samples':int(y.sum()),'feature_names':selected_names,'fit_seconds':seconds,
        'created_at':stamp(),'preprocessor':pp.to_dict(),'test_or_external_used':False,
        'model_params':model.get_params(),'checkpoint_sha256':digest(folder/'model.joblib')})
    thresholds,metrics=calibrate(ctx,task,name,seed,scores_frame(val,score),folder)
    write_json(folder/'completed.json',{'time':stamp(),'status':'trained_and_D05_calibrated'})
    log('fit_done',task=task,candidate=name,seed=seed,seconds=seconds,
        D05=[{'budget':m['budget'],'recall':m['event_recall_all_main'],'FAR':m['false_alerts_per_hour'],
              'AP':m['auprc_unadjusted']} for m in metrics])
    return metrics


def score_marginal(raw, pp, reference, topk):
    v, observed=pp.transform(raw)
    current=np.abs(v[:,-1]).astype(float)
    tail=np.empty_like(current)
    for j in range(current.shape[1]):
        refs=reference[j]
        rank=np.searchsorted(refs,current[:,j],side='left')
        tail[:,j]=-np.log10((len(refs)-rank+1)/(len(refs)+1))
    tail[~observed[:,-1]]=0.0
    tail[:,pp.ready]=0.0
    numeric_count=observed[:,-1,~pp.ready].sum(1)
    score=np.sort(tail,axis=1)[:,-topk:].mean(1)
    return score,numeric_count>0


def frozen_or(split):
    paths=[OLD/'fits'/f'm2__FD_detection__FD_detection_24__{name}__seed17'
           for name in ['AE','ReadyMaskIF']]
    frames=[pd.read_parquet(p/'predictions'/f'{split}.parquet') for p in paths]
    ids=frames[0].sample_id.astype(str).tolist()
    assert ids==frames[1].sample_id.astype(str).tolist()
    thresholds=[json.loads((p/'thresholds/D05.json').read_text())['operating_points']['0.1']['threshold']
                for p in paths]
    alarms=[];valid=[]
    for f,thr in zip(frames,thresholds):
        ok=f.prediction_valid.to_numpy(bool)&np.isfinite(f.score)
        alarms.append(ok&(f.score.to_numpy()>=thr));valid.append(ok)
    frame=frames[0].copy()
    frame['score']=(alarms[0]|alarms[1]).astype(float)
    frame['prediction_valid']=valid[0]|valid[1]
    return frame


def fit_unsupervised(ctx):
    task='FD_detection';seed=17
    train,raw,_,_,_,_,pp=ctx.get(task,'train')
    clean_ids=set(ctx.data.index(task,fit=True).sample_id)
    clean=train.sample_id.isin(clean_ids).to_numpy()
    assert clean.sum()==55196 and train.loc[clean,'y'].eq(0).all()
    vals,obs=pp.transform(raw[clean]);current=np.abs(vals[:,-1])
    reference=[np.sort(current[obs[:,-1,j],j]) for j in range(current.shape[1])]
    idx,vr,_,_,_,_,_=ctx.get(task,'validation')
    output=[]
    for name,k in [('train_normal_channel_max',1),('train_normal_channel_top3',3),
                   ('frozen_AE_or_ReadyMaskIF',None)]:
        folder=ROOT/'fits'/f'{task}__{name}__seed17';folder.mkdir(exist_ok=True)
        if (folder/'completed.json').exists():
            output.extend(pd.read_csv(folder/'evaluation/validation/metrics.csv').to_dict('records'));continue
        if k is None:
            pred=frozen_or('validation')
            config={'kind':'frozen_or','source_models':['AE_seed17','ReadyMaskIF_seed17'],
                    'source_threshold_budget':0.1,'note':'Boolean OR; union FAR is re-evaluated, not assumed.'}
        else:
            s,valid=score_marginal(vr,pp,reference,k);pred=scores_frame(idx,s,valid)
            joblib.dump(reference,folder/'reference.joblib')
            config={'kind':'marginal','topk':k,'fit_samples':55196,
                    'note':'Normal-trained empirical tail of absolute robust-scaled current values; explicit Ready/masks excluded.'}
        write_json(folder/'fit_config.json',{'candidate':{'name':name},'task':task,'seed':17,
                   'supervision':'normal-only or existing normal-only models; D05 labeled calibration',**config})
        _,metrics=calibrate(ctx,task,name,17,pred,folder);output.extend(metrics)
        write_json(folder/'completed.json',{'time':stamp(),'status':'D05_calibrated'})
        log('unsupervised_done',candidate=name,D05=[{'budget':m['budget'],
            'recall':m['event_recall_all_main'],'FAR':m['false_alerts_per_hour']} for m in metrics])
    return output


def diagnose():
    ctx=Context();channel=[];effects=[];schedules=[]
    pp=pp_for(ctx.data,'FD_detection')
    for row in ctx.data.runs[ctx.data.runs.split.isin(['train','validation'])].itertuples():
        frame=pd.read_parquet(PKG/'data'/row.run_id/'core_features_5s.parquet')
        values=frame[pp.columns].to_numpy(float)
        times=pd.to_datetime(frame.cutoff_time,utc=True).astype('int64').to_numpy()/1e9
        for j,c in enumerate(pp.columns):
            v=values[:,j];valid=np.isfinite(v)
            channel.append({'split':row.split,'slot':row.slot,'channel':c,'rows':len(v),
                'observed_fraction':valid.mean(),'unique_observed':len(np.unique(v[valid])),
                'zero_fraction_of_observed':float((v[valid]==0).mean()) if valid.any() else np.nan,
                'train_scaler':pp.scale[j]})
        episodes=ctx.data.episodes[(ctx.data.episodes.run_id==row.run_id)&ctx.data.episodes.episode_scope.eq('main')]
        ordered=pd.to_datetime(episodes.start_time,utc=True).sort_values().astype('int64').to_numpy()/1e9
        diffs=np.diff(ordered)
        schedules.append({'slot':row.slot,'split':row.split,'events':len(ordered),
             'interval_min_s':float(diffs.min()),'interval_median_s':float(np.median(diffs)),
             'interval_max_s':float(diffs.max()),'interval_std_s':float(diffs.std())})
        allstarts=pd.to_datetime(episodes.start_time,utc=True).astype('int64').to_numpy()/1e9
        allends=pd.to_datetime(episodes.end_exclusion_time,utc=True).astype('int64').to_numpy()/1e9
        for e in episodes.itertuples():
            s=pd.Timestamp(e.start_time).timestamp();end=pd.Timestamp(e.end_time).timestamp()
            pre=(times>=s-70)&(times<s-10);early=(times>=s-130)&(times<s-70)
            active=(times>=s)&(times<min(s+60,end))
            overlap=bool(((allstarts<s-10)&(allends>s-130)).any())
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',RuntimeWarning)
                before=np.nanmedian(values[pre],axis=0);earlier=np.nanmedian(values[early],axis=0)
                after=np.nanmedian(values[active],axis=0)
            for j,c in enumerate(pp.columns):
                effects.append({'slot':row.slot,'split':row.split,'fault_id':e.fault_id,
                    'fault_type':e.fault_type,'target':e.target_instance,'channel':c,
                    'pre_overlaps_prior_exclusion':overlap,'pre_observed':float(np.isfinite(values[pre,j]).mean()),
                    'active_observed':float(np.isfinite(values[active,j]).mean()),
                    'pre_median':before[j],'active_median':after[j],
                    'active_minus_pre_train_scale':(after[j]-before[j])/pp.scale[j],
                    'pretrend_train_scale':(before[j]-earlier[j])/pp.scale[j]})
    pd.DataFrame(channel).to_csv(ROOT/'diagnostics/CHANNEL_COVERAGE_TRAIN_D05.csv',index=False)
    pd.DataFrame(effects).to_csv(ROOT/'diagnostics/EVENT_RESPONSE_TRAIN_D05.csv',index=False)
    pd.DataFrame(schedules).to_csv(ROOT/'diagnostics/INJECTION_INTERVALS_TRAIN_D05.csv',index=False)
    log('diagnostics_complete',channel_rows=len(channel),event_channel_rows=len(effects))


def develop():
    assert not (ROOT/'configs/SELECTION_FREEZE.json').exists()
    ctx=Context();metrics=[]
    for task in TASKS:
        for candidate in CFG['supervised_candidates']:
            metrics.extend(fit_supervised(ctx,task,candidate,17))
    metrics.extend(fit_unsupervised(ctx))
    frame=pd.DataFrame(metrics);frame.to_csv(ROOT/'metrics/DEVELOPMENT_METRICS.csv',index=False)
    winners={}
    for task in TASKS:
        allowed={c['name'] for c in CFG['supervised_candidates'] if c['mode']!='state'}
        sub=frame[(frame.task==task)&(frame.budget==0.1)&frame.candidate.isin(allowed)]
        ordered=sub.sort_values(['event_recall_all_main','false_alerts_per_hour','auprc_unadjusted','candidate'],
                               ascending=[False,True,False,True])
        winners[task]=ordered.iloc[0].candidate
    unsup=frame[(frame.task=='FD_detection')&(frame.budget==0.1)&frame.candidate.isin(CFG['fd_unsupervised_candidates'])]
    u=unsup.sort_values(['event_recall_all_main','false_alerts_per_hour','auprc_unadjusted','candidate'],ascending=[False,True,False,True]).iloc[0].candidate
    selected={'created_at':stamp(),'supervised_winners':winners,'unsupervised_winner':u,
              'development_table_sha256':digest(ROOT/'metrics/DEVELOPMENT_METRICS.csv'),
              'protocol_sha256':digest(ROOT/'configs/protocol.json'),'selection_roles':['train','validation'],
              'test_or_external_used_for_candidate_selection':False,'historically_nonblind':True}
    write_json(ROOT/'configs/SELECTION_FREEZE.json',selected)
    log('selection_frozen',**selected)


def confirm():
    selected=json.loads((ROOT/'configs/SELECTION_FREEZE.json').read_text());ctx=Context()
    records=[];evaluated=[]
    for task,winner in selected['supervised_winners'].items():
        for name in [winner,'HGB_state_d3']:
            candidate=next(c for c in CFG['supervised_candidates'] if c['name']==name)
            for seed in [17,29,43]:
                records.extend(fit_supervised(ctx,task,candidate,seed))
                evaluated.append(f'{task}__{name}__seed{seed}')
    # Preserve all three predefined no-positive-training alternatives for evaluation;
    # the winner label is frozen before their held-out metrics are exposed.
    evaluated.extend(f'FD_detection__{name}__seed17' for name in CFG['fd_unsupervised_candidates'])
    pd.DataFrame(records).to_csv(ROOT/'metrics/CONFIRM_D05_METRICS.csv',index=False)
    hashes={}
    for name in evaluated:
        folder=ROOT/'fits'/name
        for path in folder.iterdir():
            if path.is_file() and path.name in ['model.joblib','reference.joblib','fit_config.json','thresholds.json']:
                hashes[str(path.relative_to(ROOT))]=digest(path)
    write_json(ROOT/'configs/FINAL_FREEZE.json',{'created_at':stamp(),
        'selection_freeze_sha256':digest(ROOT/'configs/SELECTION_FREEZE.json'),
        'protocol_sha256':digest(ROOT/'configs/protocol.json'),'fit_ids':evaluated,'file_hashes':hashes,
        'heldout_roles':CFG['heldout_after_freeze'],'historically_nonblind':True})
    log('all_frozen',fit_count=len(evaluated))


def heldout():
    freeze=json.loads((ROOT/'configs/FINAL_FREEZE.json').read_text())
    for rel,want in freeze['file_hashes'].items():assert digest(ROOT/rel)==want
    assert digest(ROOT/'configs/SELECTION_FREEZE.json')==freeze['selection_freeze_sha256']
    assert digest(ROOT/'configs/protocol.json')==freeze['protocol_sha256']
    ctx=Context(allow_heldout=True);metrics=[]
    for split in CFG['heldout_after_freeze']:
        for name in freeze['fit_ids']:
            folder=ROOT/'fits'/name;config=json.loads((folder/'fit_config.json').read_text())
            task=config['task'];seed=config['seed'];candidate=config['candidate']['name']
            target=folder/'evaluation'/split/'metrics.csv'
            if target.exists():
                metrics.extend(pd.read_csv(target).to_dict('records'));continue
            idx,raw,x,_,numeric,state,pp=ctx.get(task,split)
            if config.get('kind')=='frozen_or':pred=frozen_or(split)
            elif config.get('kind')=='marginal':
                ref=joblib.load(folder/'reference.joblib');s,v=score_marginal(raw,pp,ref,config['topk'])
                pred=scores_frame(idx,s,v)
            else:
                model=joblib.load(folder/'model.joblib')
                s=model.predict_proba(subset(x,config['candidate']['mode'],numeric,state))[:,1]
                pred=scores_frame(idx,s)
            assert pred.sample_id.astype(str).tolist()==idx.sample_id.astype(str).tolist()
            pred.to_parquet(folder/'predictions'/f'{split}.parquet',index=False)
            thresholds=json.loads((folder/'thresholds.json').read_text())['operating_points']
            result=evaluate(ctx,task,candidate,seed,split,pred,thresholds,folder)
            metrics.extend(result)
            log('heldout_evaluated',task=task,candidate=candidate,seed=seed,split=split)
        # Keep memory bounded by releasing raw windows after each independent role.
        ctx.cache.clear()
    pd.DataFrame(metrics).to_csv(ROOT/'metrics/HELDOUT_METRICS.csv',index=False)
    allframe=pd.concat([pd.read_csv(ROOT/'metrics/DEVELOPMENT_METRICS.csv'),
                       pd.read_csv(ROOT/'metrics/CONFIRM_D05_METRICS.csv'),pd.DataFrame(metrics)],ignore_index=True)
    allframe=allframe.drop_duplicates(['task','candidate','seed','split','budget'])
    allframe.to_csv(ROOT/'metrics/ALL_METRICS.csv',index=False)
    fields=['event_recall_all_main','false_alerts_per_hour','auprc_unadjusted',
            'first_detection_delay_median_seconds','recorded_onset_lead_median_seconds']
    fields=[f for f in fields if f in allframe]
    groups=allframe.groupby(['task','candidate','split','budget'],dropna=False)
    out=groups[fields].agg(['mean','std','count']);out.columns=['_'.join(c) for c in out.columns]
    out.reset_index().to_csv(ROOT/'metrics/SUMMARY.csv',index=False)
    write_json(ROOT/'metrics/COMPLETION.json',{'time':stamp(),'status':'complete',
        'heldout_metric_rows':len(metrics),'frozen_fit_count':len(freeze['fit_ids']),
        'scope':'post-hoc nonblind pilot; no test feedback into new candidate selection'})


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=['diagnose','develop','confirm','evaluate'])
    stage=parser.parse_args().stage
    {'diagnose':diagnose,'develop':develop,'confirm':confirm,'evaluate':heldout}[stage]()
