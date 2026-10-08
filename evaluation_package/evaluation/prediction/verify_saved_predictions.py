#!/usr/bin/env python3
"""Recompute T1 metrics and paper cells from saved per-sample predictions only."""
import csv, json, math, statistics
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'
EVID=ROOT.parent/'evidence'
scales={'n3_downlink':1e-6,'n6_aggregate':1e-6,'host_cpu':1.0}
metrics={}
with (OUT/'metrics_long.csv').open(newline='',encoding='utf-8') as f:
    for r in csv.DictReader(f):
        if r['metric']=='MAE' and r['task']=='T1' and r['target'] in scales and r['slot'] in ('D06','D07'):
            metrics[(r['target'],r['model'],r['slot'],int(r['seed']),r['subset'])]=float(r['value'])
checked=0
for (target,model,slot,seed,subset),expected in metrics.items():
    file=OUT/'predictions'/f'T1_{target}_{model}_seed{seed}_{slot}.parquet'
    index=OUT/'indices'/f'T1_{target}_{slot}.parquet'
    if not file.is_file() or not index.is_file():
        raise FileNotFoundError(file if not file.is_file() else index)
    pred=pd.read_parquet(file); idx=pd.read_parquet(index)
    if pred.sample_id.tolist()!=idx.sample_id.tolist(): raise AssertionError(f'sample ordering mismatch: {file.name}')
    np.testing.assert_array_equal(pred.label.to_numpy(),idx.label.to_numpy())
    if not np.isfinite(pred.prediction.to_numpy()).all(): raise AssertionError(f'nonfinite output: {file.name}')
    mask=np.ones(len(pred),dtype=bool) if subset=='all_eligible' else pred.valid_target_buckets.eq(10).to_numpy()
    actual=float(np.abs(pred.loc[mask,'label'].to_numpy()-pred.loc[mask,'prediction'].to_numpy()).mean()*scales[target])
    if not math.isclose(actual,expected,rel_tol=0,abs_tol=3e-8):
        raise AssertionError(f'MAE mismatch: {file.name} {subset} got={actual:.15g}, expected={expected:.15g}')
    checked+=1

# Paper rule: for each learned seed, equally average D06 and D07, then mean/sample SD.
group={}
for (target,model,slot,seed,subset),value in metrics.items():
    if subset=='all_eligible' and target in scales and model in ('RecentMean10','PatchTST','XGBoost'):
        group.setdefault((target,model,seed),{})[slot]=value
expected={
 ('n3_downlink','RecentMean10'):(6.254,None),('n3_downlink','PatchTST'):(4.252,.036),('n3_downlink','XGBoost'):(3.849,.013),
 ('n6_aggregate','RecentMean10'):(7.139,None),('n6_aggregate','PatchTST'):(5.066,.008),('n6_aggregate','XGBoost'):(4.345,.028),
 ('host_cpu','RecentMean10'):(3.168,None),('host_cpu','PatchTST'):(2.624,.007),('host_cpu','XGBoost'):(2.487,.019)}
cells={}
for key,want in expected.items():
    vals=[sum(v[s] for s in ('D06','D07'))/2 for (t,m,_),v in group.items() if (t,m)==key and all(s in v for s in ('D06','D07'))]
    mean=statistics.mean(vals); sd=statistics.stdev(vals) if len(vals)>1 else None
    ok=round(mean,3)==want[0] and (want[1] is None or round(sd,3)==want[1])
    if not ok: raise AssertionError(f'paper cell mismatch {key}: mean={mean}, sd={sd}, expected={want}')
    cells[f'{key[0]}:{key[1]}']={'mean':mean,'sample_sd':sd,'seeds':len(vals),'matches_3dp':True}

# Confirm the paper's per-run/seed input ablation rows against the same saved metric receipts.
input_map={'Operation timing':'XGBoost_schedule_only','Multivariate observations':'XGBoost','Target history':'XGBoost_target_history_and_mask'}
target_map={'N3 downlink bitrate':'n3_downlink','N6 aggregate bitrate':'n6_aggregate','Host CPU utilization':'host_cpu'}
ablation=0
with (EVID/'prediction_inputs.csv').open(newline='',encoding='utf-8') as f:
    for r in csv.DictReader(f):
        key=(target_map[r['Target']],input_map[r['Input']],'D06' if r['Test run']=='1' else 'D07',int(r['seed']),'all_eligible')
        if key not in metrics or not math.isclose(float(r['value']),metrics[key],rel_tol=0,abs_tol=1e-12):
            raise AssertionError(f'input ablation mismatch for target/method/test/seed')
        ablation+=1
if ablation!=54: raise AssertionError(f'expected 54 input ablation values, got {ablation}')

receipt={'scope':'saved-output recomputation only; no training or inference','per_seed_mae_rows_recomputed':checked,'paper_mean_sd_cells_recomputed':len(cells),'input_ablation_per_run_seed_values_checked':ablation,'paper_cells':cells}
(OUT/'T1_SAVED_OUTPUT_RECOMPUTATION.json').write_text(json.dumps(receipt,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(receipt,indent=2,ensure_ascii=False))
