#!/usr/bin/env python3
import csv,json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parent
fexpected={('n3_downlink','RecentMean10'):6.254,('n3_downlink','PatchTST'):4.252,('n3_downlink','XGBoost'):3.849,('n6_aggregate','RecentMean10'):7.139,('n6_aggregate','PatchTST'):5.066,('n6_aggregate','XGBoost'):4.345,('host_cpu','RecentMean10'):3.168,('host_cpu','PatchTST'):2.624,('host_cpu','XGBoost'):2.487}
fg=defaultdict(list)
with (ROOT/'evidence/forecast_metrics.csv').open(newline='') as f:
 for r in csv.DictReader(f):
  if (r['target'],r['model']) in fexpected:fg[(r['target'],r['model'])].append(float(r['mean']))
assert len(fg)==9 and all(round(sum(v)/len(v),3)==fexpected[k] for k,v in fg.items())
expected=json.loads((ROOT/'evidence/imputation/compact_table_aggregation.json').read_text())
rows=defaultdict(list)
with (ROOT/'imputation/results/summary.csv').open(newline='') as f:
 for r in csv.DictReader(f):
  if r['slot'] in ('D06','D07') and r['method'] in ('median','ffill','linear','H','M'):rows[(r['target'],r['condition'],r['method'])].append(float(r['mae']))
t={'0':'RX','1':'TX','2':'CPU'};conds={'0':'20\\%','1':'30 s','2':'60 s','3':'120 s'};actual={}
for (x,y,m),v in rows.items():actual.setdefault((t[x],conds[y]),{})[m]=sum(v)/len(v)
assert len(actual)==12
for row in expected:
 key=(row['target'],row['condition']);got=[round(actual[key][m],3) for m in ['median','ffill','linear','H','M']];want=[round(float(v),3) for v in row['values']];assert got==want,(key,got,want)
print(json.dumps({'prediction_mean_cells':9,'prediction_means_match_3dp':True,'imputation_table_cells':60,'imputation_cells_match_3dp':True,'scope':'aggregation only; no training or inference'},indent=2))
