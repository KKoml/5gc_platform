"""Check every derived table and report conclusion against verified per-mask metrics."""
from experiment import *
def audit_derived():
    d=pd.read_csv(ROOT/'results/metrics.csv');d=d[d.stratification=='all'];s=pd.read_csv(ROOT/'results/summary.csv');keys=['slot','target','condition','method'];expected=set(map(tuple,d[keys].drop_duplicates().to_numpy()));assert set(map(tuple,s[keys].to_numpy()))==expected and not s.duplicated(keys).any()
    for r in s.itertuples():
        q=d[(d.slot==r.slot)&(d.target==r.target)&(d.condition==r.condition)&(d.method==r.method)];means=[q[q.model_seed==seed].mae.to_numpy().mean() for seed in sorted(q.model_seed.unique())];masks=[q[q.mask_seed==seed].mae.to_numpy().mean() for seed in MS];ref=d[(d.slot==r.slot)&(d.target==r.target)&(d.condition==r.condition)&(d.method=='linear')].mae.mean();expected_values=[np.mean(means),np.std(means,ddof=1) if len(means)>1 else 0,np.std(masks,ddof=1),q.rmse.mean(),q.nmae.mean(),ref];actual=[r.mae,r.model_seed_sd,r.mask_seed_sd,r.rmse,r.nmae,r.linear_mae];assert np.allclose(actual,expected_values,rtol=1e-10,atol=1e-10)
        if ref==0:assert np.isnan(r.improvement_vs_linear_pct)
        else:assert np.isclose(r.improvement_vs_linear_pct,100*(ref-np.mean(means))/ref,rtol=1e-10,atol=1e-10)
    pair=pd.read_csv(ROOT/'results/paired_M_H.csv');pk=['slot','target','condition','mask_seed','model_seed'];m=d[d.method=='M'].set_index(pk);h=d[d.method=='H'].set_index(pk);p=pair.set_index(pk);assert set(p.index)==set(m.index)==set(h.index);assert p.index.is_unique
    for key,row in p.iterrows():assert np.allclose([row.mae_M,row.mae_H,row.M_minus_H],[m.loc[key].mae,h.loc[key].mae,m.loc[key].mae-h.loc[key].mae],rtol=1e-10,atol=1e-10)
    ps=pd.read_csv(ROOT/'results/paired_summary.csv');pskeys=['slot','target','condition'];assert not ps.duplicated(pskeys).any();assert set(map(tuple,ps[pskeys].to_numpy()))==set(map(tuple,s[s.method=='M'][pskeys].to_numpy()))
    for r in ps.itertuples():
        q=p.loc[r.slot,r.target,r.condition];vals=[q.xs(seed,level='model_seed').M_minus_H.mean() for seed in SEEDS];assert np.allclose([r.delta,r.model_sd],[np.mean(vals),np.std(vals,ddof=1)],rtol=1e-10,atol=1e-10)
    main=pd.read_csv(ROOT/'results/main_comparison.csv');assert len(main)==24 and not main.duplicated(['slot','target','condition']).any();assert set(map(tuple,main[['slot','target','condition']].to_numpy()))=={(slot,t,c) for slot in ['D06','D07'] for t in range(3) for c in range(4)};wins=[];cross=[]
    for r in main.itertuples():
        q=s[(s.slot==r.slot)&(s.target==r.target)&(s.condition==r.condition)].set_index('method');assert np.allclose([r.M,r.H,r.linear,r.ffill,r.median],[q.loc[x].mae for x in ['M','H','linear','ffill','median']]);wins.append(r.M<min(r.linear,r.ffill,r.median));cross.append(r.M<r.H)
    # Verify the booleans as well as displayed numbers.
    assert np.array_equal(main['M优于线性'],main.M<main.linear);assert np.array_equal(main['M优于H'],main.M<main.H);assert np.array_equal(main['M优于三基线'],wins)
    c=json.load(open(ROOT/'results/CONCLUSION.json'));assert c['main_cells']==24;assert c['M_better_linear']==int((main.M<main.linear).sum());assert c['M_better_all_baselines']==sum(wins)
    names=['Silver接收比特率','Silver发送比特率','宿主机CPU'];conds=['随机20%','连续30秒','连续60秒','连续120秒'];both=[];extra=[]
    for t in range(3):
        for cond in range(4):
            q=main[(main.target==t)&(main.condition==cond)];assert len(q)==2
            if q['M优于三基线'].all():both.append(f'{names[t]}／{conds[cond]}')
            if q['M优于H'].all():extra.append(f'{names[t]}／{conds[cond]}')
    assert c['both_runs_better_all']==both and c['both_runs_M_better_H']==extra
    allmetrics=pd.read_csv(ROOT/'results/metrics.csv');change=allmetrics[(allmetrics.slot.isin(['D06','D07']))&(allmetrics.stratification=='change')&(allmetrics.stratum=='high')];hh=change.groupby(['slot','target','condition','method']).mae.mean().unstack();assert c['high_change_M_better_linear']==int((hh.M<hh.linear).sum());assert c['high_change_M_better_linear_and_H']==int(((hh.M<hh.linear)&(hh.M<hh.H)).sum())
    for fname,strat in [('phase_summary.csv','phase'),('change_summary.csv','change')]:
        table=pd.read_csv(ROOT/'results'/fname);source=allmetrics[allmetrics.stratification==strat]
        if strat=='change':source=source[source.slot.isin(['D06','D07'])]
        kk=['slot','target','condition','stratum','method'];assert not table.duplicated(kk).any();assert set(map(tuple,table[kk].astype(str).to_numpy()))==set(map(tuple,source[kk].drop_duplicates().astype(str).to_numpy()))
        for r in table.itertuples():
            q=source[(source.slot==r.slot)&(source.target==r.target)&(source.condition==r.condition)&(source.stratum.astype(str)==str(r.stratum))&(source.method==r.method)];assert np.isclose(q.mae.mean(),r.mae)
            if strat=='phase':assert np.allclose([q.rmse.mean(),q.n.mean()],[r.rmse,r.mean_points_per_mask])
            else:assert np.isclose(q.n.mean(),r.n)
    # Explicit equal-run/target/condition macro table, standardized units only.
    macro=s[s.slot.isin(['D06','D07'])].groupby('method')[['nmae']].mean().reset_index();macro.to_csv(ROOT/'results/D06_D07_macro.csv',index=False)
    dump('results/DERIVED_TABLE_AUDIT.json',dict(status='PASS',checks=['complete_summary','separate_seed_variation','relative_improvement_zero_guard','complete_pair_keys_and_values','paired_summary','main_comparison','conclusion_counts_and_conditions','phase_change_tables'],macro='D06_D07_macro.csv'))
    print('DERIVED TABLE AUDIT PASS')
if __name__=='__main__':audit_derived()
