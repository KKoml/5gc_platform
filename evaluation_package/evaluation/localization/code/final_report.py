"""Build the Chinese interpretation from completed, verified fixed-run results."""
import json
import pandas as pd
from pathlib import Path
R=Path(__file__).resolve().parents[1];s=pd.read_csv(R/'metrics/SUMMARY.csv');v=json.loads((R/'audit/RESULT_VERIFICATION.json').read_text());assert v['status']=='PASS'
def table(head,rows):return '\n'.join(['| '+' | '.join(head)+' |','|'+'|'.join(['---']*len(head))+'|']+['| '+' | '.join(map(str,r))+' |' for r in rows])
def metric(model,role,key):
 r=s[(s.model==model)&(s.role==role)&(s.stratum=='all')].iloc[0];return f'{100*r[key+"_mean"]:.2f} ± {100*r[key+"_std"]:.2f}'
models=['LSTM','TCN','RF_24','RF_FL10','ReadyMaskRF'];roles={'test':'D06–D07 复评（144）','external_validation':'V4（72）','supplementary_only':'Core24h 闭集（24）'}
main=table(['模型','评价集（病例数）','联合 Top-1 %','联合 Macro-F1 %'],[[m,n,metric(m,r,'top1'),metric(m,r,'macro_f1')] for r,n in roles.items() for m in models])
rank=table(['评价集','联合 Top-3 %','MRR','机制准确率 %','机制 Macro-F1 %','作用点准确率 %'],[[n,metric('RF_24',r,'top3'),f"{s[(s.model=='RF_24')&(s.role==r)&(s.stratum=='all')].iloc[0].mrr_mean:.4f}",metric('RF_24',r,'mechanism_accuracy'),metric('RF_24',r,'mechanism_macro_f1'),metric('RF_24',r,'target_accuracy')] for r,n in roles.items()])
day=table(['模型','D06 Top-1 %','D07 Top-1 %'],[[m,metric(m,'D06','top1'),metric(m,'D07','top1')] for m in models])
mechanisms=['n3-block','n3-delay','n3-loss','n4-block','n6-block','instance-stop'];mrows=[]
for mechanism in mechanisms:
 vals=[]
 for role in roles:
  r=s[(s.model=='RF_24')&(s.role==role)&(s.stratum==mechanism)].iloc[0];vals.append(f'{r.top1_mean*100:.2f} ± {r.top1_std*100:.2f}')
 mrows.append([mechanism]+vals)
