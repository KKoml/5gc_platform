import os,sys,json,hashlib,time,platform,subprocess,resource
from pathlib import Path
import numpy as np
import pandas as pd
import torch
ROOT=Path(__file__).resolve().parents[1]; PKG=Path(os.environ['DGATE_DATASET_ROOT']).resolve()
sys.path.insert(0,str(ROOT/'third_party/SAITS'))
from modeling.saits import SAITS
F=json.load(open(PKG/'metadata/feature_sets.json'))['FD_detection_24']; TARGETS=[16,17,12]; CONDS=['random20','gap30','gap60','gap120']; SEEDS=[17,29,43]; MS=[101,202,303]
torch.set_num_threads(4)
def dump(p,o):
    (ROOT/p).write_text(json.dumps(o,indent=2,ensure_ascii=False,allow_nan=False))
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def model(seed=17):
    torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    return SAITS(2,1,60,24,64,128,4,16,16,.1,input_with_mask=True,param_sharing_strategy='inner_group',MIT=True,device='cuda',diagonal_attention_mask=True).cuda()
def group(t): return list(range(16,22)) if t in [16,17] else list(range(12,16))
def hide(rng,c):
    h=np.zeros(60,bool)
    if c==0: h[rng.choice(60,12,replace=False)]=True
    else:
        n=[0,6,12,24][c]; s=rng.integers(6,60-n-6+1); h[s:s+n]=True
    return h
def inputs(raw,t,h,branch,mean,std):
    # Truth is never passed to the network: this function returns only sanitized X and V.
    v=np.isfinite(raw); v[:,group(t)] &= ~h[:,None]
    if branch=='H': v[:,np.arange(24)!=t]=False
    safe=np.where(v,raw,mean)
    return ((safe-mean)/std).astype('float32'),v.astype('float32')
def baseline(x,v,t,median,mean,std):
    vals=x[:,t].astype('float64')*std[t]+mean[t]; ok=v[:,t].astype(bool); idx=np.flatnonzero(ok)
    out=np.full((3,60),median[t],float)
    for j in range(60):
        if ok[j]: out[1,j]=vals[j]
        elif j: out[1,j]=out[1,j-1]
    if len(idx):out[2]=np.interp(np.arange(60),idx,vals[idx])
    return out

