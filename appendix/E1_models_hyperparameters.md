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