mt=table(['真实机制','D06–D07 联合Top-1 %','V4 联合Top-1 %','Core24h 联合Top-1 %'],mrows)
comp=pd.read_csv(R/'reports/COMPOSITE_CASES.csv');comp=comp[(comp.model=='RF_24')&(comp.seed==17)];ct=table(['复合病例','真实作用点','RF24 seed17 的前三候选（概率）'],[[r.fault_id,r.target,r.top3] for r in comp.itertuples()])
t=json.loads((R/'tracker.json').read_text());tt=table(['模型','seed','训练耗时秒','运行epoch','选中epoch'],[[r['model'],r['seed'],f"{r['seconds']:.3f}",r['epochs_run'],r['selected_epoch'] if r['selected_epoch'] is not None else '不适用'] for r in t])
report=f'''# RCA_joint12：受控 Core 故障机制—作用点联合诊断结果

任务状态：**15/15 个正式拟合成功，留出评价与结果重算完成**。此前输入角色阻塞已依据用户限定澄清解除；历史阻塞报告保存在 `audit/history_blocked/FINAL_REPORT_ZH.md`，原 `audit/BLOCKER.json` 和两份差异表原样保留。本报告不否认曾发生阻塞。

## 1. 结论

**现有24列自采观测支持范围有限的机制—作用点联合诊断，证据超出了仅区分 Gold/Silver 路径；但不足以支持所有机制稳定可分或跨场景可靠诊断。** RF24在D06–D07联合Top-1为65.05%，V4为64.81%，高于相同12类任务的RF10和Ready/缺失对照。Core24h降至45.83%，两种深度模型在Core24h更明显退化。

不是仅靠Ready/缺失获得全部成绩：ReadyMaskRF在上述三个角色的联合Top-1均为25%，RF24在完整12候选中评价网络故障子集时分别为58.06%、57.78%、35.00%，ReadyMaskRF的对应网络子集均为10%。但这些对照只能证明当前输入与模型组合存在额外区分信息，不能证明真实因果机制或排除用户行为混杂。

路径识别强于机制区分：RF24在D06–D07的作用点边缘准确率100%，机制边缘准确率66.67%；Core24h分别为83.33%和45.83%。因此可写“受控场景下的联合诊断/候选排序可行性”，不应写“完整RCA问题已解决”。

## 2. 任务、标签与角色合同

正式任务是“给定记录起点后固定60秒观测、以实际注入记录为标签的机制—作用点联合诊断/根因候选排序”。6种机制依次为n3-block、n3-delay、n3-loss、n4-block、n6-block、instance-stop，每种依次为upf-silver、upf-gold，共12类。网络机制对应Silver/Gold关联路径，并不全部是UPF软件内部故障。fault_id只生成标签与审计，未输入模型。

源机验证过的delay/loss映射按 `source_verified_rule_received_in_prompt` 保存；本机未访问原始faults.jsonl。原 `source_marked_inferred` 等质量标记继续保留，未提升为独立业务损伤因果真值。

- 训练：D01–D04共288，每类24；验证D05共72，每类6。
- 固定既有划分追加复评：D06–D07共144，每类12，逐日各72。历史上已访问，不是新盲测，也不是日历前向划分。
- V4外部验证72，每类6；Core24h补充闭集24，每类2，另4个delay+loss复合病例；diagnostic5共8。
- 612病例=608闭集+4复合；完整621台账另有8个AMF/SMF stop和1个V4 prelude排除。baseline2h未加入训练。

Core24h唯一特殊run为 `supp_core24h`。保留source_episode_run_split=event_block_protocol，registry_split/index_split/effective_split=supplementary_only。该规则仅处理精确run、slot和值组合，36条台账/28个FL病例匹配；Core24h进入预处理或训练的病例数为0。所有其他不一致继续报错。详见 `data_contract/role_resolution.json` 与 `audit/BLOCKER_RELEASE.json`。

## 3. 输入、预处理与模型

直接复用原FL的[start_row,stop_row)12步×5秒窗口；每个病例只有一窗，无新增事前或事后数据。实际截点在记录起点之后、60秒以内，anchor为观察结束附近的锚点。612窗逐元素核验及时间边界见 `data_contract/window_boundaries.csv`。

主输入为FD_detection_24白名单的24个观测值和对应24个mask。最低窗口覆盖率71.53%，W1没有整窗全缺通道，固定0.5覆盖要求保留全部612病例。原始NaN保存在cache；仅从288个训练事件的观测值估计中位数插补、median/IQR缩放，零IQR回退训练标准差再回退1；Ready观测保留0/1，mask独立保留。训练样本ID、参数和覆盖均已保存。

LSTM沿用两层width64；TCN沿用两个残差块、dilation1/2、kernel3，均dropout0.1，输出12类。交叉熵、AdamW lr0.001/weight_decay0.0001、batch32、最多50epoch。只用D05 Macro-F1早停，patience8；同分优先低验证损失，再优先早epoch。全部seed17/29/43共用同一配置。旧checkpoint未复用。

RF24与RF10均提取各数值通道的均值、总体标准差、最小值、最大值、末值、末减首值及观测比例，宽度分别168/70。ReadyMaskRF只使用两个Ready值的同样6种统计、24列逐步mask和观测比例，共324维；没有CPU/内存/流量数值。三个RF变体均500树、min_samples_leaf2、max_features=sqrt、max_depth=None。没有网格搜索、过采样或复制病例。

## 4. 主结果

下表为三个seed的均值±样本标准差，均按事件评价。seed不是独立物理采集重复，不据此给出泛化显著性。模型名称RF_24/RF_FL10对应RF24/RF10。

{main}

W1均匀随机参考：联合Top-1=8.33%，Top-3=25%，机制准确率16.67%，作用点准确率50%。排序相同概率时严格按冻结类别顺序。随机参考不是额外训练模型。

RF24的排序与边缘分类结果如下（全部模型的相同指标和标准差见 `reports/FULL_TABLES_ZH.md`）。机制概率由同一12类概率对作用点求和；作用点概率对机制求和。边缘argmax可能与联合argmax分量不同，未拼接两个独立最优模型。

{rank}

逐日结果：

{day}

RF24在diagnostic5联合Top-1为95.83%±7.22%，Macro-F1为97.22%±4.81%。这里只含n3-block和instance-stop的4个有真值支持的联合类别、共8病例；Macro-F1只平均这4类，但仍在完整12类中预测。该小样本高分不能替代完整机制验证。逐项support保存在 `metrics/ALL_METRICS.csv`。

## 5. 对照与机制差异

相对RF10，RF24联合Top-1在D06–D07提高18.98个百分点（相对41.21%）、V4提高18.52个百分点（40.00%）、Core24h提高11.11个百分点（32.00%）。这是同时扩充14个数值通道及其mask/比例后的整体收益，不能归因到某一个KPI。相对ReadyMaskRF则分别提高40.05、39.81、20.83个百分点。所有模型对照、逐seed配对差与相对变化见 `metrics/CONTROL_COMPARISONS.csv`。

RF24逐真实机制的联合识别结果如下；子集评价仍保留全部12个候选，不以已知真值先过滤候选。

{mt}

instance-stop和n4-block在这些固定评价病例上的联合Top-1均为100%；不能外推为任意运行中永远可分。n3-block、delay、loss和n6-block较弱，尤其Core24h的n3-loss和n6-block联合识别为0。两种深度模型Core24h机制边缘准确率均16.67%，表明其机制判别未稳定迁移。

D06–D07的RF24主要机制混淆为n6-block→n3-delay、n3-delay→n6-block以及两者→n3-block。三个seed累计分别31、19、19/17次；这是同一批病例重复预测的计数，不是新增物理事件。Core24h常见网络机制被判为n4-block。六类边缘混淆矩阵及所有12×12联合混淆矩阵均在 `metrics/`。

## 6. 错误病例与观测

固定使用seed17、按每个真实联合类别的首个错误病例输出示例，不挑选最佳seed。`reports/ERROR_CASE_OBSERVATIONS.csv`包含所有模型的示例及24列观测均值/覆盖。

- D06 `b02_p03_n3_delay_silver_core`：真实n3-delay|upf-silver，RF24预测n6-block|upf-silver。窗口覆盖100%，两个Ready均为1，Silver tx_dropped_delta均值0，Silver接收速率均值约206,940.5 bps。此例不是缺失窗口或明显Ready停机，却发生机制混淆。
- V4 `r01_p04_n3_delay_gold_core`：真实n3-delay|upf-gold，预测n6-block|upf-gold。窗口覆盖100%，两个Ready均为1，Silver接收速率均值约1,316,283.1 bps。Gold关联路径缺少对应接口观测，现有示例不能判定哪些信号缺失导致错误。
- Core24h `r1_05_n3_delay_silver`：真实n3-delay|upf-silver，预测n3-block|upf-gold，机制与作用点均错。覆盖100%，两个Ready均为1，说明“无缺失”不等于“信息足够”。

以上是错误和观测的并列描述，不是对错误原因的因果证明；未使用SHAP、重要性或注意力冒充因果解释。

## 7. 四个复合病例

四个病例真实干预均为n3-delay+n3-loss，不属于12类。以下仅展示RF24固定seed17的前三候选；全部15个模型/seed的60条案例在 `reports/COMPOSITE_CASES.csv`，完整12概率仍保存。没有计算12类正确率或未知故障检测指标。

{ct}

## 8. 执行与核验

训练前真实训练集smoke各取一例/类、共12病例。LSTM36步、TCN21步达到该小样本100%训练准确率，权重丢弃；这些数字仅验证可训练性，不是正式模型结果。正式拟合计数始终为15。

首个LSTM实测3.097秒，39epoch、选31epoch，PyTorch峰值分配显存50,475,008字节，进程峰值RSS1,450,688 KiB。根据首次实测记录其余5个深度拟合估计15.48秒；RF当时耗时未知。实际15次拟合计时之和20.342秒，不包括数据检查、smoke、评价和报告；没有据此编造GPU小时。详细日志与tracker保存全部耗时、epoch和状态。

{tt}

`audit/FORMAL_START_FREEZE.json`记录smoke通过后的正式启动冻结，`audit/TEST_FREEZE.json`记录全部模型完成后的留出评价前冻结。配置、训练代码、模型和预处理哈希核验一致。

第一次评价在保存分层指标支持类别时遇到numpy.int64无法JSON序列化的实现错误。原冻结代码保留，修正副本 `code/pipeline_eval_v2.py`只将该标签列表转换为Python整数；差异、首轮失败日志和部分输出均保存于 `audit/EVALUATION_SERIALIZATION_FIX.json`、`audit/evaluation_attempt1/`。未变更预测数学定义、模型、超参数或seed，未重训，没有基于留出分数选择配置。

最终使用独立NumPy混淆矩阵/排名算术重算全部1800行指标，最大差值{v['max_metric_error']:.3g}；从15个保存模型重放9180个病例概率，最大差值{v['max_replay_probability_error']:.3g}。均值/样本标准差、support、排名、混淆矩阵、checkpoint选择及源包154哈希均通过。详见 `audit/RESULT_VERIFICATION.json`。这一独立算术检查不等于外部独立研究团队复现。

## 9. 局限与可写贡献

1. Silver有接口速率/drop/error列，Gold没有对称接口列；观察能力不对称。模型中没有不存在的控制面错误计数或日志。
2. W1的用户行为背景可能混杂；Core24h仅24个闭集病例，提供有限Core-only对照，其退化不能单独归因于模型、数据或背景中的某一项。
3. 只有288个训练事件且沿用既有非盲划分。滑窗、随机seed和不同模型都不是新的物理采集重复。
4. 模型已知记录起点并等待固定60秒后诊断；这里不验证自动检测故障起点，也不验证提前预测。旧检测器漏检不能被本实验分数掩盖。
5. 没有独立证明每次干预产生业务损伤，没有验证自然未知故障、完整因果链、开放集拒识或端到端自动RCA。

可采用的贡献表述：平台自采Core观测在既定受控干预场景下支持机制—关联路径联合诊断及候选排序；24列观测相比原10列和Ready/缺失对照提供额外区分信息，但机制混淆及跨角色迁移限制仍明显。当前证据不止于路径定位，也不能泛化为完整可靠的根因分析能力。

## 10. 产物入口

本目录：`evaluation/localization/`。

- `config.json`、`README.md`、`code/`：冻结配置、环境与重跑方法。
- `data_contract/sample_index.csv`、`event_disposition_621.csv`：新标签、四类角色字段和完整事件去向。
- `data_contract/feature_whitelists.json`、`coverage.csv`、`fit_sample_ids.json`：输入白名单、覆盖与拟合范围。
- `models/`、`logs/`、`tracker.json`：15组模型、训练日志、预处理参数及正式状态。
- `predictions/`：每组612病例的12概率、全部排名、预测/真值、配置/模型身份，含4复合案例。
- `metrics/ALL_METRICS.csv`、`SUMMARY.csv`、`CONTROL_COMPARISONS.csv`、混淆矩阵：全部逐seed/逐run/分层指标。
- `reports/FULL_TABLES_ZH.md`、`ERROR_CASE_OBSERVATIONS.csv`、`COMPOSITE_CASES.csv`：完整数值与案例。
- `audit/RESULT_VERIFICATION.json`、各冻结回执和历史阻塞/解除记录：核验链条。
'''
(R/'reports/FINAL_REPORT_ZH.md').write_text(report)
print('FINAL_REPORT_WRITTEN')
