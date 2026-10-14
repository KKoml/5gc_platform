> 当前主分支已提供1 s平台导出、四类任务的评测输入、模型、配置和代码。PCAP、完整原始采集记录及完整业务轨迹语料不在当前材料范围内；选定平台源码及扩展附录位于独立平台分支。详见 [DATA_ACCESS.md](DATA_ACCESS.md) 和 [附录导航](APPENDIX_NAVIGATION.md)。

# D-GATE 实验附录（中文平台修订稿）

本文件保留详细实验附录的原 D.3、E.1—E.3 编号。当前英文六页正文引用的 A–D 请从[正文配套附录](manuscript_supplement/README.md)进入；编号分工见[附录导航](APPENDIX_NAVIGATION.md)，当前英文附录不设D.4。原实验材料基线与[当前英文正文指纹](manifests/english_manuscript.json)分别保留。

# Appendix D.3　四类任务的数据构造

本附录对应中文平台修订稿，依据实际配置、任务索引、训练记录和保存结果整理。论文版本及参与核验的正文、图表文件哈希见 `manifests/paper_baseline.json`。附录单独交付，不修改正文。数值对应、检查点解释保存输出、历史论文运行身份分别记录：前两者的已有证据不能代替最后一项。

主划分为 D01—D04 训练、D05 验证与模型/阈值选择、D06—D07 已访问过的后验测试。七个标识代表七次独立执行，不是一条连续七天序列；窗口不跨运行。模型种子与人工掩码种子反映算法变化，不是平台独立重复。`validation_v4r6`、`supp_core24h`、`diagnostic5` 单列；`development_excluded` 不进入正文主测试。旧 `task_data/provenance/SOURCE_PROTOCOL.json` 中名为 T1 的 5 s 任务不是本论文预测任务，不能混用。

## D.3.1　网络性能预测

实际输入为 `prediction_inputs/D01` 至 `D07/` 中的 `T1_history.csv.gz`、`T1_targets.csv.gz`，以及 `evaluation_package/evaluation/prediction/outputs/indices/` 中按目标与运行冻结的 Parquet 索引。截止点 c 的历史为 [c−60,c)，60 个 1 s 位置，窗口步长 60 s；经过 [c,c+60) 的间隔，目标为 [c+60,c+70) 内有效目标值均值。十个目标桶至少八个有效。目标表保留候选样本有效性和计数；模型实际样本集合由冻结索引决定。未来目标有效性只用于评测资格，不作为输入。

18 个变量的精确顺序为：

```text
n3_uplink_bitrate_bps, n3_downlink_bitrate_bps, n6_bitrate_bps,
cp_pdu_session_success_rate, cp_pdu_session_failure_count,
end_to_end_rtt_ms, jitter_ms, packet_loss_rate,
cp_active_session_count, cp_pending_session_count,
cp_pdu_session_request_count, registration_success_rate,
registration_failure_count, registration_request_count,
n4_bitrate_bps, host_cpu_pct, host_mem_used_pct, host_loadavg_1
```

每个变量附 `<field>__missing`，非有限值时为 1。`prediction/src/data.py:transform` 用训练通道中位数填补，再用训练均值/标准差标准化，得到 N×60×36 的数值与缺失标记张量。PatchTST 仅取目标历史 N×60×1；XGBoost 对 36 通道计算均值、总体标准差、最小值、最大值、最后值及 (末值−首值)/59，共 216 特征。SMA 仅使用历史末十个位置中的有效目标值。目标标准化参数来自训练目标观测；预测还原到原单位，比特率评测除以 10^6。

正文三个目标为 `n3_downlink_bitrate_bps`、`n6_bitrate_bps`、`host_cpu_pct`。完整结果另保留 `end_to_end_rtt_ms`，其语义是原来源定义的流 RTT 代理，不能改称 UE 到 DN 的端到端实测 RTT。N6 是流记录定义的聚合量，不等于已核实的逐秒接收吞吐。配置仍将部分原生采样间隔、保持规则和在线可用性列为未知。本输入来自后续四字段前缀修复视图；截止点检查不能自动证明所有原始测量都具有严格在线因果可用性。

