from experiment import *

def baselines_raw(raw,v,t,median):
    ok=v[:,t].astype(bool);vals=np.where(ok,raw[:,t],median[t]);idx=np.flatnonzero(ok);out=np.full((3,60),median[t],float)
    for j in range(60):out[1,j]=vals[j] if ok[j] else (out[1,j-1] if j else median[t])
    if len(idx):out[2]=np.interp(np.arange(60),idx,vals[idx])
    return out

def evaluate():
    assert (ROOT/'metadata/training_complete.json').exists()
    sc=np.load(ROOT/'metadata/scales.npz');runs=pd.read_csv(ROOT/'metadata/runs.csv');manifest=[];maskcounts=[]
    for r in runs.itertuples():
        if r.split=='train':continue
        slot=r.slot;a=dict(np.load(ROOT/f'data/{slot}.npz'));h=np.load(ROOT/f'masks/{slot}.npz')['artificial_time'];x,v,y,e,ids=cases(slot,'M');ci,ti=np.where(e);q=ids[ci];target=q[:,4];truth=a['raw'][q[:,0],ti,target]
        base=dict(case=ci.astype('int32'),window=q[:,0].astype('int32'),target=q[:,1].astype('int8'),condition=q[:,2].astype('int8'),mask_seed=np.array(MS)[q[:,3]],step=ti.astype('int8'),timestamp=a['time'][q[:,0],ti],truth=truth,phase=a['phase'][q[:,0],ti],change=np.where(np.isfinite(a['delta'][q[:,0],ti,q[:,1]]),np.where(a['delta'][q[:,0],ti,q[:,1]]>sc['change_threshold'][q[:,1]],'high','rest'),'unknown'))
        # Separate truth table from prediction artifacts and inference interface.
        truthdf=pd.DataFrame(base);truthdf.to_parquet(ROOT/f'predictions/{slot}_truth.parquet',index=False)
        bpred=np.empty((3,len(ids),60))
        for j,(w,k,c,mi,t) in enumerate(ids):
            bpred[:,j]=baselines_raw(a['raw'][w],v[j],t,sc['median']);maskcounts.append(dict(slot=slot,case=j,window=int(w),target=int(k),condition=int(c),mask_seed=MS[mi],designed_hidden=int(h[w,k,c,mi].sum()),scored=int(e[j].sum()),original_finite=int(np.isfinite(a['raw'][w,:,t]).sum())))
        for bi,name in enumerate(['median','ffill','linear']):
            rawp=bpred[bi,ci,ti];p=pd.DataFrame(dict(prediction_raw=rawp,prediction=np.maximum(rawp,0)));path=f'predictions/{slot}_{name}.parquet';p.to_parquet(ROOT/path,index=False);manifest.append(dict(slot=slot,method=name,seed=0,path=path,rows=len(p)))
        del bpred
        for branch in ['M','H']:
            if branch=='H':x,v,y,e,ids=cases(slot,'H')
            for seed in SEEDS:
                net=model(seed);net.load_state_dict(torch.load(ROOT/f'checkpoints/{branch}_{seed}.pt',weights_only=True));pp=predict(net,x,v,ids);rawp=pp[ci,ti].astype(float)*sc['std'][target]+sc['mean'][target];p=pd.DataFrame(dict(prediction_raw=rawp,prediction=np.maximum(rawp,0)));path=f'predictions/{slot}_{branch}_{seed}.parquet';p.to_parquet(ROOT/path,index=False);manifest.append(dict(slot=slot,method=branch,seed=seed,path=path,rows=len(p)));del net
        print('evaluated',slot,len(truthdf),flush=True)
    pd.DataFrame(maskcounts).to_csv(ROOT/'metadata/mask_counts.csv',index=False);pd.DataFrame(manifest).to_csv(ROOT/'predictions/manifest.csv',index=False)
    dump('metadata/evaluation_complete.json',dict(status='DONE',utc=pd.Timestamp.now(tz='UTC').isoformat()))

def metrics():
    sc=np.load(ROOT/'metadata/scales.npz');manifest=pd.read_csv(ROOT/'predictions/manifest.csv');out=[]
    for m in manifest.itertuples():
        d=pd.read_parquet(ROOT/f'predictions/{m.slot}_truth.parquet');p=pd.read_parquet(ROOT/m.path);assert len(d)==len(p);err=p.prediction.to_numpy()-d.truth.to_numpy();factors=np.array([1e6,1e6,1.])[d.target];d['ae']=np.abs(err)/factors;d['se']=(err/factors)**2;d['nae']=np.abs(err)/sc['std'][np.array(TARGETS)[d.target]];d['nse']=(err/sc['std'][np.array(TARGETS)[d.target]])**2
        for strat,col in [('all',None),('phase','phase'),('change','change')]:
            keys=['target','condition','mask_seed']+([col] if col else []);g=d.groupby(keys,observed=True).agg(n=('ae','size'),mae=('ae','mean'),mse=('se','mean'),nmae=('nae','mean'),nmse=('nse','mean')).reset_index()
            for z in g.to_dict('records'):
                z.update(slot=m.slot,method=m.method,model_seed=m.seed,stratification=strat,stratum=str(z.pop(col)) if col else 'all');z['rmse']=float(np.sqrt(z.pop('mse')));z['nrmse']=float(np.sqrt(z.pop('nmse')));out.append(z)
    pd.DataFrame(out).to_csv(ROOT/'results/metrics.csv',index=False)
    d=pd.DataFrame(out);a=d[d.stratification=='all'];keys=['slot','target','condition','method'];byseed=a.groupby(keys+['model_seed']).agg(mae=('mae','mean'),rmse=('rmse','mean'),nmae=('nmae','mean')).reset_index();summary=byseed.groupby(keys).agg(mae=('mae','mean'),model_seed_sd=('mae','std'),rmse=('rmse','mean'),nmae=('nmae','mean')).reset_index();by_mask=a.groupby(keys+['mask_seed']).mae.mean().reset_index();ms=by_mask.groupby(keys).mae.std().rename('mask_seed_sd').reset_index();summary=summary.merge(ms,on=keys);summary['model_seed_sd']=summary.model_seed_sd.fillna(0);linear=summary[summary.method=='linear'][['slot','target','condition','mae']].rename(columns={'mae':'linear_mae'});summary=summary.merge(linear,on=['slot','target','condition']);summary['improvement_vs_linear_pct']=np.where(summary.linear_mae!=0,100*(summary.linear_mae-summary.mae)/summary.linear_mae,np.nan);summary.to_csv(ROOT/'results/summary.csv',index=False)
    pair=a[a.method=='M'].merge(a[a.method=='H'],on=['slot','target','condition','mask_seed','model_seed','stratification','stratum'],suffixes=('_M','_H'));pair['M_minus_H']=pair.mae_M-pair.mae_H;pair.to_csv(ROOT/'results/paired_M_H.csv',index=False)
    byseed.to_csv(ROOT/'results/model_seed_variation.csv',index=False);by_mask.to_csv(ROOT/'results/mask_seed_variation.csv',index=False)

if __name__=='__main__':globals()[sys.argv[1]]()
