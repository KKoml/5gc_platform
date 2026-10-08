"""Replay supervised RF checkpoints; recalibrate only from D05 and score held-out test."""
from pathlib import Path
import json,sys
import numpy as np
import pandas as pd
HERE=Path(__file__).resolve().parent;TOP=HERE.parents[2]
EVAL=TOP/'evaluation_package'/'evaluation'; RF=EVAL/'detection'/'supervised_rf';DATA=TOP/'data_machine'/'dataset'/'task_data'
OUT=HERE/'results'/'detection';OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(RF/'code'));sys.path.insert(0,str(RF/'code'/'baseline_runtime'))
from baseline_runtime.data import PackageData,Preprocessor
from baseline_runtime.evaluation import evaluate_binary,calibrate_thresholds
from pilot import summarize
D=PackageData(DATA);rows=[];tol=1e-12
paper=pd.read_csv(RF/'paper_metrics/rf_test_seed_rows.csv',float_precision='round_trip')
for folder in sorted((RF/'fits').glob('FD_detection__RF_full__seed*')):
    cfg=json.loads((folder/'fit_config.json').read_text());pp=Preprocessor.from_dict(cfg['preprocessor']);model=__import__('joblib').load(folder/'model.joblib')
    thresholds=json.loads((folder/'thresholds.json').read_text())['operating_points']
    threshold_diffs={};test_metrics=[]
    for split in ['validation','test']:
        idx=D.index('FD_detection',split=split,feature_set='FD_detection_24')
        raw=D.raw_windows(idx,'FD_detection_24');mat,*_=summarize(raw,pp);score=model.predict_proba(mat)[:,1]
        saved=pd.read_parquet(folder/'predictions'/f'{split}.parquet')
        assert idx.sample_id.astype(str).tolist()==saved.sample_id.astype(str).tolist(),(folder.name,split,'sample ids')
        assert np.array_equal(idx.y.to_numpy(),saved.y.to_numpy()),(folder.name,split,'labels')
        delta=np.abs(score-saved.score.to_numpy(float));assert np.allclose(score,saved.score.to_numpy(float),rtol=0,atol=tol),(folder.name,split,float(delta.max()))
        runs=D.runs.loc[D.runs.split.eq(split),'run_id'].astype(str);events=D.episodes[D.episodes.run_id.astype(str).isin(set(runs))].copy();eligible=D.evaluability[D.evaluability.run_id.astype(str).isin(set(runs))].copy()
        if split=='validation':
            pred=idx.copy();pred['score']=score;pred['prediction_valid']=True
            fresh=calibrate_thresholds(pred,events,'FD_detection',budgets=[0.1,1.0],event_evaluability=eligible)
            for budget in ['0.1','1.0']:
                diff=abs(float(thresholds[budget]['threshold'])-float(fresh[str(float(budget))]['threshold']))
                threshold_diffs[budget]=diff;assert diff<=tol,(folder.name,'D05 threshold',budget,diff)
        else:
            orig=paper[(paper.seed.eq(cfg['seed']))&(paper.split.eq('test'))]
            pred=idx.copy();pred['score']=score;pred['prediction_valid']=True
            for budget in [0.1,1.0]:
                result=evaluate_binary(pred,events,float(thresholds[str(budget)]['threshold']),'FD_detection',event_evaluability=eligible)['metrics']
                want=orig[orig.budget.eq(budget)].iloc[0]
                fields=['event_recall_all_main','event_recall_eligible_main','false_alerts_per_hour','auprc_unadjusted','f1_unadjusted','first_detection_delay_median_seconds','hit_event_count','false_alert_count','effective_normal_hours']
                differences={k:abs(float(result[k])-float(want[k])) if np.isfinite(float(result[k])) and np.isfinite(float(want[k])) else 0. for k in fields}
                assert max(differences.values())<=1e-6,(folder.name,budget,differences)
                test_metrics.append({'budget':budget,'max_metric_abs_difference':max(differences.values()),'paper_fields':fields,'recomputed':{k:result[k] for k in fields}})
        rows.append({'fit':folder.name,'seed':cfg['seed'],'split':split,'n':len(idx),'max_score_abs_difference':float(delta.max()),'threshold_max_abs_difference':max(threshold_diffs.values(),default=0.),'paper_metrics':test_metrics if split=='test' else []})
        print(json.dumps(rows[-1]),flush=True)
report={'status':'PASS','tol_score_absolute':tol,'tol_metric_absolute':1e-6,'rows':rows,'fit_count':len({x['fit'] for x in rows}),'scope':'RF seed17/29/43; full D05 validation and D06-D07 test; thresholds recalibrated from replayed D05 only; test metrics evaluated using frozen thresholds'}
(OUT/'SUPERVISED_RF_REPLAY.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');print(json.dumps(report,ensure_ascii=False))