输入对照包括目标历史与缺失标记、时间计划及仅缺失标记。时间计划为行位置/86400，加 600、900 s 周期的正弦/余弦；对照复用主 XGBoost 在 D05 选择的超参数。N6 时间计划对照表现接近多变量模型的结果保留。`verification/replay_prediction_checkpoints.py` 检查顺序、时间和缺失标记；CSV 标签往返允许 2e−8 原单位加 2e−15 相对误差。预测历史不是从本包现有 81 字段表重新生成的。

## D.3.2　故障检测

实际观测为 `data_machine/dataset/task_data/data/<run>/core_features_5s.parquet`，样本由 `tasks/FD_detection/index.parquet` 绑定，事件及资格由 episodes、EVENT_EVALUABILITY 和 `metadata/protocol.json` 约束。每个样本为零基行区间 [start_row,stop_row) 的 12 个 5 s 截止点，最后点为评分锚点。`eligible` 包含时间、范围和总体有效观测比例至少 0.8 的资格要求；原表保留 NaN，有限值状态形成有效性标记。旧 `is_valid_row` 不是通用资格规则。

检测、执行后的识别及缺失重建使用以下 24 变量：

```text
amf-a__cpu_millicores, amf-b__cpu_millicores,
smf-silver__cpu_millicores, smf-gold__cpu_millicores,
upf-silver__cpu_millicores, upf-gold__cpu_millicores,
amf-a__memory_bytes, amf-b__memory_bytes,
smf-silver__memory_bytes, smf-gold__memory_bytes,
upf-silver__memory_bytes, upf-gold__memory_bytes,
core-host-local__cpu_pct, core-host-local__mem_used_pct,
core-host-local__loadavg_1, core-host-local__swap_used_bytes,
core-if-upfgtp-silver__rx_bitrate_bps,
core-if-upfgtp-silver__tx_bitrate_bps,
core-if-upfgtp-silver__rx_packet_rate_pps,
core-if-upfgtp-silver__tx_packet_rate_pps,
core-if-upfgtp-silver__tx_dropped_delta,
core-if-upfgtp-silver__tx_errors_delta,
upf-silver__ready, upf-gold__ready
```

正常数据拟合模型使用恰好 55,196 个 `eligible ∧ split=train ∧ normal_train_window` 的 D01—D04 窗口，整个历史排除已记录活动、恢复排除期和前导操作。预处理用同一训练子集的中位数填补及中位数/IQR 缩放；IQR 为零时退到训练标准差，再退到 1。已观测 Ready 保持 0/1，缺失 Ready 填补后有效标记仍为 0。AE/TranAD 使用数值和有效标记；KAN-AD 的损失与评分使用有效标记。只有有效数值通道贡献重建误差，缺失标记不参与误差项。

监督 RF 使用全部合格训练窗口及注入正标签，复用训练预处理，计算每变量末值、均值、标准差、末减首、末三点均值减首三点均值、有效比例和末点有效标记，共 168 特征，拟合66,069个训练窗口（7,705阳性）。这是监督方式不同的后验优化，不能包装为正常拟合方法的同条件替代。标签表示记录的干预活动，不是独立认证的业务损害真值。运行标识、时间、操作、标签和计划元数据不进入模型。

D05 按 0.1 或 1 次误报/h 标定阈值。超过阈值的连续有效报警点组成段；无效、阴性或缺点打断段，间隔超过 7.5 s 也打断。段起点为首个阳性有效截止点，按确定顺序在 [事件起点,事件终点) 一对一匹配。正常暴露按每个合格且已评分的正常点计 5 s；无效点不贡献分母。不进行点调整或测试分数归一化，验证目标不代表测试误报率必然达标。保留低召回、漏报与无报警工作点。

## D.3.3　已知注入起点的类型与关联目标识别

`tasks/FL_localization/index.parquet` 将事件绑定到上述观测；`localization/data_contract/` 保存特征白名单、类序、样本索引、窗口边界、事件处置和覆盖记录。已知记录起点 s 后取 (s,s+60 s] 内 12 个 5 s 截止点，有效观测比例至少 0.5。本任务不检测 s。主训练/验证/测试为 288/72/144 例，每个联合类分别 24/6/12 例。四个 delay+loss 复合事件保留为闭集指标范围外；`supp_core24h` 单列补充，不能用于训练。