def prepare():
    checks=[]
    for line in (PKG/'SHA256SUMS.txt').read_text().splitlines():
        h,p=line.split(maxsplit=1);p=p.lstrip('*');actual=sha(PKG/p); checks.append(dict(path=p,expected=h,actual=actual,ok=h==actual))
    dump('metadata/input_hash_verification.json',checks);assert all(x['ok'] for x in checks)
    runs=pd.read_csv(PKG/'metadata/runs.csv');runs=runs[runs.slot!='baseline2h'];runs.to_csv(ROOT/'metadata/runs.csv',index=False)
    arrays={}; indexes=[]; segments=[]; ages=[]; profile=[]; train=[]; deltas=[[],[],[]]
    for r in runs.itertuples():
        d=PKG/r.data_path; df=pd.read_parquet(d/'core_features_5s.parquet');assert df.run_id.eq(r.run_id).all()
        ts=pd.to_datetime(df.cutoff_time,utc=True).astype('int64').to_numpy()//10**9;assert np.all(np.diff(ts)>0)
        raw=df[F].to_numpy(float); assert not np.isinf(raw).any(); split=np.r_[0,np.flatnonzero(np.diff(ts)!=5)+1,len(ts)]
        phase=np.zeros(len(ts),np.int8); ep=pd.read_csv(d/'episodes.csv')
        for e in ep.itertuples():
            st=pd.Timestamp(e.start_time).timestamp();en=pd.Timestamp(e.end_time).timestamp();ex=pd.Timestamp(e.end_exclusion_time).timestamp()
            assert st<=en<=ex
            phase[(ts>=en)&(ts<ex)]=2
        for e in ep.itertuples():phase[(ts>=pd.Timestamp(e.start_time).timestamp())&(ts<pd.Timestamp(e.end_time).timestamp())]=1
        # Conservative annotation: normal means outside documented activity/recovery intervals.
        diff=np.full((len(ts),3),np.nan)
        for k,t in enumerate(TARGETS):
            diff[1:,k]=np.where(np.diff(ts)==5,np.abs(np.diff(raw[:,t])),np.nan)
            if r.split=='train':deltas[k].extend(diff[np.isfinite(diff[:,k]),k].tolist())
        stride=12 if r.split=='train' else 60; xx=[]; tt=[]; pp=[]; dd=[]
        for a,b in zip(split[:-1],split[1:]):
            starts=list(range(a,b-59,stride)); covered_end=starts[-1]+60 if starts else a
            segments.append(dict(slot=r.slot,start_row=int(a),stop_row=int(b),length=int(b-a),windows=len(starts),tail_uncovered=int(b-covered_end),reason='tail_not_padded'))
            for s in starts:
                wi=len(xx);xx.append(raw[s:s+60]);tt.append(ts[s:s+60]);pp.append(phase[s:s+60]);dd.append(diff[s:s+60]);indexes.append(dict(slot=r.slot,run_id=r.run_id,role=r.split,window=wi,row_start=s,row_stop=s+60,start=int(ts[s]),last=int(ts[s+59]),stride=stride))
        np.savez_compressed(ROOT/f'data/{r.slot}.npz',raw=np.asarray(xx),original_valid=np.isfinite(xx),time=np.asarray(tt),phase=np.asarray(pp),delta=np.asarray(dd))
        if r.split=='train':train.append(raw)
        age=pd.read_parquet(d/'source_age_5s.parquet')
        for col in age.columns[1:]:
            z=age[col].dropna().to_numpy();ages.append(dict(slot=r.slot,source=col,median=float(np.median(z)),p95=float(np.quantile(z,.95)),maximum=float(z.max()),over5_fraction=float((z>5).mean())))
        for j,f in enumerate(F):
            z=raw[:,j]; pair=np.isfinite(z[1:])&np.isfinite(z[:-1])&(np.diff(ts)==5);same=(z[1:]==z[:-1])&pair
            longest=cur=0
            for eq in same:cur=cur+1 if eq else 0;longest=max(longest,cur)
            profile.append(dict(slot=r.slot,feature=f,coverage=float(np.isfinite(z).mean()),unchanged_fraction=float(same.sum()/max(pair.sum(),1)),longest_equal_steps=longest+1))
        print('prepared',r.slot,len(xx),flush=True)
    tr=np.concatenate(train);mean=np.nanmean(tr,axis=0);std=np.nanstd(tr,axis=0);std[std==0]=1;median=np.nanmedian(tr,axis=0)
    threshold=np.array([np.quantile(x,.9) for x in deltas]);np.savez(ROOT/'metadata/scales.npz',mean=mean,std=std,median=median,change_threshold=threshold)
    dup=[]
    for t in TARGETS:
        for j in range(24):
            if j==t:continue
            ok=np.isfinite(tr[:,t])&np.isfinite(tr[:,j]);x=tr[ok,j];y=tr[ok,t];coef=np.polyfit(x,y,1) if np.std(x)>0 else [0,float(y.mean())];err=np.max(np.abs(y-np.polyval(coef,x)));dup.append(dict(target=F[t],candidate=F[j],same_group=j in group(t),exact_equal=bool(np.array_equal(x,y)),linear_max_error=float(err),target_std=float(np.std(y))))
    pd.DataFrame(dup).to_csv(ROOT/'metadata/alias_audit.csv',index=False)
    pd.DataFrame(indexes).to_csv(ROOT/'metadata/window_index.csv',index=False);pd.DataFrame(segments).to_csv(ROOT/'metadata/segments.csv',index=False);pd.DataFrame(ages).to_csv(ROOT/'metadata/source_age.csv',index=False);pd.DataFrame(profile).to_csv(ROOT/'metadata/value_profile.csv',index=False)
    for r in runs.itertuples():
        if r.split=='train':continue
        a=np.load(ROOT/f'data/{r.slot}.npz');n=len(a['raw']);hh=np.zeros((n,3,4,3,60),bool)
        for w in range(n):
            for k,t in enumerate(TARGETS):
                for c in range(4):
                    for mi,ms in enumerate(MS):
                        digest=hashlib.sha256(f'{r.run_id}|{w}|{t}|{c}|{ms}'.encode()).digest();hh[w,k,c,mi]=hide(np.random.default_rng(int.from_bytes(digest[:8],'little')),c)
        np.savez_compressed(ROOT/f'masks/{r.slot}.npz',artificial_time=hh,target_columns=TARGETS,group_columns_interface=np.arange(16,22),group_columns_host=np.arange(12,16))
    dump('metadata/prepare_status.json',dict(status='PASS',sealed_entries=len(checks),train_rows=len(tr),threshold=threshold.tolist()))

