"""Validate delivered cutoff-conditioned windows and prepare isolated tensors."""
from pathlib import Path
import os
import json, shutil, time
import numpy as np
import pandas as pd
import yaml
from . import data as d
OLD=Path(os.environ['DGATE_PREFIXFIX_LEGACY_PARENT'])
SUP=Path(os.environ['DGATE_PREFIXFIX_SUPPLEMENT_ROOT'])
PKG=Path(os.environ['DGATE_PREFIXFIX_INPUT_PACKAGE'])

def configure():
 c=yaml.safe_load((OLD/'resolved_config.yaml').read_text()); sup=yaml.safe_load((SUP/'resolved_config.yaml').read_text())
 for task,names in [('t1',['RecentMean10','ARIMA','PatchTST','TimeFilter','XGBoost']),('t2',['PCA','IsolationForest','AE','TranAD','KANAD'])]:
  specs={s['id']:s for s in c[task]['models']};specs.update({s['id']:s for s in sup[task]['models']})
  c[task]['models']=[specs[n] for n in names]
 c['resolved'].update(output_root=str(d.ROOT/'outputs'),data_version='w1-fourfield-prefixfix-20260917',view_id='cutoff_conditioned_strict18_missing18',purpose='fourfield_prefix_repaired_offline_rerun',observation_support_status='four_fields_prefix_repaired_other_legacy_scope_limits_retained',device='cuda',threads=16)
 c['resolved'].pop('continuation_source',None)
 c['repair']=dict(package=str(PKG),parent=str(OLD),paper='PAPER_REFERENCE_NOT_INCLUDED',history_statistics='all train candidate window positions for T1; clean train windows for T2; no timestamp dedup',zero_old_checkpoint_reuse=True)
 (d.ROOT/'resolved_config.yaml').write_text(yaml.safe_dump(c,sort_keys=False,allow_unicode=True))
 return c

def history(c,slot,task,receipts):
 source=PKG/f'data/{slot}/{task}_history.csv';out=d.ROOT/f'cache/{slot}';out.mkdir(exist_ok=True)
 if task=='T1':
  target=pd.read_csv(PKG/f'data/{slot}/T1_targets.csv'); idx=target.drop_duplicates('window_id').reset_index(drop=True)
 else:idx=pd.read_csv(PKG/f'data/{slot}/T2_index.csv')
 count=len(idx);features=c['resolved']['features'];masks=[f+'__missing' for f in features]
 a=np.lib.format.open_memmap(out/f'{task}_raw_windows.npy',mode='w+',dtype='float64',shape=(count,60,18))
 ids=[];offset=0;check=[]
 cols=['run_id','slot','task','window_id','anchor_epoch','history_position','history_row_epoch','history_row_index']+features+masks
 for frame in pd.read_csv(source,usecols=cols,chunksize=60000):
  assert len(frame)%60==0
  n=len(frame)//60
  pos=frame.history_position.to_numpy().reshape(n,60)
  assert np.array_equal(pos,np.broadcast_to(np.arange(60),(n,60)))
  times=frame.history_row_epoch.to_numpy().reshape(n,60);anchors=frame.anchor_epoch.to_numpy().reshape(n,60)
  assert np.array_equal(times,anchors+np.arange(-60,0))
  assert np.all(anchors==anchors[:,0:1]); assert frame.slot.eq(slot).all() and frame.task.eq(task).all()
  wid=frame.window_id.to_numpy().reshape(n,60);assert np.all(wid==wid[:,0:1])
  assert np.array_equal(wid[:,0],idx.window_id.iloc[offset:offset+n].to_numpy())
  assert frame.run_id.eq(idx.run_id.iloc[0]).all()
  expected=pd.to_datetime(idx.anchor_c.iloc[offset:offset+n],utc=True).astype('int64').to_numpy()//10**9
  assert np.array_equal(anchors[:,0],expected)
  rows=frame.history_row_index.to_numpy().reshape(n,60)
  assert np.array_equal(rows,rows[:,0:1]+np.arange(60))
  raw=frame[features].to_numpy(dtype=float);missing=frame[masks].to_numpy(dtype=float)
  assert np.array_equal(missing,(~np.isfinite(raw)).astype(float)),(slot,task,'mask mismatch')
  raw[~np.isfinite(raw)]=np.nan;a[offset:offset+n]=raw.reshape(n,60,18)
  check.extend(rows[:,0]+60);offset+=n
 assert offset==count;a.flush()
 if task=='T2':assert np.array_equal(idx.cutoff_row,np.array(check))
 idx['tensor_row']=np.arange(count);idx['verified_cutoff_row']=check
 for path in [source]:
  st=path.stat();receipts.append(dict(path=str(path),sha256=d.digest(path),size=st.st_size,mtime_ns=st.st_mtime_ns))
 return a,idx

