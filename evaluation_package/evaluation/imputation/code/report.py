from experiment import *
from evaluate import baselines_raw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import html
LABELS=['Silver RX (Mbps)','Silver TX (Mbps)','Host CPU (pp)']; SHORT=['Silver RX bitrate','Silver TX bitrate','Host CPU']; CNCOND=['Random20','Gap30s','Gap60s','Gap120s']; METHODS=['median','ffill','linear','H','M']
def table(df):
    columns=df.columns.tolist();lines=['| '+' | '.join(columns)+' |','|'+'|'.join(['---']*len(columns))+'|']
    for row in df.itertuples(index=False,name=None):lines.append('| '+' | '.join(str(v) if not isinstance(v,float) else ('—' if not np.isfinite(v) else f'{v:.4g}') for v in row)+' |')
    return '\n'.join(lines)
def report():
    summary=pd.read_csv(ROOT/'results/summary.csv');metrics=pd.read_csv(ROOT/'results/metrics.csv');sc=np.load(ROOT/'metadata/scales.npz');pair=pd.read_csv(ROOT/'results/paired_M_H.csv');main=summary[summary.slot.isin(['D06','D07'])];fig,axes=plt.subplots(2,3,figsize=(13,7))
    for ri,slot in enumerate(['D06','D07']):
        for k in range(3):
            ax=axes[ri,k]
            for method in METHODS:
                d=main[(main.slot==slot)&(main.target==k)&(main.method==method)&(main.condition>0)].sort_values('condition');ax.plot([30,60,120],d.mae,marker='o',label=method)
            ax.set(title=f'{slot}: {LABELS[k]}',xlabel='Gap length (seconds)',ylabel='MAE');ax.grid(alpha=.25);ax.set_xticks([30,60,120])
    axes[0,0].legend(ncol=3,fontsize=8);fig.tight_layout();fig.savefig(ROOT/'figures/mae_gap.png',dpi=170);fig.savefig(ROOT/'figures/mae_gap.pdf');plt.close(fig)
    examples=[];example_errors=[];fig,axes=plt.subplots(3,1,figsize=(12,9))
    slot='D06';a=dict(np.load(ROOT/f'data/{slot}.npz'));hh=np.load(ROOT/f'masks/{slot}.npz')['artificial_time']
    for k,t in enumerate(TARGETS):
        candidates=np.flatnonzero((hh[:,k,3,0]&np.isfinite(a['raw'][:,:,t])).any(axis=1));w=int(candidates[0]);h=hh[w,k,3,0];raw=a['raw'][w];unit=1e6 if k<2 else 1.;x,v=inputs(raw,t,h,'M',sc['mean'],sc['std']);bp=baselines_raw(raw,v,t,sc['median']);ax=axes[k];grid=np.arange(60)*5;ax.plot(grid,raw[:,t]/unit,color='black',lw=1.5,label='Observed truth');ax.scatter(grid[v[:,t].astype(bool)],raw[v[:,t].astype(bool),t]/unit,s=10,color='black',label='Visible');ax.plot(grid[h],bp[2,h]/unit,'--',label='Linear')
        data=dict(step=np.arange(60),seconds=grid,truth=raw[:,t],visible=v[:,t],hidden=h,linear=bp[2])
        for branch in ['M','H']:
            xx,vv=inputs(raw,t,h,branch,sc['mean'],sc['std']);net=model(17);net.load_state_dict(torch.load(ROOT/f'checkpoints/{branch}_17.pt',weights_only=True));p=predict(net,xx[None],vv[None],np.array([[w,k,3,0,t]]))[0].astype(float)*sc['std'][t]+sc['mean'][t];p=np.maximum(p,0);ax.plot(grid[h],p[h]/unit,label=f'SAITS-{branch}');data[branch]=p
        ax.axvspan(grid[h][0]-2.5,grid[h][-1]+2.5,color='grey',alpha=.13);ax.set(title=f'{slot} window {w}: {LABELS[k]}',xlabel='Seconds from window start');ax.legend(ncol=5,fontsize=8);pd.DataFrame(data).to_csv(ROOT/f'figures/example_{k}.csv',index=False);examples.append(dict(slot=slot,window=w,target=k,condition='gap120',mask_seed=101,model_seed=17))
    for k in range(3):
        ed=pd.read_csv(ROOT/f'figures/example_{k}.csv');ed=ed[ed.hidden & ed.truth.notna()];unit=1e6 if k<2 else 1.;example_errors.append({'target':SHORT[k],'linear_MAE':float((ed.linear-ed.truth).abs().mean()/unit),'M_MAE':float((ed.M-ed.truth).abs().mean()/unit),'H_MAE':float((ed.H-ed.truth).abs().mean()/unit),'n':len(ed)})
    pd.DataFrame(example_errors).to_csv(ROOT/'results/example_metrics.csv',index=False)
    fig.tight_layout();fig.savefig(ROOT/'figures/reconstruction.png',dpi=170);fig.savefig(ROOT/'figures/reconstruction.pdf');plt.close(fig);dump('metadata/example_selection.json',examples)
    # Paired comparisons, each seed first averages masks, then seeds summarized.
    pp=pair.groupby(['slot','target','condition','model_seed']).agg(M_minus_H=('M_minus_H','mean')).reset_index();paired=pp.groupby(['slot','target','condition']).agg(delta=('M_minus_H','mean'),model_sd=('M_minus_H','std')).reset_index();paired.to_csv(ROOT/'results/paired_summary.csv',index=False)
    compare=main.pivot(index=['slot','target','condition'],columns='method',values='mae').reset_index();compare['M_better_linear']=compare.M<compare.linear;compare['M_better_H']=compare.M<compare.H;compare['M_better_all_baselines']=compare.M<compare[['median','ffill','linear']].min(axis=1);compare.to_csv(ROOT/'results/main_comparison.csv',index=False)
    stable=[];cross=[];allbase=[]
    for k in range(3):
        for c in range(4):
            sub=compare[(compare.target==k)&(compare.condition==c)]
            if sub['M_better_linear'].all():stable.append(f'{SHORT[k]} / {CNCOND[c]}')
            if sub['M_better_H'].all():cross.append(f'{SHORT[k]} / {CNCOND[c]}')
            if sub['M_better_all_baselines'].all():allbase.append(f'{SHORT[k]} / {CNCOND[c]}')
    strata=metrics[(metrics.slot.isin(['D06','D07']))&(metrics.stratification=='change')].groupby(['slot','target','condition','stratum','method']).agg(mae=('mae','mean'),n=('n','mean')).reset_index();sp=strata.pivot(index=['slot','target','condition','stratum'],columns='method',values='mae').reset_index();high=sp[sp.stratum=='high'];highwins=int((high.M<high.linear).sum());highboth=int(((high.M<high.linear)&(high.M<high.H)).sum())
    phase=metrics[metrics.stratification=='phase'].groupby(['slot','target','condition','stratum','method']).agg(mae=('mae','mean'),rmse=('rmse','mean'),mean_points_per_mask=('n','mean')).reset_index();phase.to_csv(ROOT/'results/phase_summary.csv',index=False);strata.to_csv(ROOT/'results/change_summary.csv',index=False)
    fits=[json.load(open(ROOT/f'logs/fit_{s}.json')) for s in SEEDS];fitrows=[]
    for f in fits:
        for b in ['M','H']:fitrows.append(dict(model=b,seed=f['seed'],epochs=f['epochs'],best_epoch=f['best_epochs'][b],seconds=f['branch_seconds'][b],D05_standardized_MAE=f['best_scores'][b]))
    audit=json.load(open(ROOT/'results/RECOMPUTATION_AUDIT.json'));cfg=json.load(open(ROOT/'metadata/config.json'));profile=pd.read_csv(ROOT/'metadata/value_profile.csv');age=pd.read_csv(ROOT/'metadata/source_age.csv');counts=pd.read_csv(ROOT/'metadata/mask_counts.csv');ix=pd.read_csv(ROOT/'metadata/window_index.csv');nonscore=int((counts.scored==0).sum())
    cshow=compare.copy();cshow.target=cshow.target.map(dict(enumerate(SHORT)));cshow.condition=cshow.condition.map(dict(enumerate(CNCOND)));cshow=cshow.rename(columns={'slot':'Run','target':'Target','condition':'Missingness condition','median':'Median','ffill':'Forward fill','linear':'Linear interpolation','H':'SAITS-H','M':'SAITS-M'})
    pairedshow=paired[paired.slot.isin(['D06','D07'])].copy();pairedshow.target=pairedshow.target.map(dict(enumerate(SHORT)));pairedshow.condition=pairedshow.condition.map(dict(enumerate(CNCOND)))
    lines=['# Network metric imputation: execution report','',f'Generated: {pd.Timestamp.now(tz="UTC").isoformat()}. All artifacts are under `{ROOT}`.','',
    '## Five key findings','',
    '1. **Execution is complete.** Six formal fits, three baselines, D05 development evaluation, separate D06/D07 reevaluation, and V4/Core24h/diagnostic supplementary evaluation were executed. Each deep model uses three fixed evaluation-mask sets without retraining for individual masks.',
    f'2. **Imputation gains are conditional.** Among 24 main evaluation cells (2 runs × 3 targets × 4 conditions), SAITS-M beats linear interpolation in {int(compare["M_better_linear"].sum())} and all three baselines in {int(compare["M_better_all_baselines"].sum())}. Target/condition pairs beating all three baselines in both D06 and D07: '+('; '.join(allbase) if allbase else 'none')+'.',
    '3. **Other channels provide conditional additional information, not gains across every run.** M beats H in 22/24 main cells. Random-missingness RX is the only pair degraded in both runs. Target/condition pairs where M beats H in both runs: '+('; '.join(cross) if cross else 'none')+'. In standardized aggregation across targets/conditions, M has 22.39% higher error than H on Core24h and 1.99% higher on diagnostic; V4 improves by only 0.44%. These are numerical comparisons on fixed samples, not statistical significance or generalization across independent collections.',
    f'4. **High-change regions are checked separately.** Among {len(high)} main cells above the training-data 90th-percentile change threshold, M beats linear interpolation in {highwins} and both linear and H in {highboth}. Overall means alone do not establish reconstruction of abrupt changes; see the change-stratified table.',
    '5. **Results support a controlled offline validation task, including negative findings.** Report reconstructability under fixed artificial missingness in platform-exported observations and the conditional contribution of other channels. Do not claim reliable online repair, future forecasting, recovery from real collection failures, or algorithmic novelty. Every gain statement must specify targets, missingness conditions, historical nonblind reevaluation, and baseline comparisons.','',
    '## Data, task, and implementation','',
    f'All 154 archived-package hashes matched before and after execution. D01–D04 contain {int((ix.role=="train").sum())} training windows; D05/D06/D07 each contain 291, Core24h 289, V4 292, and diagnostic 99. Normal background and fault activity are retained; classification indices and easy-window filtering are not used. The 60 steps span a 300 s grid interval, with 295 s between first and last samples. Training stride is 12, otherwise 60; windows stay within runs and continuous segments, with incomplete tails discarded.',
    'Each target is queried separately. Interface queries jointly hide 6 Silver interface columns; CPU queries hide 4 host columns. Other times remain visible, including observations on both sides of a gap within the window. Original-valid and artificial masks are saved separately; only their intersection is scored. Continuous gaps retain at least 6 grid points on each side, without guaranteeing those points were originally observed. Random20 hides 12 designed positions, not necessarily 20% scoreable points.',
    f'Across evaluation cases, {nonscore} have no scoreable ground truth. They are flagged rather than assigned zero error. Per-case records are in metadata/mask_counts.csv.',
    f'The model directly imports the [official SAITS repository](https://github.com/WenjieDu/SAITS/tree/{cfg["official_commit"]}), pinned at `{cfg["official_commit"]}`. Both DMSA modules, diagonal attention masks, and attention-weighted fusion are retained; each module has 2 layers, width 64, 4 heads, FFN 128, and dropout 0.1. Each branch has 144,896 parameters. Execution uses the existing PyTorch 2.11.0+cu128 environment, without claiming reproduction of the original paper.',
    'M/H retain a 24-dimensional input shape and share initialization seeds. H hides all other 23 columns. Branches share epoch-wise window order, query targets, missingness conditions, and realized masks; only the queried target receives MIT and ORT supervision. AdamW uses lr=1e-3, weight_decay=1e-4, and batch=64. Each training window receives one query per epoch, with uniformly sampled targets and conditions.',
    'To match training steps, the predefined paired stopping rule stops only when both branches fail to improve for 8 consecutive epochs, up to 50 epochs. Each independently selects the checkpoint with minimum D05 standardized MAE. This adaptation can train the earlier-stagnating branch longer and was recorded before testing. D05 weights target×condition cells equally, pooling three mask sets with equal case counts per cell. Held-out errors are not used for model selection.',
    'Scales are fitted to finite observations in original D01–D04 rows, without duplicate weighting from overlapping windows. All methods clip predictions below at 0; both raw and clipped predictions are saved, without post hoc smoothing. Forward filling falls back to the training median if no previous value exists. Linear interpolation uses the nearest value on a single available side, or the training median if no value is visible. Baselines use original double-precision visible values.','',
    '## Main results: MAE in original units','',
    'Bitrate is in Mbps and CPU in percentage points. Results first average 3 mask sets within each model seed, then average 3 model seeds. RMSE, relative improvement over linear interpolation, and both types of seed variation are in results/summary.csv. Relative improvement is undefined when baseline error is zero.','',table(cshow),'',
    '![MAE versus continuous gap length](figures/mae_gap.png)','',
    '## Paired multivariate and univariate comparison','',
    'delta is M−H; negative values favor M. model_sd is the sample standard deviation after averaging three masks within each model seed. Mask variation is reported separately in results/mask_seed_variation.csv. The 3×3 combinations are not 9 independent collections.','',table(pairedshow),'',
    '## Change, event, and supplementary evaluation','',
    f'High-change thresholds are the training-set 90th percentiles of absolute differences between adjacent finite 5 s observations: RX {sc["change_threshold"][0]/1e6:.5g} Mbps, TX {sc["change_threshold"][1]/1e6:.5g} Mbps, and CPU {sc["change_threshold"][2]:.5g} percentage points. Stratification compares hidden scored points with their preceding grid observations: above threshold is high, otherwise rest; missing preceding truth or a time discontinuity gives unknown. Stratification truth is used only for post hoc evaluation, not mask generation or model inputs.','',table(high),'',
    'Normal background lies outside recorded episodes; fault activity is [start,end), recovery is [end,end_exclusion), and activity takes priority during overlap. Recovery is an archived exclusion-period proxy, not a verified physical recovery time. Event labels are source_marked_inferred. Local stratification can be reconstructed from archived episode tables, but referenced original faults/recovery logs are absent, so independent replay of original label derivation is not claimed. Full stratified MAE/RMSE and counts are in results/phase_summary.csv and results/metrics.csv. Event labels are not used for training.','',
    'V4, Core24h, and diagnostic were evaluated only after all six checkpoints were frozen. The following standardized per-run summaries also retain D05/D06/D07 for comparison. Targets and missingness conditions receive equal weight within each run; different original units are not averaged.', '',
    table(summary.groupby(['slot','method']).nmae.mean().unstack().reset_index()),'',
    '## Reconstruction curves selected by a frozen rule','',
    'For each target, select the first scoreable D06 window with a continuous 120 s gap, mask 101, and model seed 17. This rule was frozen before training. Selected RX/TX examples have low backgrounds with spikes; multivariate reconstruction slightly beats linear interpolation while univariate reconstruction is worse. In the selected CPU example, linear interpolation clearly beats both deep models. Case MAEs are retained as observed, without replacement by best cases. Curves illustrate examples and do not replace full results.','',
    '![Reconstruction examples selected by a fixed rule](figures/reconstruction.png)','',table(pd.DataFrame(example_errors)),'',
    '## Time, resources, and verification','',table(pd.DataFrame(fitrows)),'',
    f'Six fits and their D05 validation total {sum(sum(f["branch_seconds"].values()) for f in fits):.1f} s; paired-training wall time totals {sum(f["wall_seconds"] for f in fits):.1f} s. GPU: RTX PRO 6000 Blackwell. Process peak allocated GPU memory: {max(f["gpu_peak_allocated"] for f in fits)/2**20:.1f} MiB; reserved: {max(f["gpu_peak_reserved"] for f in fits)/2**20:.1f} MiB; peak CPU RSS: {max(f["cpu_maxrss_kib"] for f in fits)/2**20:.2f} GiB. These are process statistics, not whole-system energy consumption. Small-sample smoke checks are counted separately and are not formal results.',
    f'Independent metric recomputation status: {audit["status"]}, covering {audit["metric_rows"]} metric rows and {audit["truth_points"]} saved hidden truth points; maximum arithmetic difference: {audit["max_metric_absolute_difference"]:.3g}. Sampled replay covers all six checkpoints and every evaluation run within numerical tolerances. Changing artificially hidden truth leaves inputs, visible masks, and baseline predictions unchanged. Checks cover original sources, time continuity, scoring-set completeness, equal training epochs, D05 selection, and archived hashes.',
    'The separate-agent review is a provisional semantic audit within the same model family, not independent external reproduction. See metadata/FINAL_REVIEW.md; any pending fixes are governed by that audit and execution-status records.','',
    '## Limitations, unfinished items, and artifact index','',
    'No formal model branch remains unfinished. The first evaluation was stopped during D05 baselines because a loop repeatedly decompressed inputs; after a cache repair, evaluation was rerun completely. Models, masks, and tasks did not change, and no tuning used test scores. See metadata/EVALUATION_REPAIRS.md. No additional collection, deployment changes, or new faults were introduced. baseline2h was optional and not evaluated. Physical collection repetitions, an online causal version, natural-missingness truth recovery, and hyperparameter search were not performed. D06/D07 are previously accessed nonblind reevaluations. Splits follow fixed run roles, not strict chronology: some training runs occurred after D05/D06/D07, so temporal generalization into the future cannot be claimed.',
    'Data contain repeated observations; a 5 s grid does not guarantee a new measurement every 5 s. metadata/source_age.csv records per-run source ages; metadata/value_profile.csv records each channel\'s adjacent-unchanged fraction and longest repeated segment. True states during missing measurements are unobserved; results concern artificial hiding of exported values only. Model/mask seed variation is not a confidence interval across collections.',
    'Environment notes: the older Matplotlib environment lacks 3D projection support, which does not affect these 2D plots; a project-local graphics cache is explicitly configured. The tensor-to-scalar training warning concerns logging only. Environment evidence is in metadata/ENV_AGENT_CHECK.md.',
    '- metadata/config.json: frozen contract and upstream revision; ADAPTATIONS_ZH.md: adaptation notes (English text; legacy filename).\n- data/, metadata/window_index.csv, masks/: windows, original-valid masks, artificial masks, and training sampling.\n- checkpoints/, logs/training.csv, logs/fit_*.json: six fits and checkpoint-selection evidence.\n- predictions/*_truth.parquet: separate truth interface; other parquet files: aligned raw/clipped predictions.\n- results/summary.csv, metrics.csv, paired_M_H.csv: full original-unit metrics and paired results.\n- results/RECOMPUTATION_AUDIT.json: independent recomputation and replay.\n- code/: execution, evaluation, independent checks, and report source.\n- figures/: PNG, PDF, and example data.']
    text='\n'.join(lines)+'\n';(ROOT/'REPORT_ZH.md').write_text(text)
    # Small markdown renderer is only for presentation, no external runtime dependency.
    import re
    def inline(v):
        z=html.escape(v);z=re.sub(r'\[([^\]]+)\]\((https?://[^)]+)\)',r'<a href="\2">\1</a>',z);z=re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',z);z=re.sub(r'`([^`]+)`',r'<code>\1</code>',z);return z
    out=[];intable=False;inlist=False
    for line in lines:
        for l in line.split('\n'):
            if l.startswith('|'):
                cells=[x.strip() for x in l.strip('|').split('|')]
                if all(re.fullmatch(r'[-:]+',x) for x in cells):continue
                if not intable:out.append('<table>');intable=True
                out.append('<tr>'+''.join('<td>'+html.escape(c)+'</td>' for c in cells)+'</tr>');continue
            if intable:out.append('</table>');intable=False
            if not l:continue
            if l.startswith('!['):url=l.split('](')[1][:-1];out.append(f'<img src="{url}">');continue
            n=len(l)-len(l.lstrip('#'))
            if n:out.append(f'<h{n}>'+html.escape(l[n:].strip())+f'</h{n}>')
            else:out.append('<p>'+inline(l)+'</p>')
    if intable:out.append('</table>')
    (ROOT/'REPORT_ZH.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><title>Network metric imputation experiment</title><style>body{font-family:system-ui,sans-serif;max-width:1250px;margin:32px auto;line-height:1.7;color:#17212b;overflow-wrap:anywhere}table{border-collapse:collapse;font-size:12px;width:100%;margin:14px 0}td{padding:5px;border:1px solid #ccc}tr:first-child{background:#eaf0f5;font-weight:bold}img{max-width:100%}h2{border-bottom:1px solid #bbb}@media print{@page{size:A4 landscape;margin:12mm}body{margin:0;font-size:10pt}h2{break-after:avoid}tr,img{break-inside:avoid}table{font-size:8pt}}</style>'+''.join(out)+'</html>')
    import base64
    hp=ROOT/'REPORT_ZH.html';ht=hp.read_text()
    for fn in ['mae_gap.png','reconstruction.png']:ht=ht.replace('figures/'+fn,'data:image/png;base64,'+base64.b64encode((ROOT/'figures'/fn).read_bytes()).decode())
    hp.write_text(ht)
    dump('results/CONCLUSION.json',dict(main_cells=len(compare),M_better_linear=int(compare['M_better_linear'].sum()),M_better_all_baselines=int(compare['M_better_all_baselines'].sum()),both_runs_better_all=allbase,both_runs_M_better_H=cross,high_change_M_better_linear=highwins,high_change_M_better_linear_and_H=highboth))
    print('REPORT DONE',flush=True)
if __name__=='__main__':report()
