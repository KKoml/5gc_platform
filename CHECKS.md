> 本页其他回执描述完整本地核验包；当前发布删去了数据集和平台源码。当前发布检查见 [publication_validation.json](checks/publication_validation.json)，可运行范围见 [DATA_ACCESS.md](DATA_ACCESS.md)。

# 本次检查与实际验证范围

检查对象为独立整理副本、中文平台修订稿、当前原实验和core来源；没有编辑正文、覆盖原实验、启动训练或进行新检查点推理。

| 检查 | 结果/回执 |
|---|---|
| 原审稿候选复制验收 | 原SHA256SUMS逐项通过；private保存原验收日志 |
| 预测保存结果 | 200个MAE、正文9组均值/SD、54输入对照值通过；checks/current/recompute_prediction.log |
| 重建正文表 | 60数值与正文对应；recompute_tables.log |
| 正常拟合检测 | D05阈值及18种子/预算测试行，六种子汇总工作点通过；normal_only_metrics.json、detection_per_seed.csv |
| 监督RF检测 | D05阈值重算及六种子/预算测试行通过，九项指标最大差异0；detection_saved_metrics.json |
| 已知起点识别 | 15模型/种子、60指标通过；classification_recomputed.csv |
| 完整重建统计 | 54预测文件、12,636指标行逐组通过，最大误差0；saved_metrics.json |
| 当前导出与任务schema | 七张81字段1秒表共611,777行、24变量任务表、字典/覆盖/时间对应通过；data_schema_verification.json |
| 原始来源 | 323来源锁、87权重副本通过；local_source_check.json |
| core交接 | 108任务来源、15导出/字典来源hash通过，11观测表除ID外逐字段相同；core_handoff_check.json、core_conversion_check.json |
| 当前论文图/表 | 稳定标签、正文数值与材料核对，当前评测图副本字节比较及新旧图版差异记录；paper_correspondence.json |
| 匿名入口 | 1FEA未经认证访问HTTP403，不能证明文件可读/同步；anonymous_entry.json |

匿名扫描、链接/映射检查和封存前核验见 `checks/package_acceptance.json`；最终压缩包独立解包验收回执为随压缩包另交的 `PACKAGE_ACCEPTANCE.json`，不置于被验收包内。本页的结果不能解释为历史论文运行身份已绑定，也不能解释为所有模型从头训练已验证。既有2026-10-03检查点重放/训练回执保留在verification/results，与本次检查分开。
