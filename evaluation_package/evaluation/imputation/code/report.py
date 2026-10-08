from experiment import *
from evaluate import baselines_raw
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import html
LABELS=['Silver RX (Mbps)','Silver TX (Mbps)','Host CPU (pp)']; SHORT=['Silver接收比特率','Silver发送比特率','宿主机CPU']; CNCOND=['随机20%','连续30秒','连续60秒','连续120秒']; METHODS=['median','ffill','linear','H','M']
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
    compare=main.pivot(index=['slot','target','condition'],columns='method',values='mae').reset_index();compare['M优于线性']=compare.M<compare.linear;compare['M优于H']=compare.M<compare.H;compare['M优于三基线']=compare.M<compare[['median','ffill','linear']].min(axis=1);compare.to_csv(ROOT/'results/main_comparison.csv',index=False)
    stable=[];cross=[];allbase=[]
    for k in range(3):
        for c in range(4):
            sub=compare[(compare.target==k)&(compare.condition==c)]
            if sub['M优于线性'].all():stable.append(f'{SHORT[k]}／{CNCOND[c]}')
            if sub['M优于H'].all():cross.append(f'{SHORT[k]}／{CNCOND[c]}')
            if sub['M优于三基线'].all():allbase.append(f'{SHORT[k]}／{CNCOND[c]}')
    strata=metrics[(metrics.slot.isin(['D06','D07']))&(metrics.stratification=='change')].groupby(['slot','target','condition','stratum','method']).agg(mae=('mae','mean'),n=('n','mean')).reset_index();sp=strata.pivot(index=['slot','target','condition','stratum'],columns='method',values='mae').reset_index();high=sp[sp.stratum=='high'];highwins=int((high.M<high.linear).sum());highboth=int(((high.M<high.linear)&(high.M<high.H)).sum())
    phase=metrics[metrics.stratification=='phase'].groupby(['slot','target','condition','stratum','method']).agg(mae=('mae','mean'),rmse=('rmse','mean'),mean_points_per_mask=('n','mean')).reset_index();phase.to_csv(ROOT/'results/phase_summary.csv',index=False);strata.to_csv(ROOT/'results/change_summary.csv',index=False)
    fits=[json.load(open(ROOT/f'logs/fit_{s}.json')) for s in SEEDS];fitrows=[]
    for f in fits:
        for b in ['M','H']:fitrows.append(dict(模型=b,种子=f['seed'],训练轮数=f['epochs'],最佳轮数=f['best_epochs'][b],耗时秒=f['branch_seconds'][b],D05标准化MAE=f['best_scores'][b]))
    audit=json.load(open(ROOT/'results/RECOMPUTATION_AUDIT.json'));cfg=json.load(open(ROOT/'metadata/config.json'));profile=pd.read_csv(ROOT/'metadata/value_profile.csv');age=pd.read_csv(ROOT/'metadata/source_age.csv');counts=pd.read_csv(ROOT/'metadata/mask_counts.csv');ix=pd.read_csv(ROOT/'metadata/window_index.csv');nonscore=int((counts.scored==0).sum())
    cshow=compare.copy();cshow.target=cshow.target.map(dict(enumerate(SHORT)));cshow.condition=cshow.condition.map(dict(enumerate(CNCOND)));cshow=cshow.rename(columns={'slot':'运行','target':'目标','condition':'缺失条件','median':'中位数','ffill':'前值','linear':'线性插值','H':'SAITS-H','M':'SAITS-M'})
    pairedshow=paired[paired.slot.isin(['D06','D07'])].copy();pairedshow.target=pairedshow.target.map(dict(enumerate(SHORT)));pairedshow.condition=pairedshow.condition.map(dict(enumerate(CNCOND)))
    lines=['# 网络指标缺失重建：实际执行报告','',f'生成时间：{pd.Timestamp.now(tz="UTC").isoformat()}。所有产物位于 `{ROOT}`。','',
    '## 先回答五个问题','',
    '1. **实验已实际完成。** 六次正式拟合、三个基线、D05开发评价、D06与D07分别复评，以及V4/Core24h/diagnostic补充评价均已执行。每个深度模型使用三套固定评价掩码，未针对掩码重新训练。',
    f'2. **重建收益有明确条件限制。** 24个主评价单元（2运行×3目标×4条件）中，SAITS-M有{int(compare["M优于线性"].sum())}个优于线性插值，有{int(compare["M优于三基线"].sum())}个同时优于全部三个基线。D06和D07均优于三个基线的目标/条件：'+('；'.join(allbase) if allbase else '无')+'。',
    '3. **其他观测通道提供条件性额外信息，不能泛化到所有运行。** 主评价M在22/24个单元优于H，唯一在两运行均退化的是随机缺失的RX；两运行均出现M优于H的目标/条件：'+('；'.join(cross) if cross else '无')+'。跨目标/条件标准化汇总中，Core24h的M比H误差高22.39%，diagnostic高1.99%；V4仅降低0.44%。这些是固定样本的数值对照，不是统计显著性或独立采集泛化证据。',
    f'4. **变化区间单独核查。** 训练数据90分位变化阈值以上的{len(high)}个主评价单元中，M优于线性插值的有{highwins}个，同时优于线性与H的有{highboth}个。不能仅凭总体均值认定模型能重建突变，详见变化分层表。',
    '5. **适合以受控离线任务验证或负结果加入论文。** 可报告平台导出观测上固定人工缺失的可重建程度及其他通道的条件性贡献；不能宣称可靠在线修复、未来预测、真实采集故障恢复或算法创新。所有收益表述必须附目标、缺失条件、历史非盲复评和基线比较。','',
    '## 数据、任务与实现','',
    f'封存包154条哈希执行前后全部一致。D01–D04训练窗口{int((ix.role=="train").sum())}个，D05/D06/D07各291个；Core24h 289个、V4 292个、diagnostic 99个。保留正常背景和故障活动，不使用分类索引、不筛选容易窗口。60步对应300秒网格区间，首末采样时刻相差295秒；训练步长12、其他步长60，按运行与连续片段取窗，不补尾窗。',
    '每个目标分别查询；接口目标同时隐藏Silver接口6列，CPU隐藏宿主机4列。其他时刻可见，允许同窗口缺口前后观测。原始有效掩码与人工掩码分别保存，仅两者交集评分。连续缺口两侧各留至少6个网格点，不保证这些点原本有值。随机20%为12个设计遮蔽位置，不等于实际可评分比例。',
    f'全部评价病例中有{nonscore}个没有可评分真值，这些病例标记而不记零误差。逐病例记录在metadata/mask_counts.csv。',
    f'模型直接导入[官方SAITS仓库](https://github.com/WenjieDu/SAITS/tree/{cfg["official_commit"]})，固定commit `{cfg["official_commit"]}`。双DMSA、对角注意力掩码和注意力加权融合完整保留，每模块2层，宽64、4头、FFN128、dropout 0.1；每分支144,896参数。使用现有PyTorch 2.11.0+cu128，不声称原论文复现。',
    'M/H均使用24维输入形状和同一初始化种子，H把其余23列全部隐藏。两分支共享逐轮窗口顺序、查询目标、缺失条件与实际掩码；仅查询目标获得MIT和ORT监督。AdamW lr=1e-3、weight_decay=1e-4、batch64。每个训练窗口每轮抽一次查询，目标与条件均匀随机。',
    '为保持训练步数相同，预先固定两分支均连续8轮未改善时成对停止，最多50轮；各自独立选择D05标准化MAE最小checkpoint。该适配可能让较早停滞分支多训练若干轮，已在测试前记录。D05每目标×条件等权，每单元合并三套等数量病例；不读取留出误差选模型。',
    '尺度按D01–D04原始行有限观测估计，不以重叠窗重复加权。所有方法预测统一截0，原始与截断预测都保存；没有事后平滑。前值无前值回退训练中位数；线性插值单侧取最近值，无可见值回退训练中位数。基线使用原始双精度可见值。','',
    '## 主结果：原单位MAE','',
    '比特率单位Mbps，CPU单位百分点。以下先对每个模型种子的3套掩码取均值，再对3个模型种子取均值。RMSE、相对线性改善率、两类种子波动在results/summary.csv；零基线误差的相对改善为未定义。','',table(cshow),'',
    '![MAE随连续缺失长度变化](figures/mae_gap.png)','',
    '## 多变量与单变量配对','',
    'delta为M−H，负值代表M较好；model_sd是每个模型种子先平均三套掩码后的样本标准差。掩码波动独立列在results/mask_seed_variation.csv，不把3×3视为9次独立采集。','',table(pairedshow),'',
    '## 变化、事件与补充评价','',
    f'大变化阈值由训练集相邻5秒有限值绝对差的90分位确定：RX {sc["change_threshold"][0]/1e6:.5g} Mbps、TX {sc["change_threshold"][1]/1e6:.5g} Mbps、CPU {sc["change_threshold"][2]:.5g}个百分点。按隐藏评分点与其前一网格观测之差分层，超过阈值为high，其余rest；前值无真值或跨断档则unknown。分层真值只进入事后评价，不进入掩码生成或模型输入。','',table(high),'',
    '正常背景指不在已记录episode内；故障活动为[start,end)，恢复为[end,end_exclusion)，活动重叠优先。这是封存恢复排除期代理，不是已验证的真实物理恢复时刻。事件标签均为source_marked_inferred；本机可从封存episodes表重建分层，但包内未包含其引用的原始faults/recovery事件日志，因此不能声称已独立重放原始标签推导。完整分层MAE/RMSE和数量见results/phase_summary.csv及results/metrics.csv。没有用事件标签训练。','',
    'V4、Core24h与diagnostic仅在六个checkpoint冻结后执行，分别列于以下各运行标准化汇总（同时保留D05/D06/D07便于对照）。各运行内按目标和缺失条件等权，不平均不同原单位。', '',
    table(summary.groupby(['slot','method']).nmae.mean().unstack().reset_index()),'',
    '## 事先固定的重建曲线','',
    '每个目标选择D06首个可评分窗口，连续120秒、mask101、模型seed17；该规则在训练前冻结。所选RX/TX案例为低值背景夹杂突增，多变量略优于线性而单变量较差；所选CPU案例则线性明显优于两个深度模型。以下给出案例MAE，如实保留，不换成最佳案例。曲线只用于展示案例，不替代完整结果。','',
    '![固定规则重建示例](figures/reconstruction.png)','',table(pd.DataFrame(example_errors)),'',
    '## 时间、资源和核验','',table(pd.DataFrame(fitrows)),'',
    f'六次训练与其D05验证累计计时{sum(sum(f["branch_seconds"].values()) for f in fits):.1f}秒；成对训练wall时间合计{sum(f["wall_seconds"] for f in fits):.1f}秒。GPU为RTX PRO 6000 Blackwell；进程峰值allocated显存{max(f["gpu_peak_allocated"] for f in fits)/2**20:.1f}MiB、reserved显存{max(f["gpu_peak_reserved"] for f in fits)/2**20:.1f}MiB、CPU峰值RSS {max(f["cpu_maxrss_kib"] for f in fits)/2**20:.2f}GiB。这些是实际进程统计，不是整机能源消耗。小样本smoke另计、不作为正式结果。',
    f'独立指标重算状态{audit["status"]}，覆盖{audit["metric_rows"]}行指标、{audit["truth_points"]}个保存的隐藏真值点，最大算术差{audit["max_metric_absolute_difference"]:.3g}。抽样重放覆盖所有六个checkpoint和每个评价运行，按数值容差核对；改变人工隐藏真值不改变输入、可见掩码和基线预测。检查原始来源、时间连续性、计分集合完整性、相同训练轮数、D05选点与封存哈希。',
    '独立代理复核为同模型家族的provisional语义审计，不等同于外部独立复现。详情见metadata/FINAL_REVIEW.md（如有待修项，以该审计和执行状态记录为准）。','',
    '## 局限、未完成项与交付索引','',
    '没有未完成的正式模型分支。第一次评价因循环重复解压而在D05基线阶段主动终止，缓存修复后完整重跑；没有改变模型、掩码、任务或按测试成绩调参。详见metadata/EVALUATION_REPAIRS.md。未补采、未改部署、未引入新故障；baseline2h为方案可选项，本轮未评价。未做物理重复采集、在线因果版本、自然缺失真值恢复或超参数搜索。D06/D07是历史已访问非盲复评。划分按既定运行角色，非严格时间先后切分：部分训练运行的实际日期晚于D05/D06/D07，不能表述为向未来时间泛化。',
    '数据含重复观测，5秒网格并不保证每5秒新测量。metadata/source_age.csv列出各运行源年龄，metadata/value_profile.csv保存各通道相邻不变比例和最长重复段。缺测时真实状态不可观测，结果仅针对导出值人工遮蔽。模型和掩码种子波动不代表跨采集置信区间。',
    '环境警告：Matplotlib旧环境的3D投影不可用，不影响本轮二维图；已显式设置项目内图形缓存。训练的tensor转标量警告只涉及日志取值；环境证据见metadata/ENV_AGENT_CHECK.md。',
    '- metadata/config.json：冻结合同及官方版本；ADAPTATIONS_ZH.md：适配说明。\n- data/、metadata/window_index.csv、masks/：窗口、原始有效掩码、人工掩码及训练抽样。\n- checkpoints/、logs/training.csv、logs/fit_*.json：六次训练与选点证据。\n- predictions/*_truth.parquet：独立真值接口；其余parquet：对齐预测，含截断前后两版。\n- results/summary.csv、metrics.csv、paired_M_H.csv：完整原单位指标与配对结果。\n- results/RECOMPUTATION_AUDIT.json：独立重算与重放。\n- code/：执行、评价、独立检查与报告源码。\n- figures/：PNG、PDF与案例数据。']
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
    (ROOT/'REPORT_ZH.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>网络指标缺失重建实验</title><style>body{font-family:system-ui,sans-serif;max-width:1250px;margin:32px auto;line-height:1.7;color:#17212b;overflow-wrap:anywhere}table{border-collapse:collapse;font-size:12px;width:100%;margin:14px 0}td{padding:5px;border:1px solid #ccc}tr:first-child{background:#eaf0f5;font-weight:bold}img{max-width:100%}h2{border-bottom:1px solid #bbb}@media print{@page{size:A4 landscape;margin:12mm}body{margin:0;font-size:10pt}h2{break-after:avoid}tr,img{break-inside:avoid}table{font-size:8pt}}</style>'+''.join(out)+'</html>')
    import base64
    hp=ROOT/'REPORT_ZH.html';ht=hp.read_text()
    for fn in ['mae_gap.png','reconstruction.png']:ht=ht.replace('figures/'+fn,'data:image/png;base64,'+base64.b64encode((ROOT/'figures'/fn).read_bytes()).decode())
    hp.write_text(ht)
    dump('results/CONCLUSION.json',dict(main_cells=len(compare),M_better_linear=int(compare['M优于线性'].sum()),M_better_all_baselines=int(compare['M优于三基线'].sum()),both_runs_better_all=allbase,both_runs_M_better_H=cross,high_change_M_better_linear=highwins,high_change_M_better_linear_and_H=highboth))
    print('REPORT DONE',flush=True)
if __name__=='__main__':report()