六种机制为 n3-block、n3-delay、n3-loss、n4-block、n6-block、instance-stop，与 upf-silver/upf-gold 交叉形成 12 类，类序见配置。联合类取十二概率最大项；类型与关联目标分别对另一维度求和后取最大项，平局使用固定类序。关联目标表示注入 UPF 或关联路径，不是独立证明的因果根因。

预处理仅拟合 288 个训练例的 3,456 个时间位置：有效值中位数填补、中位数/IQR 缩放，标准差→1 回退；Ready 中心 0、尺度 1；保留有限值掩码。LSTM/TCN 输入 N×12×48。RF_24 使用均值、标准差、最小、最大、末值、末减首及有效比例，共 168 特征；RF_FL10 按 `feature_whitelists.json` 取 SMF/UPF CPU、内存和就绪十变量，共 70 特征。ReadyMaskRF 使用两个 Ready 的统计及完整掩码和掩码均值，共324特征。所有对照保持同一病例集合与配置，不用旧 FL10/FL6 计划替代实际的 24 变量联合识别任务。

## D.3.4　离线缺失重建

`imputation/data/<slot>.npz` 保存 raw、original_valid、time、phase、delta；`metadata/window_index.csv` 绑定到 5 s 任务表。先按连续 5 s 时间段分段，再构造 60 位置（300 s）窗口，训练步长 12 位置，评测步长 60；遇到时间缺口重新分段，不填补不足窗口的尾部。均值、标准差、中位数和变化分层阈值仅由 D01—D04 计算。上述 24 变量中目标下标 16 为 RX，17 为 TX，12 为 CPU。

固定 `masks/<slot>.npz` 中人工时间掩码维度为 N×3目标×4条件×3掩码种子×60。Random20 无放回选 12 个位置；gap30/60/120 连续遮去 6/12/24 位置，两侧至少各留 6 位置。接口目标同时遮去通道 16—21，CPU 同时遮去 12—15，降低同组变量直接泄露。原缺失始终不可见；仅人工遮去且原本有限的目标值计分。H 将所有非目标变量标为不可见，但仍用相同 24 通道结构；M 保留其他有效观测。缺失位置填训练均值，标准化后为零，另传有效标记。

每训练窗口每轮随机查询一个目标/条件，目标及条件均匀抽样，M/H 共用窗口顺序和遮盖计划。模型种子为 17/29/43；固定评测掩码种子为 101/202/303。训练中位数、前向填补（首部退到训练中位数）、窗口内双向线性插值使用相同目标/掩码。保存原始预测，所有方法的报告预测下界为零。D05 选择检查点后才评测其他运行。phase 的恢复标记是记录排除期代理，不代表认证的物理恢复。缺口两侧观测可用，因此是人工缺失下的离线重建。两次主运行 RX 随机缺失下 M 均略逊 H，该负面结果保留。

## D.3.5　core 交接与未确认关系

`manifests/input_manifest.csv` 给出实际文件相对路径、SHA-256、行数或数组形状、字段/类型、时间范围、运行别名、处理程序及程序哈希。`core_handoff.csv` 分列转换前与转换后哈希，并注明压缩、格式变换、标识匿名化或路径元数据删除；不同格式不要求同哈希。`LINEAGE.md` 记录本次来源复查及缺口。当前 1 s 导出、预测修复历史和 24 变量 5 s 表是分别版本化的视图，同槽位同时间不是转换证据，不能猜测补齐。


---

# Appendix E.1　模型与超参数

`manifests/fit_records.csv` 从实际训练记录提取模型、种子、执行/选中轮数、参数量、状态及完整记录。其哈希标识整理副本；记录内部原始程序哈希标识它自己的来源，不应误当作适配后文件哈希。`selected_prediction_models.csv` 给出各目标 D05 实际赢家。仅存在配置候选不能证明已执行。

