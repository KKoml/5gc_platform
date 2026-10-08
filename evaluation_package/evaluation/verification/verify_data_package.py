import csv,gzip,json,hashlib
from pathlib import Path
from datetime import datetime,timezone
import pandas as pd
HERE=Path(__file__).resolve().parent; TOP=HERE.parents[2]; DM=TOP/'data_machine'; DATA=DM/'dataset'
index=json.loads((DATA/'metadata/TIMESERIES_1S_INDEX.json').read_text());dic=pd.read_csv(DATA/'metadata/PLATFORM_FIELD_DICTIONARY_400.csv'); task_dict=pd.read_csv(DATA/'task_data/metadata/EXPERIMENT_KPI_DICTIONARY.csv'); report=[];common_header=None
for item in index:
 slot=item['slot']; p=DATA/f'timeseries_1s/{slot}/v3_timeseries.csv.gz';cov=json.loads((p.parent/'v3_field_coverage.json').read_text())
 with gzip.open(p,'rt',newline='',encoding='utf-8') as f:
  reader=csv.reader(f);header=next(reader);n=0;prev=None;interval_counts={};
  for row in reader:
   n+=1
   ts=datetime.fromisoformat(row[0].replace('Z','+00:00'))
   if prev is not None:
    dt=int((ts-prev).total_seconds());interval_counts[dt]=interval_counts.get(dt,0)+1
   prev=ts
 assert len(header)==81 and n==item['rows']==cov['row_count'] and len(cov['fields'])==81
 assert item['columns']==len(header) and item['grid_seconds']==1
 assert interval_counts=={1:n-1},(slot,interval_counts)
 if common_header is None:common_header=header
 assert header==common_header
 report.append(dict(slot=slot,rows=n,columns=len(header),interval_counts=interval_counts,coverage=cov['summary']))
assert sum(r['rows'] for r in report)==611777
assert len(dic)==400 and dic.canonical_id.nunique()==400
assert int(dic.field_role.eq('metric').sum())==215
assert len(task_dict)==24
# Current dictionary is a broad catalog, while data columns are a versioned runtime view.
field_roles=dic[dic.field_name.isin(common_header)].groupby('field_role').field_name.nunique().to_dict()
metric_defs=dic[dic.field_name.isin(common_header)&dic.field_role.eq('metric')].drop_duplicates('field_name')
coverage_status={}
for slot in [f'D{i:02}' for i in range(1,8)]:
 c=json.loads((DATA/f'timeseries_1s/{slot}/v3_field_coverage.json').read_text())['fields']
 statuses={x.field_name:c[x.field_name]['status'] for _,x in metric_defs.iterrows()}
 coverage_status[slot]={k:sum(v==k for v in statuses.values()) for k in sorted(set(statuses.values()))}
# Validate 5-second task tables, exact 5-s timestamps where continuous, and explicit UTC intersection with 1-s tables.
rel=[]
for slot in [f'D{i:02}' for i in range(1,8)]:
 p=DATA/f'task_data/data/{slot}/core_features_5s.parquet';f=pd.read_parquet(p)
 obs=[x for x in f.columns if x not in ['run_id','cutoff_time']]
 assert len(obs)==24 and f.run_id.nunique()==1 and f.run_id.iloc[0]==slot
 t=pd.to_datetime(f.cutoff_time,utc=True);diff=t.diff().dt.total_seconds().dropna();
 one=pd.read_csv(DATA/f'timeseries_1s/{slot}/v3_timeseries.csv.gz',usecols=['time','host_cpu_pct','host_mem_used_pct','host_loadavg_1'])
 one['time']=pd.to_datetime(one.time,utc=True); merged=f[['cutoff_time','core-host-local__cpu_pct','core-host-local__mem_used_pct','core-host-local__loadavg_1']].copy();merged['cutoff_time']=pd.to_datetime(merged.cutoff_time,utc=True);joined=merged.merge(one,left_on='cutoff_time',right_on='time',validate='one_to_one')
 exact={}
 for a,b in [('core-host-local__cpu_pct','host_cpu_pct'),('core-host-local__mem_used_pct','host_mem_used_pct'),('core-host-local__loadavg_1','host_loadavg_1')]:
  x=joined[a].to_numpy(float);y=joined[b].to_numpy(float);valid=pd.notna(x)&pd.notna(y);exact[a]=dict(paired=int(valid.sum()),equal_count=int((x[valid]==y[valid]).sum()),max_abs_diff=float(abs(x[valid]-y[valid]).max()) if valid.any() else None)
 rel.append(dict(slot=slot,rows=len(f),variables=len(obs),time_min=str(t.min()),time_max=str(t.max()),step_counts={str(int(k)):int(v) for k,v in diff.value_counts().sort_index().items()},exact_1s_timestamp_intersection=len(joined),same_timestamp_comparison=exact))
report_obj={'status':'passed','one_second':report,'total_rows':sum(r['rows'] for r in report),'columns':81,'field_dictionary':{'entries':len(dic),'unique_ids':dic.canonical_id.nunique(),'metric_role_entries':int(dic.field_role.eq('metric').sum()),'fields_in_81_column_schema':field_roles,'distinct_metric_role_fields_in_schema':int(metric_defs.field_name.nunique()),'per_run_coverage_status_for_metric_role_fields':coverage_status},'task_dictionary_entries':len(task_dict),'five_second_task_relation':rel,'interpretation':'The 5 s tables and 1 s exports share slot identities and exactly aligned UTC timestamps, but direct host-field values are not elementwise identical at those times. They are separately derived views and cannot be claimed as simple 1 s-to-5 s resampling from this package. Current schema/dictionary counts are confirmed; the exact historical version behind the manuscript 32-metric statement is not resolved by present-day hashes.'}
(HERE/'results'/'data_schema_verification.json').write_text(json.dumps(report_obj,indent=2,ensure_ascii=False)+'\n')
print(json.dumps({k:v for k,v in report_obj.items() if k not in ['one_second','five_second_task_relation']},indent=2,ensure_ascii=False))