def run():
 start=time.time();c=configure();receipts=[];counts=[];audit=[]
 archive=Path(os.environ['DGATE_PREFIXFIX_SOURCE_ARCHIVE'])
 assert d.digest(archive)=='b68c8266f16f458e3f79a1ebd77a925fcc73eec6661193e76cc94b5f992475d1'
 for slot in [f'D{i:02}' for i in range(1,8)]:
  for task in ['T1','T2']:
   a,idx=history(c,slot,task,receipts)
   if task=='T1':
    ts=PKG/f'data/{slot}/T1_targets.csv';targets=pd.read_csv(ts)
    for target in [t['id'] for t in c['data']['targets']]:
     t=targets[targets.target_id.eq(target)].reset_index(drop=True)
     assert t.window_id.tolist()==idx.window_id.tolist()
     values=t.target_cells.fillna('').str.split(';',expand=True).replace('',np.nan).astype(float).to_numpy()
     assert values.shape==(len(t),10);finite=np.isfinite(values).sum(1)
     assert np.array_equal(finite,t.finite_target_buckets)
     good=finite>=8;assert np.array_equal(good,t.eligible.eq(1))
     expected=np.nansum(values[good],1)/finite[good]
     np.testing.assert_allclose(expected,t.loc[good,'target_mean'],rtol=1e-6,atol=1e-5)
     for field,offset in [('target_start',60),('target_end',70)]:
      assert (pd.to_datetime(t[field],utc=True)-pd.to_datetime(t.anchor_c,utc=True)).dt.total_seconds().eq(offset).all()
     legacy=OLD/f'outputs/indices/T1_{target}_{slot}.parquet';old=pd.read_parquet(legacy)
     m=idx.loc[good,['verified_cutoff_row','tensor_row','window_id']].copy().rename(columns={'verified_cutoff_row':'cutoff_row'})
     f=old.merge(m,on='cutoff_row',how='inner',validate='one_to_one',sort=False)
     assert len(f)==int(good.sum())
     assert np.array_equal(pd.to_datetime(f.cutoff_time,utc=True).astype('int64').to_numpy()//10**9,t.loc[good,'anchor_epoch'].to_numpy())
     f['label']=t.loc[good,'target_mean'].to_numpy();f['valid_target_buckets']=finite[good]
     f.to_parquet(d.ROOT/f'outputs/indices/T1_{target}_{slot}.parquet',index=False)
     counts.append(dict(task='T1',target=target,slot=slot,candidates=len(t),eligible=len(f),excluded=len(t)-len(f),fit_all_clean=int(f.window_all_clean.sum()),index_hash=d.index_hash(f)))
   else:
    ts=PKG/f'data/{slot}/T2_index.csv';legacy=OLD/f'outputs/indices/T2_command_overlap_{slot}.parquet';old=pd.read_parquet(legacy)
    f=old.merge(idx[['run_id','slot','cutoff_row','anchor_row','tensor_row','window_id','strict_observed_numeric_at_anchor','anchor_c']],on=['run_id','slot','cutoff_row','anchor_row'],validate='one_to_one',how='left',sort=False)
    assert f.sample_id.tolist()==old.sample_id.tolist() and f.tensor_row.notna().all()
    assert (pd.to_datetime(f.cutoff_time,utc=True)==pd.to_datetime(f.anchor_c,utc=True)).all()
    observed=np.isfinite(a[f.tensor_row.to_numpy(),-1]).sum(1)
    assert np.array_equal(observed,f.strict_observed_numeric_at_anchor) and (observed>0).all()
    f['valid_target_buckets']=observed
    f.to_parquet(d.ROOT/f'outputs/indices/T2_command_overlap_{slot}.parquet',index=False)
    counts.append(dict(task='T2',target='command_overlap',slot=slot,candidates=len(idx),eligible=len(f),excluded=len(idx)-len(f),fit_all_clean=int(f.window_all_clean.sum()),index_hash=d.index_hash(f)))
   for path in [ts]+list((OLD/'outputs/indices').glob(f'{task}_*_{slot}.parquet')):
    st=path.stat();receipts.append(dict(path=str(path),sha256=d.digest(path),size=st.st_size,mtime_ns=st.st_mtime_ns))
   audit.append(dict(slot=slot,task=task,candidate_windows=len(idx),positions=60,mask_equals_nonfinite=True,physical_time_pass=True))
   print(json.dumps(audit[-1]),flush=True);del a
  # Legacy raw access is isolated to unchanged ARIMA targets and the paper's RAN probe.
  source=d.load_slot(c,slot)
  raw=source['raw'].copy();raw[:,[2,5,6,7]]=np.nan
  np.save(d.ROOT/f'cache/{slot}/raw.npy',raw)
  np.save(d.ROOT/f'cache/{slot}/ran_raw.npy',source['ran'])
  ep=Path(c['resolved']['task_root'])/f'episodes_by_slot/{slot}.parquet';shutil.copy2(ep,d.ROOT/f'outputs/indices/events_{slot}.parquet')
  for path in [Path(c['resolved']['dataset_root'])/source['item']['path'],Path(c['resolved']['task_root'])/f'rows/{slot}.parquet',ep]:
   st=path.stat();sha=d.digest(path)
   if path.suffix=='.csv':assert sha==source['item']['sha256']
   receipts.append(dict(path=str(path),sha256=sha,size=st.st_size,mtime_ns=st.st_mtime_ns))
  del source
 scalers={}
 for task in ['T1','T2','RAN']:
  rows=[]
  for slot in c['data']['split']['train']:
   if task=='RAN':
    raw=np.load(d.ROOT/f'cache/{slot}/ran_raw.npy');labels=pd.read_parquet(Path(c['resolved']['task_root'])/f'rows/{slot}.parquet')
    rows.append(raw[labels.clean_baseline.eq(1)])
   else:
    raw=np.load(d.ROOT/f'cache/{slot}/{task}_raw_windows.npy',mmap_mode='r')
    if task=='T2':
     f=pd.read_parquet(d.ROOT/f'outputs/indices/T2_command_overlap_{slot}.parquet');raw=raw[f.loc[f.window_all_clean,'tensor_row'].to_numpy()]
    rows.append(raw.reshape(-1,18))
  a=np.concatenate(rows);valid=np.isfinite(a);count=valid.sum(0);assert (count>0).all(),('all missing',task)
  mean=np.nanmean(a,0);std=np.nanstd(a,0);low=np.nanmin(a,0);spread=np.nanmax(a,0)-low
  scalers[task]=dict(median=np.nanmedian(a,0).tolist(),mean=mean.tolist(),scale=np.where(std>1e-8,std,1).tolist(),minimum=low.tolist(),spread=np.where(spread>1e-8,spread,1).tolist(),valid_count=count.tolist(),fit_slots=c['data']['split']['train'],window_position_weighting=task!='RAN')
  del a,raw,rows,valid
 d.json_write(d.ROOT/'outputs/scalers.json',scalers)
 for slot in [f'D{i:02}' for i in range(1,8)]:
  for key,sc in [('T1','T1'),('T2','T2'),('TranAD','T2')]:
   raw=np.load(d.ROOT/f'cache/{slot}/{sc}_raw_windows.npy',mmap_mode='r');dest=np.lib.format.open_memmap(d.ROOT/f'cache/{slot}/{key}.npy',mode='w+',dtype='float32',shape=raw.shape[:2]+(36,))
   for lo in range(0,len(raw),1024):dest[lo:lo+1024]=d.transform(raw[lo:lo+1024].reshape(-1,18),scalers[sc],key=='TranAD').reshape(-1,60,36)
   dest.flush();del dest,raw
  np.save(d.ROOT/f'cache/{slot}/RAN.npy',d.transform(np.load(d.ROOT/f'cache/{slot}/ran_raw.npy'),scalers['RAN']))
 d.json_write(d.ROOT/'outputs/data_receipts.json',receipts)
 pd.DataFrame(counts).to_csv(d.ROOT/'outputs/sample_counts.csv',index=False)
 d.json_write(d.ROOT/'outputs/WINDOW_VALIDATION.json',dict(passed=True,checks=audit,elapsed_seconds=time.time()-start,scope='complete delivered tensor structure/masks/time, labels and train-only preprocessing; not independent PCAP replay'))
 derived=[]
 for folder in ['cache','outputs/indices']:
  for path in (d.ROOT/folder).rglob('*'):
   if path.is_file():derived.append(dict(path=str(path.relative_to(d.ROOT)),sha256=d.digest(path)))
 d.json_write(d.ROOT/'outputs/derived_data_manifest.json',derived)
 print('REPAIRED_PREPARED',time.time()-start,flush=True)
if __name__=='__main__':run()