def cases(slot,branch):
    a=np.load(ROOT/f'data/{slot}.npz');hh=np.load(ROOT/f'masks/{slot}.npz')['artificial_time'];sc=np.load(ROOT/'metadata/scales.npz');raw=a['raw'];xx=[];vv=[];yy=[];ee=[];ids=[]
    for w in range(len(raw)):
        for k,t in enumerate(TARGETS):
            for c in range(4):
                for mi in range(3):
                    h=hh[w,k,c,mi];x,v=inputs(raw[w],t,h,branch,sc['mean'],sc['std']);xx.append(x);vv.append(v);yy.append(np.nan_to_num((raw[w,:,t]-sc['mean'][t])/sc['std'][t]));ee.append(h&np.isfinite(raw[w,:,t]));ids.append([w,k,c,mi,t])
    return np.asarray(xx),np.asarray(vv),np.asarray(yy),np.asarray(ee),np.asarray(ids)
def predict(net,x,v,ids,batch=256):
    out=[];net.eval()
    with torch.no_grad():
        for s in range(0,len(x),batch):
            xx=torch.tensor(x[s:s+batch],device='cuda');vv=torch.tensor(v[s:s+batch],device='cuda');p,_=net.impute(dict(X=xx,missing_mask=vv));t=torch.tensor(ids[s:s+batch,4],device='cuda');out.append(p[torch.arange(len(xx),device='cuda'),:,t].cpu().numpy())
    return np.concatenate(out)
def val_score(pred,y,e,ids,sc):
    vals=[]
    for k,t in enumerate(TARGETS):
        for c in range(4):
            ix=(ids[:,1]==k)&(ids[:,2]==c);err=np.abs(np.maximum(pred[ix],-sc['mean'][t]/sc['std'][t])-y[ix]); vals.append(float(err[e[ix]].mean()))
    return np.mean(vals)
def witness():
    sc=np.load(ROOT/'metadata/scales.npz');a=np.load(ROOT/'data/D01.npz')['raw'];rng=np.random.default_rng(71);h=hide(rng,3);x,v=inputs(a[0],16,h,'M',sc['mean'],sc['std']);b=a[0].copy();b[np.ix_(h,group(16))]=123456789
    x2,v2=inputs(b,16,h,'M',sc['mean'],sc['std']);assert np.array_equal(x,x2) and np.array_equal(v,v2);assert np.array_equal(baseline(x,v,16,sc['median'],sc['mean'],sc['std']),baseline(x2,v2,16,sc['median'],sc['mean'],sc['std']))
    net=model();opt=torch.optim.AdamW(net.parameters(),lr=.001);xx=torch.tensor(np.repeat(x[None],8,0),device='cuda');vv=torch.tensor(np.repeat(v[None],8,0),device='cuda');y=torch.tensor(np.nan_to_num((a[0,:,16]-sc['mean'][16])/sc['std'][16]),device='cuda',dtype=torch.float32);e=torch.tensor(h&np.isfinite(a[0,:,16]),device='cuda');losses=[];start=time.time()
    for i in range(80):
        net.train();opt.zero_grad();_,parts=net.impute(dict(X=xx,missing_mask=vv));loss=(parts[-1][:,:,16]-y).abs()[:,e].mean();loss.backward();opt.step();losses.append(float(loss))
    assert np.isfinite(losses).all() and np.mean(losses[-10:])<np.mean(losses[:10]);torch.cuda.synchronize()
    dump('metadata/witness.json',dict(status='PASS',initial10=float(np.mean(losses[:10])),final10=float(np.mean(losses[-10:])),seconds=time.time()-start,gpu=torch.cuda.get_device_name(),torch=torch.__version__,peak_allocated=torch.cuda.max_memory_allocated(),parameters=sum(p.numel() for p in net.parameters()),hidden_value_invariance=True))
    print('WITNESS PASS',flush=True)
