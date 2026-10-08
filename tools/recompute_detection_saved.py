"""Recompute detector operating points from saved scores without loading weights."""
from pathlib import Path
import json, runpy, sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'evaluation_package/evaluation'
OUT=ROOT/'checks/current'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    normal=runpy.run_path(str(E/'verification/replay_normal_only_metrics.py'))
    rows=[dict(model=r['model'],seed=r['seed'],budget=r['budget'],**r['metrics']) for r in normal['raw']]
    sys.path.insert(0,str(E/'detection'))
    from normal_only.data import PackageData
    from normal_only.evaluation import calibrate_thresholds,evaluate_binary
    data=PackageData(ROOT/'data_machine/dataset/task_data')
    rf=E/'detection/supervised_rf';ref=pd.read_csv(rf/'paper_metrics/rf_test_seed_rows.csv',float_precision='round_trip')
    maxdelta=0.
    for folder in sorted((rf/'fits').glob('FD_detection__RF_full__seed*')):
        cfg=json.loads((folder/'fit_config.json').read_text());thresholds=json.loads((folder/'thresholds.json').read_text())['operating_points']
        for split in ['validation','test']:
            saved=pd.read_parquet(folder/'predictions'/f'{split}.parquet')
            idx=data.index('FD_detection',split=split,feature_set='FD_detection_24')
            assert idx.sample_id.astype(str).tolist()==saved.sample_id.astype(str).tolist()
            assert np.array_equal(idx.y,saved.y)
            runs=set(data.runs.loc[data.runs.split.eq(split),'run_id'].astype(str))
            episodes=data.episodes[data.episodes.run_id.astype(str).isin(runs)]
            eligibility=data.evaluability[data.evaluability.run_id.astype(str).isin(runs)]
            if split=='validation':
                new=calibrate_thresholds(saved,episodes,'FD_detection',budgets=[.1,1.],event_evaluability=eligibility)
                for b in ['0.1','1.0']:assert abs(float(new[b]['threshold'])-float(thresholds[b]['threshold']))<1e-12
                continue
            for budget in [.1,1.]:
                got=evaluate_binary(saved,episodes,float(thresholds[str(budget)]['threshold']),'FD_detection',event_evaluability=eligibility)['metrics']
                want=ref[ref.seed.eq(cfg['seed'])&ref.budget.eq(budget)&ref.split.eq('test')].iloc[0]
                fields=['event_recall_all_main','event_recall_eligible_main','false_alerts_per_hour','auprc_unadjusted','f1_unadjusted','first_detection_delay_median_seconds','hit_event_count','false_alert_count','effective_normal_hours']
                for k in fields:
                    a,b=float(got[k]),float(want[k]);assert np.isfinite(a)==np.isfinite(b)
                    delta=abs(a-b) if np.isfinite(a) else 0.;assert delta<1e-6;maxdelta=max(maxdelta,delta)
                rows.append(dict(model='RF_supervised',seed=int(cfg['seed']),budget=budget,**got))
    pd.DataFrame(rows).to_csv(OUT/'detection_per_seed.csv',index=False)
    report={'status':'PASS','scope':'saved D05/test scores only; no weights, inference or training','normal_only_seed_budget_rows':18,'rf_seed_budget_rows':6,'rf_max_metric_difference':maxdelta,'threshold_selection':'D05 only; test thresholds fixed'}
    (OUT/'detection_saved_metrics.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
