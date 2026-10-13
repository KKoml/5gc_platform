# Appendix E.3　复现指南

**数据与运行入口：** 本仓库已包含[平台时间序列表与5 s任务数据](../data_machine/dataset/README.md)、[预测历史与目标](../prediction_inputs/README.md)、[预测索引](../evaluation_package/evaluation/prediction/outputs/indices/)、[分类窗口](../evaluation_package/evaluation/localization/cache/)，以及插补的[窗口数据](../evaluation_package/evaluation/imputation/data/)、[人工掩码](../evaluation_package/evaluation/imputation/masks/)和[训练尺度](../evaluation_package/evaluation/imputation/metadata/scales.npz)。运行前仍需安装下述软件依赖。PCAP明确排除，完整原始采集日志和业务输入语料未随包提供；具体范围见[数据访问说明](../DATA_ACCESS.md)。

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

当前仓库已提供1 s导出、400项字典、5 s任务表及上述评估输入，但未提供重建全部原始采集过程所需的完整日志、业务语料和部署材料；PCAP不在上传范围内。预测、24变量表与平台导出的未确认关系见 [LINEAGE.md](LINEAGE.md)。选定平台源码位于同仓库的 `codex/platform-data-appendices-20261007` 分支，路径为 `platform/source/`。仓库文件可用不等于论文匿名入口已同步可用。[RUN_GUIDE.md](../RUN_GUIDE.md)保留更细命令与既有验证范围。