def train():
    sc=np.load(ROOT/'metadata/scales.npz');arr=np.concatenate([np.load(ROOT/f'data/D0{i}.npz')['raw'] for i in range(1,5)]);vals={b:cases('D05',b) for b in ['M','H']};records=[]
    for seed in SEEDS:
        nets={b:model(seed) for b in ['M','H']};opts={b:torch.optim.AdamW(nets[b].parameters(),lr=.001,weight_decay=.0001) for b in nets};best={b:float('inf') for b in nets};stale={b:0 for b in nets};elapsed={b:0. for b in nets};bestep={};start=time.time()
        for epoch in range(1,51):
            # Generate once and share exact windows, queries and masks across M/H.
            rng=np.random.default_rng(seed*100000+epoch);order=rng.permutation(len(arr));ts=rng.choice(TARGETS,len(arr));cs=rng.integers(0,4,len(arr));hs=np.asarray([hide(rng,c) for c in cs]);np.savez_compressed(ROOT/f'masks/train_{seed}_{epoch:02d}.npz',window=order,target=ts,condition=cs,artificial_time=hs)
            for branch in ['M','H']:
                tick=time.time();torch.manual_seed(seed*1000+epoch);net=nets[branch];net.train();losses=[]
                for s in range(0,len(arr),64):
                    rr=arr[order[s:s+64]];tt=ts[s:s+64];hh=hs[s:s+64];xx=[];vv=[];yy=[];ee=[];oo=[]
                    for raw,t,h in zip(rr,tt,hh):
                        x,v=inputs(raw,int(t),h,branch,sc['mean'],sc['std']);xx.append(x);vv.append(v);yy.append(np.nan_to_num((raw[:,t]-sc['mean'][t])/sc['std'][t]));ee.append(h&np.isfinite(raw[:,t]));oo.append((~h)&np.isfinite(raw[:,t]))
                    x=torch.tensor(np.asarray(xx),device='cuda');v=torch.tensor(np.asarray(vv),device='cuda');y=torch.tensor(np.asarray(yy),dtype=torch.float32,device='cuda');e=torch.tensor(np.asarray(ee),device='cuda');o=torch.tensor(np.asarray(oo),device='cuda');ttt=torch.tensor(tt,device='cuda');bi=torch.arange(len(rr),device='cuda');opts[branch].zero_grad();_,parts=net.impute(dict(X=x,missing_mask=v));p=[z[bi,:,ttt] for z in parts];loss=((p[-1]-y).abs()*e).sum()/e.sum().clamp_min(1)+sum(((z-y).abs()*o).sum()/o.sum().clamp_min(1) for z in p)/3;loss.backward();opts[branch].step();losses.append(float(loss))
                x,v,y,e,ids=vals[branch];p=predict(net,x,v,ids);score=val_score(p,y,e,ids,sc);torch.cuda.synchronize();elapsed[branch]+=time.time()-tick
                if score<best[branch]:best[branch]=score;stale[branch]=0;bestep[branch]=epoch;torch.save(net.state_dict(),ROOT/f'checkpoints/{branch}_{seed}.pt')
                else:stale[branch]+=1
                rec=dict(seed=seed,branch=branch,epoch=epoch,train_loss=float(np.mean(losses)),validation_mae=float(score),best_epoch=bestep[branch],stale=stale[branch],seconds=elapsed[branch]);records.append(rec);pd.DataFrame(records).to_csv(ROOT/'logs/training.csv',index=False);print(json.dumps(rec),flush=True)
            if all(v>=8 for v in stale.values()):break
        dump(f'logs/fit_{seed}.json',dict(seed=seed,status='DONE',epochs=epoch,best_epochs=bestep,best_scores=best,branch_seconds=elapsed,wall_seconds=time.time()-start,gpu_peak_allocated=torch.cuda.max_memory_allocated(),gpu_peak_reserved=torch.cuda.max_memory_reserved(),cpu_maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss))
    dump('metadata/training_complete.json',dict(status='DONE',checkpoints={p.name:sha(p) for p in (ROOT/'checkpoints').glob('*.pt')}))

if __name__=='__main__': globals()[sys.argv[1]]()