| 任务/模型 | 结构与适配 | 训练及选择 |
|---|---|---|
| 预测/SMA | 末 10 个位置的有效目标均值 | 无拟合，同一冻结索引 |
| 预测/PatchTST | 60×1 目标历史，d_model=64，heads=4，layers=2，FFN=128，patch=12，stride=6，dropout=0.1，延迟区间均值标量头 | AdamW，候选 lr=0.001/0.0003，weight_decay=1e−4，batch=128，max_epochs=50，patience=8，grad_norm=5，SmoothL1(beta=1)；D05 原尺度 MAE；种子42/43/44 |
| 预测/XGBoost | 18 值+18 缺失标记的六统计，共216特征；500树，lr=0.04，min_child_weight=3，subsample=0.9，colsample_bytree=0.9 | depth候选4/6，平方误差；D05 MAE；种子42/43/44；输入对照复用主模型赢家 |
| 预测/TimeFilter（完整结果） | d_model=64，FFN=128，heads=4，layers=2，patch=12，dropout=0.1，alpha=0.1，top_p=0.5，位置编码，多变量输入 | 同神经训练预算，MoE辅助系数0.05；逐目标赢家见训练记录 |
| 检测/AE | flatten(12×48)→256 GELU→64→256→12×48，328,832参数，数值通道限定损失 | AdamW，lr=0.001，weight_decay=1e−4，batch=128，max50，patience8；D05 当前正常点损失最小；种子17/29/43 |
| 检测/适配TranAD | 作者commit `7ffb98d0c18189cc3d9ab732b4cb0278200a0af0`；输入48，d_model96，heads48，单层encoder、两个单层decoder；有界logistic两阶段自条件、decoder2对抗梯度；200,448参数 | 同AE预算；当前有效点两阶段有界空间残差平方均值；不能声称原论文精确数值复现 |
| 检测/适配KAN-AD | 作者commit `7c3a0d96b77e0d609660a240c2b11db084ba523f`；共享单变量、24通道一阶差分适配，native_window10、order2，从此前位置预测当前锚点；188参数 | Adam lr0.003，StepLR(5,0.75)，max50、patience8、batch128；D05 当前正常预测损失；有效数值点绝对残差均值 |
| 检测/监督RF | 24×7统计，160树，depth12，min_samples_leaf20，max_features=sqrt，balanced_subsample，n_jobs8 | seed17在D05有界比较RF/HGB候选：0.1/h下召回最高→FAR最低→AUPRC最高；赢家以29/43重拟合；测试后不追加搜索；监督制度不同 |
| 已知起点/LSTM | 两层64单元，dropout0.1，输入48/输出12，末位置分类头；63,244参数 | AdamW lr0.001，weight_decay1e−4，batch32，max50，patience8；D05宏F1最大→CE最低→最早轮；种子17/29/43 |
| 已知起点/TCN | 两残差因果块，width64、dilation1/2、kernel3、dropout0.1，末位置头；50,252参数 | 同分类训练与选择规则 |
| 已知起点/RF及对照 | 500树，min_samples_leaf2，max_features=sqrt，max_depth=null，class_weight=null，n_jobs4 | RF_24、RF_FL10、ReadyMaskRF同一固定配置，种子17/29/43，测试不调参 |
| 重建/SAITS-M,H | 作者commit `660b87f19c1277065f314f24134f646229e89ca9`；实际构造 `SAITS(2,1,60,24,64,128,4,16,16,0.1)`，input_with_mask、inner_group共享、对角attention mask；H屏蔽非目标，不改变参数量 | AdamW lr0.001，weight_decay1e−4，batch64，max50；两分支同时stale≥8才停；当前目标MIT MAE+三个重建输出在当前目标可见位置的ORT MAE均值，1:1；各分支按D05等权目标/条件标准化截断MAE选点；17/29/43 |

检测的正常拟合模型仍使用带标签的 D05 标定阈值，不是端到端完全无监督。候选包括正无穷和 D05 全部有限得分，在实际 FAR 不超过预算的候选中依次最大化命中、最小化误报、取较高阈值。D06/D07 固定阈值，不做测试归一化或点调整；保留无报警及漏报结果。

历史验证环境为 Python3.10.12、NumPy2.2.6、pandas2.3.2、PyArrow21.0.0、scikit-learn1.7.1、SciPy1.15.3、XGBoost3.0.4、PyTorch2.11.0+cu128/CUDA12.8、NVIDIA RTX PRO6000 Blackwell。完整记录见 `evaluation_package/evaluation/verification/runtime_environment.json`，包依赖见 requirements-replay.txt。本次仅统计核验的当前环境另记于 `checks/current/environment.json`。历史神经推理/训练使用CUDA，CPU回退未验证。

