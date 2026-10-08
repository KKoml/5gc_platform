"""Independent arithmetic/window/mask checks plus sampled implementation replay.
Metric arithmetic uses saved truth/predictions, not evaluate.metrics.
"""
from experiment import *
from evaluate import baselines_raw

def audit():
    checks={};issues=[];idx=pd.read_csv(ROOT/'metadata/window_index.csv');runs=pd.read_csv(ROOT/'metadata/runs.csv');sc=np.load(ROOT/'metadata/scales.npz');mt=pd.read_csv(ROOT/'results/metrics.csv');manifest=pd.read_csv(ROOT/'predictions/manifest.csv');ntruth=0;maxerr=0.;replays=[];expected_metric_keys=set();training_rows=[];training_deltas=[]
    assert set(idx[idx.role=='train'].slot)=={'D01','D02','D03','D04'}
    for r in runs.itertuples():
        source=pd.read_parquet(PKG/r.data_path/'core_features_5s.parquet');raw=source[F].to_numpy(float);st=pd.to_datetime(source.cutoff_time,utc=True).astype('int64').to_numpy()//10**9;a=dict(np.load(ROOT/f'data/{r.slot}.npz'));wi=idx[idx.slot==r.slot]
        ep=pd.read_csv(PKG/r.data_path/'episodes.csv');phase=np.zeros(len(raw),np.int8)
        for ev in ep.itertuples():phase[(st>=pd.Timestamp(ev.end_time).timestamp())&(st<pd.Timestamp(ev.end_exclusion_time).timestamp())]=2
        for ev in ep.itertuples():phase[(st>=pd.Timestamp(ev.start_time).timestamp())&(st<pd.Timestamp(ev.end_time).timestamp())]=1
        delta=np.full((len(raw),3),np.nan);delta[1:]=np.where((np.diff(st)==5)[:,None],np.abs(np.diff(raw[:,TARGETS],axis=0)),np.nan)
        if r.split=='train':training_rows.append(raw);training_deltas.append(delta)
        for z in wi.itertuples():
            assert z.row_stop-z.row_start==60;assert np.all(np.diff(st[z.row_start:z.row_stop])==5);assert np.array_equal(raw[z.row_start:z.row_stop],a['raw'][z.window],equal_nan=True);assert np.array_equal(a['original_valid'][z.window],np.isfinite(a['raw'][z.window]));assert z.last-z.start==295;assert np.array_equal(a['phase'][z.window],phase[z.row_start:z.row_stop]);assert np.array_equal(a['delta'][z.window],delta[z.row_start:z.row_stop],equal_nan=True)
        if r.split=='train':continue
        hh=np.load(ROOT/f'masks/{r.slot}.npz')['artificial_time'];truth=pd.read_parquet(ROOT/f'predictions/{r.slot}_truth.parquet');ntruth+=len(truth)
        for c,n in enumerate([12,6,12,24]):
            mask=hh[:,:,c];assert np.all(mask.sum(axis=-1)==n)
            if c:
                assert not mask[...,:6].any() and not mask[...,-6:].any();assert np.all(np.diff(np.where(mask.reshape(-1,60))[1].reshape(-1,n),axis=-1)==1)
        assert np.array_equal(truth.timestamp.to_numpy(),a['time'][truth.window,truth.step]);assert np.array_equal(truth.phase.to_numpy(),a['phase'][truth.window,truth.step])
        dv=a['delta'][truth.window,truth.step,truth.target];cl=np.where(np.isfinite(dv),np.where(dv>sc['change_threshold'][truth.target],'high','rest'),'unknown');assert np.array_equal(truth.change.to_numpy(),cl)
        target=np.array(TARGETS)[truth.target];actual=a['raw'][truth.window,truth.step,target];assert np.isfinite(actual).all();assert np.array_equal(actual,truth.truth.to_numpy());msmap={101:0,202:1,303:2};mis=truth.mask_seed.map(msmap).to_numpy();assert hh[truth.window,truth.target,truth.condition,mis,truth.step].all()
        expected=sum(int((hh[:,k]&np.isfinite(a['raw'][:,:,t])[:,None,None,:]).sum()) for k,t in enumerate(TARGETS));assert expected==len(truth);assert not truth.duplicated(['window','target','condition','mask_seed','step']).any()
        # Fixed geometric replay cases, independent of error; all targets/conditions and masks represented.
        for branch in ['M','H']:
            replaycases=[]
            for k,t in enumerate(TARGETS):
                for c in range(4):
                    for mi in range(3):
                        w=(k*13+c*7+mi*3)%len(a['raw'])
                        candidates=[(w+j)%len(a['raw']) for j in range(len(a['raw']))];w=next(j for j in candidates if (hh[j,k,c,mi]&np.isfinite(a['raw'][j,:,t])).any());h=hh[w,k,c,mi];raw0=a['raw'][w];changed=raw0.copy();changed[np.ix_(h,group(t))]=987654321.;x,v=inputs(raw0,t,h,branch,sc['mean'],sc['std']);x2,v2=inputs(changed,t,h,branch,sc['mean'],sc['std']);assert np.array_equal(x,x2) and np.array_equal(v,v2);assert np.all(v[np.ix_(h,group(t))]==0)
                        if branch=='H':assert not v[:,np.arange(24)!=t].any()
                        b=baselines_raw(raw0,v,t,sc['median']);b2=baselines_raw(changed,v2,t,sc['median']);assert np.array_equal(b,b2)
                        replaycases.append((w,k,c,mi,t,x,v))
            xx=np.asarray([q[5] for q in replaycases]);vv=np.asarray([q[6] for q in replaycases]);ids=np.array([q[:5] for q in replaycases]);
            for seed in SEEDS:
                net=model(seed);net.load_state_dict(torch.load(ROOT/f'checkpoints/{branch}_{seed}.pt',weights_only=True));pred=predict(net,xx,vv,ids);p=pd.read_parquet(ROOT/f'predictions/{r.slot}_{branch}_{seed}.parquet');joined=truth.copy();joined['p']=p.prediction_raw.to_numpy();maxdiff=0.
                for j,(w,k,c,mi,t,_,_) in enumerate(replaycases):
                    select=joined[(joined.window==w)&(joined.target==k)&(joined.condition==c)&(joined.mask_seed==MS[mi])];assert len(select)>0;got=pred[j,select.step].astype(float)*sc['std'][t]+sc['mean'][t];err=np.abs(got-select.p.to_numpy());maxdiff=max(maxdiff,float(err.max()) if len(err) else 0.);assert np.allclose(got,select.p.to_numpy(),rtol=1e-4,atol=sc['std'][t]*1e-5)
                replays.append(dict(slot=r.slot,branch=branch,seed=seed,cases=len(ids),max_absolute_native_difference=maxdiff));del net
    trraw=np.concatenate(training_rows);trdelta=np.concatenate(training_deltas);sd=np.nanstd(trraw,axis=0);sd[sd==0]=1
    for name,val in [('mean',np.nanmean(trraw,axis=0)),('std',sd),('median',np.nanmedian(trraw,axis=0)),('change_threshold',np.nanquantile(trdelta,.9,axis=0))]:assert np.allclose(sc[name],val,rtol=1e-12,atol=1e-12)
    expected_manifest={(r.slot,b,s) for r in runs.itertuples() if r.split!='train' for b,s in [('median',0),('ffill',0),('linear',0)]+[(b,s) for b in ['M','H'] for s in SEEDS]};assert set(zip(manifest.slot,manifest.method,manifest.seed))==expected_manifest;assert len(manifest)==len(expected_manifest)
    keycols=['slot','method','model_seed','stratification','stratum','target','condition','mask_seed'];assert not mt.duplicated(keycols).any()
    for row in manifest.itertuples():
        d=pd.read_parquet(ROOT/f'predictions/{row.slot}_truth.parquet');p=pd.read_parquet(ROOT/row.path);assert len(d)==len(p);assert np.isfinite(p.to_numpy()).all();assert np.array_equal(p.prediction.to_numpy(),np.maximum(p.prediction_raw.to_numpy(),0));err=p.prediction.to_numpy()-d.truth.to_numpy();units=np.array([1e6,1e6,1.])[d.target];d['abs']=abs(err)/units;d['sq']=(err/units)**2;d['na']=abs(err)/sc['std'][np.array(TARGETS)[d.target]]
        for strat,col in [('all',None),('phase','phase'),('change','change')]:
            kk=['target','condition','mask_seed']+([col] if col else [])
            for key in d.groupby(kk).groups:
                key=tuple(key);expected_metric_keys.add((row.slot,row.method,row.seed,strat,str(key[3]) if col else 'all',int(key[0]),int(key[1]),int(key[2])))
        selected=mt[(mt.slot==row.slot)&(mt.method==row.method)&(mt.model_seed==row.seed)]
        for z in selected.itertuples():
            take=(d.target==z.target)&(d.condition==z.condition)&(d.mask_seed==z.mask_seed)
            if z.stratification=='phase':take &= d.phase==int(z.stratum)
            if z.stratification=='change':take &= d.change==z.stratum
            q=d[take];assert len(q)==z.n
            actual=[q['abs'].sum()/len(q),np.sqrt(q.sq.sum()/len(q)),q.na.sum()/len(q),np.sqrt(np.sum(q.na.to_numpy()**2)/len(q))];expected=[z.mae,z.rmse,z.nmae,z.nrmse];assert np.allclose(actual,expected,rtol=1e-10,atol=1e-10);maxerr=max(maxerr,float(np.max(np.abs(np.array(actual)-expected))))
    assert set(map(tuple,mt[keycols].to_numpy()))==expected_metric_keys
    tr=pd.read_csv(ROOT/'logs/training.csv')
    for seed in SEEDS:
        m=tr[(tr.seed==seed)&(tr.branch=='M')];h=tr[(tr.seed==seed)&(tr.branch=='H')];assert np.array_equal(m.epoch,h.epoch)
        for b,d in [('M',m),('H',h)]:
            fit=json.load(open(ROOT/f'logs/fit_{seed}.json'));assert int(d.loc[d.validation_mae.idxmin(),'epoch'])==fit['best_epochs'][b]
    sealed=json.load(open(ROOT/'metadata/input_hash_verification.json'));sealed_expected={line.split(maxsplit=1)[1].lstrip('*'):line.split(maxsplit=1)[0] for line in (PKG/'SHA256SUMS.txt').read_text().splitlines()};assert len(sealed)==len(sealed_expected) and len(sealed_expected)>0;assert len({z['path'] for z in sealed})==len(sealed_expected);assert {z['path']:z['expected'] for z in sealed}==sealed_expected;assert all(z['ok'] and sha(PKG/z['path'])==z['expected'] for z in sealed)
    config=json.load(open(ROOT/'metadata/config.json'));assert sha(ROOT/'code/experiment.py')==config['implementation_sha256']
    dump('results/RECOMPUTATION_AUDIT.json',dict(status='PASS',truth_points=ntruth,metric_rows=len(mt),max_metric_absolute_difference=maxerr,replayed=replays,checks=['roles','source_window_identity','5s_continuity','no_tail_padding','original_validity','saved_artificial_masks','score_set_complete','hidden_truth_input_and_baseline_invariance','sample_model_replay_all_six','raw_clipped_predictions','independent_all_strata_MAE_RMSE_NMAE_NRMSE_complete_key_set','source_phase_change_timestamp','independent_training_scales','paired_training_epochs','D05_checkpoint_selection','154_source_hashes_unchanged','training_code_unchanged']))
    print('AUDIT PASS',ntruth,len(mt),maxerr,flush=True)
if __name__=='__main__':audit()
