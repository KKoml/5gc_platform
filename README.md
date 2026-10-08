# D-GATE 中文实验附录与审稿材料

本次对应中文平台修订稿；附录、正文图表映射、输入/来源清单和复现范围已在独立副本整理。原论文及原实验不改。本材料为已核验实验的发布副本，包含实验代码、配置、模型与结果；平台源码及所有数据集暂不上传，网盘地址待补。发布状态见 [PUBLICATION_STATUS.md](PUBLICATION_STATUS.md)。

- [完整中文附录](APPENDIX.md)：D.3数据构造、E.1模型与参数、E.2完整结果、E.3复现指南。
- [正文图表对应表](PAPER_RESULT_MAP.md)：从正文标签定位输入、配置、记录、输出和程序。
- [实际输入清单](manifests/input_manifest.csv)、[core转换交接](manifests/core_handoff.csv)、[预测输入交接](manifests/prediction_handoff.csv)。
- [逐拟合记录](manifests/fit_records.csv)、[完整结果文件索引](manifests/result_files.csv)、[逐目标预测选择](manifests/selected_prediction_models.csv)。
- [当前检查摘要](CHECKS.md)、[当前核验回执](checks/current)、[来源边界](appendix/LINEAGE.md)。

正文匿名入口以用户指定的1FEA为准；匿名入口不是Git推送地址。先执行 `sha256sum -c SHA256SUMS.txt`，再在可写复制目录执行 [复现指南](appendix/E3_reproduction.md)。本次不启动新训练/推理；旧检查点/训练回执仅作为2026-10-03的已有证据保留。随包旧英文README/运行指南描述旧候选状态，论文版本和发布状态以本README及PUBLICATION_STATUS为准。

## 当前发布范围

请先阅读 [数据访问与可运行范围](DATA_ACCESS.md)。[未发布文件清单](manifests/omitted_files.csv) 区分待网盘输入和暂不公开的平台源码；下述结构描述完整本地包，当前发布树受该清单约束。

## 完整本地包结构

**Reviewed publication copy.** Public repository publication and anonymous-entry readability are separate checks. Original paper, source experiment files, and analytical data values were left unchanged. One redundant raw-source path annotation was removed from the reviewer copy and documented in the data-machine completion report.

## Contents

- `data_machine/` — task-ready D01–D07 data, the full 1 s exports, coverage reports, current 400-entry field dictionary, and selected platform source snapshot (withheld from this publication).
- `evaluation_package/` — code, configurations, checkpoints, saved outputs, result checks, and training/replay helpers for prediction, detection, known-start classification, and offline imputation.
- `prediction_inputs/` — withheld pending external data download; complete local T1 history windows and target aggregates used to reconstruct forecasting tensors without the omitted multi-gigabyte cache.
- `RUN_GUIDE.md` — fresh-extraction commands for saved-result recomputation, checkpoint inference, data checks, and separately numbered retraining.
- `evaluation_package/docs/ASSEMBLY_REPORT.md` — paper output mapping and current verification status.
- `evaluation_package/docs/DATA_CODE_AVAILABILITY_DRAFT.md` — statement draft with an access-route placeholder.

`SHA256SUMS.txt` lists every package file except itself. The SHA-256 sidecar is delivered beside the `.tar.gz` archive and is not inside this directory. The private source mapping and audit stay outside this package.

## Evidence limits

The checkpoint replays confirm that the included later run artifacts reproduce their included saved outputs. They do not identify those runs as the historical source of the paper. D06/D07 were previously accessed and are post-hoc, not blind. The current 81-column exports and 400-entry field dictionary cannot yet be tied to the historical field version described in the paper. The 5 s task tables are not shown to be a simple resampling of the 1 s exports.

The current manuscript's 32 numeric-indicator statement does not map exactly to the current 81-column view: the current dictionary marks 39 metric-role field definitions present in the schema, with a subset unavailable or non-current for every run. See the executed schema report and dataset guide.
