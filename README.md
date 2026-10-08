# D-GATE 论文配套材料

当前中文六页稿（含参考文献）引用的附录为 **A–D**，入口是 [正文配套附录](manuscript_supplement/README.md)。其中包括平台五项功能及开发内容对应表、网络与实验配置、400条字段定义、真实数据小样例、任务输入和模型超参数。

- [附录 A–D](manuscript_supplement/README.md)：与当前正文编号对应。
- [完整字段字典](manuscript_supplement/data/field_dictionary.csv)、[81列1 s样例](manuscript_supplement/data/timeseries_1s_sample.csv)、[5 s核心网样例](manuscript_supplement/data/core_features_5s_sample.csv)。
- [正文图表对应表](PAPER_RESULT_MAP.md)：使用稳定标签，图号已按当前五图四表更新。
- [详细实验附录](APPENDIX.md)：保留原D.3/E.1–E.3编号，提供任务构造、模型参数、完整结果和复现说明；与当前A–D的对应见正文附录D.4。
- [数据访问与可运行范围](DATA_ACCESS.md)、[发布状态](PUBLICATION_STATUS.md)、[检查摘要](CHECKS.md)。
- [当前正文指纹](manifests/compressed_manuscript.json)、[输入合同](manifests/input_manifest.csv)、[拟合记录](manifests/fit_records.csv)、[结果索引](manifests/result_files.csv)。

## 发布内容与访问

仓库包含实验复现代码、已有模型、配置、保存结果、来源清单，以及说明数据格式的小样例。完整数据集及平台源码尚未发布；完整数据下载入口待补充。源码目录名称可用于解释开发工作，但不代表这些源码已可下载。

匿名审稿入口为 https://anonymous.4open.science/r/5gc_platform-1FEA/ 。源仓库更新与匿名镜像同步分别核验；当前匿名端仅列出旧readme，文件下载返回 GitHub App 访问权限错误，尚不能从该入口访问本版附录。详见发布状态。

## 验证与来源边界

`SHA256SUMS.txt` 覆盖当前发布树的全部有效载荷文件（不含其自身）；`manifests/file_inventory.csv` 不含自身及根哈希清单。先验证文件哈希，再依据复现指南在可写副本中执行需要的检查。当前修订没有重训模型或运行检查点推理，原结果、模型、输入合同和历史回执保留不变。

D06/D07此前已被访问，属于固定划分下的后验评估。分类依赖已知注入起点，缺失重建使用人工遮蔽并允许缺口前后观测。已有保存结果重算及检查点回放不能代替历史论文运行身份认证。

当前1 s导出表为611,777行、81列，字典共400条定义，其中215条为metric。旧稿的“32项数值指标”历史子计数尚未恢复，当前六页稿不再使用该子计数；附录保留缺口，不用39个metric角色字段替换为39项有效指标。1 s导出与5 s任务表之间也不表述为简单降采样关系。

`manifests/paper_baseline.json` 及旧回执对应先前实验材料基线；当前正文指纹单独保存，两者不互相覆盖。