作者代码地址、固定版本和许可证随第三方源码保留；上述模型适配内容单列。项目整体发布许可须由仓库所有者确定，本次不自行添加新授权。


---

# Appendix E.2　完整结果与论文对应

使用正文 TeX 标签，通过 `PAPER_RESULT_MAP.md`、`manifests/paper_result_map.csv` 和 `result_files.csv` 定位输入、配置、训练记录、保存结果及统计/绘图程序。当前论文版本与历史执行的身份绑定仍未确认；数值和已定位执行的产物对应具有证据，不能扩展为历史身份已闭合。

| 任务 | 保留的完整结果 | 正文汇总规则 |
|---|---|---|
| 预测 | `prediction/outputs/metrics_long.csv` 共1,000指标行，含额外模型/目标/输入对照；逐样本预测和冻结索引 | 每种子先等权平均D06/D07 MAE，再算三种子均值及样本SD(ddof=1)；SMA无训练随机性，比特率换为Mbit/s |
| 检测 | 九个正常拟合模型/种子记录，D05/test得分与阈值；监督RF六个种子/预算测试行；完整预算0.1/1.0 | 合并两次完整主测试运行，144主事件、40.53有效正常小时；各种子先算事件指标，再均值/样本SD。FAR为报警段数/正常小时，不是逐点FP比例 |
| 已知起点识别 | `localization/metrics/ALL_METRICS.csv` 共1,800分组指标行；15训练记录/概率文件；混淆与对照 | 合并144测试例，每联合类12例；每种子算联合/类型/关联目标准确率及宏F1，再均值/样本SD；保留FL10、ReadyMask对照 |
| 缺失重建 | `imputation/results/metrics.csv` 共12,636指标行；54保存预测文件、真值、固定掩码及逐掩码/逐模型种子统计 | 运行内先平均101/202/303掩码，SAITS再平均17/29/43模型种子，最后等权平均D06/D07；仅遮盖且原有效的目标点计分 |

表中路径相对 `evaluation_package/evaluation/`。逐模型配置、选中轮数及验证分数见 `fit_records.csv` 与 `selected_prediction_models.csv`；复制的原记录保留候选/失败/跳过状态。没有用新结果替换历史保存结果。

完整材料保留时间计划对照的强表现、正常拟合检测方法不足10%的召回、监督RF与正常拟合制度差异，以及SAITS-M在两次运行的RX随机缺失下退化。记录中D05与测试划分分离不改变D06/D07已访问事实；后续RF优化也不能称为盲测。

本次从保存预测重算15个分类模型/种子行（60指标）、54个重建预测文件的全部12,636指标行；正常拟合检测重做D05阈值标定及六个均值/SD工作点摘要；预测重算200个MAE、正文九组均值/SD和54输入对照值。回执见 `checks/current/`。`verification/results/` 中检查点重放及新训练记录来自2026-10-03，是保留的既有验证，不是本次重新执行。

当前英文六页稿将预测、检测、分类与定位、缺失重建分别列为表II、III、IV、V；图1–3分别为架构、部署和实物平台照片。旧检测/识别图及绘图程序作为补充材料保留，其文件和保存结果未改，不应再用旧图号定位当前正文。当前标签、结果入口及旧标签对照见 PAPER_RESULT_MAP.md 和 manifests/paper_result_map.csv；当前英文稿指纹见 manifests/english_manuscript.json。架构/部署/实物图不绑定模型训练记录。旧稿“32数值指标”的历史口径差异继续保留于 LINEAGE.md，当前英文稿未使用该子计数。


---

# Appendix E.3　复现指南

从材料根目录先执行 `sha256sum -c SHA256SUMS.txt`。运行时使用独立可写副本：部分既有验证程序会写 `evaluation_package/evaluation/verification/results/`，预测推理临时建立cache。保留封存副本和原实验。本包的表级入口不需要原实验目录或原始PCAP。

在隔离环境安装 `evaluation_package/evaluation/verification/requirements-replay.txt`。神经推理另安装与历史记录匹配且适合本机的PyTorch/CUDA；不声称CPU推理已验证。本次统计环境见 `checks/current/environment.json`。检查点推理前应检查GPU和当前实验占用。本次仅重算统计，不启动新训练。

