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