## E.3.1　保存结果重算：无需推理

```bash
cd evaluation_package/evaluation
python verify_paper_tables.py
python prediction/verify_saved_predictions.py
cd ../..
python tools/recompute_saved_metrics.py
python tools/recompute_detection_saved.py
python evaluation_package/evaluation/verification/verify_data_package.py
```

输入：保存预测/索引；D05/test检测得分、阈值和事件记录；分类概率/标签；重建真值/预测、训练尺度；当前1秒导出/字典和5秒表。输出：控制台回执、预测 `outputs/T1_SAVED_OUTPUT_RECOMPUTATION.json`、既有 `verification/results/` 回执、新 `checks/current/saved_metrics.json` 与 classification_recomputed.csv。本次确认统计数值、被检查的数据合同和分别记载的来源哈希，不执行模型推理，不证明历史身份。

## E.3.2　检查点推理

```bash
python evaluation_package/evaluation/verification/replay_prediction_checkpoints.py
python evaluation_package/evaluation/verification/replay_detection_checkpoints.py
python evaluation_package/evaluation/verification/replay_supervised_rf_checkpoints.py
python evaluation_package/evaluation/verification/replay_localization_checkpoints.py
python evaluation_package/evaluation/verification/replay_imputation_checkpoints.py
```

输入：预测历史/目标与尺度、任务表/索引、拟合预处理、模型权重和固定人工掩码；输出到既有verification/results，预测退出后删除临时cache，重建使用临时目录。保留的2026-10-03回执覆盖54个预测模型/数据组合、九个正常拟合及三个RF检测检查点、15分类模型、六SAITS模型与54预测文件。这是既有实际验证，本次不重新执行推理。每个程序记录数值容差和标识/掩码/决策的精确检查；既有神经检查使用CUDA，CPU未验证。重放证明检查点可解释随包输出，不等于历史论文运行身份。

## E.3.3　从头训练：提供入口，本次不执行

选择材料树之外的新空目录。入口记录 `NEW_RUN_MANIFEST.json`，不覆盖随包检查点与结果。

```bash
python evaluation_package/evaluation/verification/train_prediction_t1_from_bundle.py \
  --run-dir ../new-runs/forecast-hostcpu-xgboost --target host_cpu --model XGBoost
python evaluation_package/evaluation/verification/train_detection_from_bundle.py \
  --run-dir ../new-runs/fd-ae17 --model AE --seed 17 --skip-test
python evaluation_package/evaluation/verification/train_localization_from_bundle.py \
  --run-dir ../new-runs/known-start-classification
python evaluation_package/evaluation/verification/train_imputation_from_bundle.py \
  --run-dir ../new-runs/offline-imputation
```

预测只读D01—D05拟合/选择，另支持n3_downlink、n6_aggregate及PatchTST、TimeFilter。正常拟合检测支持AE、KAN-AD、TranAD及17/29/43；`--skip-test`在D05后停止。监督RF原入口为 `detection/supervised_rf/code/pilot.py`，配套protocol保留，但未验证独立便携的RF从头训练wrapper，已验证入口是检查点重放。分类训练五变体×三种子后冻结评测；重建先准备掩码、训练M/H×三种子再冻结评测。

既有2026-10-03隔离训练回执仅覆盖host_cpu/XGBoost三种子、AE17、15分类模型及六SAITS模型；不等于所有预测/检测模型全量从头训练已验证。它们属于论文后新运行，不替换原结果。本次未启动任何训练。

绘图入口（在可写副本中运行）为 `python paper_figures/plot_detection.py` 和 `python paper_figures/plot_localization.py`，读取相邻CSV并生成相邻PDF/SVG/PNG。本次从这些程序重绘两张图，在1500像素尺度与当前正文图逐像素完全相同；PDF时间元数据不要求一致。

## E.3.4　范围与访问限制

当前仓库已提供1 s导出、400项字典、5 s任务表及上述评估输入，但未提供重建全部原始采集过程所需的完整日志、业务语料和部署材料；PCAP不在上传范围内。预测、24变量表与平台导出的未确认关系见 [LINEAGE.md](appendix/LINEAGE.md)。选定平台源码位于同仓库的 `codex/platform-data-appendices-20261007` 分支，路径为 `platform/source/`。仓库文件可用不等于论文匿名入口已同步可用。[RUN_GUIDE.md](RUN_GUIDE.md)保留更细命令与既有验证范围。


---

# 来源关系、转换记录与证据边界

本次直接读取当前论文、原实验、core机来源文件和既有记录后整理。没有修改正文，没有启动采集、故障注入、检查点推理或新训练。

| 核查对象 | 本次结果 | 能支持的结论 |
|---|---|---|
| 预测训练来源锁 | 323/323原文件与记录哈希相符 | 当前原执行源码/配置锁仍匹配；不是论文历史绑定 |
| 五组任务权重副本 | 87/87与原目录字节相同：预测54、正常检测9、监督检测3、识别15、SAITS6 | 权重复制完整，不代表历史正文一定来自该执行 |
| 预测输入 | 14个原CSV与gzip副本比较；标识一致替换，时间、缺失标记、顺序保留；浮点CSV往返差异单列 | 原修复输入到审稿输入的关系明确；格式/匿名转换前后独立哈希 |
| core任务来源 | 108/108当前源文件哈希与转换记录相符 | 来源包与当前记录相符；实际私人路径及运行映射在审稿副本外保留 |
| core原5秒观测到匿名副本 | 11张表除run_id外所有字段逐表完全相同 | 标识匿名化未改变这些观测表数值与时间 |
| core导出/覆盖/字典来源 | 15/15原文件当前哈希与记录相符 | 当前7组导出及字典来源成立，历史版本身份仍未确认 |
| 1秒表与5秒表 | 同槽位有精确UTC交集，但CPU/内存/load同时间值不完全相同 | 不能把5秒表称为现有1秒表的直接重采样 |
| 当前论文评测图 | 当前两张PDF与新paper_figures副本相同、与旧审稿副本不同；当前绘图来源已定位，见回执 | 证明当前图版和定位的绘图来源；不认证最初历史实验身份 |

`manifests/core_handoff.csv` 为每个core输入分列原哈希、当前原哈希、core转换哈希和审稿副本哈希。路径以来源包中的逻辑别名表达，避免泄露原始私人运行名；完整实际路径映射仅留本机private审计目录。`prediction_handoff.csv` 列原修复CSV和审稿gzip副本、转换规则及字段往返误差。`input_manifest.csv`补充字段/形状、时间范围、当前程序哈希；这些表通过相对路径连接。中间格式或标识经过变换，哈希不同是预期状态。

预测原CSV经浮点读取/重写时存在少量float64往返差异；本次检查使用包既有标签往返界限rtol=2e−15、atol=2e−8原单位，逐字段最大差异保存在prediction_handoff.csv。没有把这种关系写成逐字节一致。变换后输入的现有检查点重放属于先前2026-10-03记录，本次不重放。

当前1秒表总计611,777行、81字段；400条字典定义含215项metric定义；映射到当前81字段schema的metric字段有39个，各运行其中25为ok、1为replaced、3为snapshot_only、10为capability_missing。它们的计数范围不同，均不能直接证明正文“32项数值指标”的历史口径。当前六页正文不再使用这一未恢复的子计数，历史口径缺口仍显式保留。

原5秒数据构造与论文预测输入有共同运行别名，但列集合、采样尺度和原始测量定义不同。来源程序/协议能说明已保存视图的处理规则，不能证明存在唯一的18变量→24变量→81字段转换链。已有预测前缀修复仅覆盖它声明的四字段，其他测量源的原生采样/在线可用性未重新认证。另从core取回 `task_data/code/build_package.py` 原任务包投影程序，保持原字节、可检查特征投影与索引构造规则；它需要原封存transfer包，不能据此声称从原始遥测生成5秒表已可复现。完整原始采集报告/PCAP不随包提供，不声称从零重新生成整个平台导出。

历史论文身份尚缺共同记录，把论文修订、执行ID、程序版本、输入清单、检查点及当时环境绑定。当前文件hash、数值相同、原机器仍在或检查点重放成功，都不能单独补上这条绑定。D06/D07是已访问后验测试；任何新运行只能作为另外编号的复现验证，不能覆盖历史保存值。
