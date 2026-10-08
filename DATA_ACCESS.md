# 数据与平台代码访问范围

用户确认本次 GitHub 暂不上传任何数据集；网盘下载链接、访问方式及匿名可用性待补充。平台源码快照暂不公开。实验复现代码、模型、配置、保存结果及输入合同已纳入发布副本。

## 清单与恢复目录

- [实际输入合同](manifests/input_manifest.csv)：完整本地核验的489项输入及形状、字段、时间、处理规则。部分为模型尺度或派生缓存，随数据输入一起留待补充。
- [未发布文件](manifests/omitted_files.csv)：逐文件区分待网盘数据与暂不发布平台代码，记录原副本路径、字节数和SHA-256。
- [core交接](manifests/core_handoff.csv)、[预测转换交接](manifests/prediction_handoff.csv)：保留转换前后各自哈希和差异，不要求格式不同文件哈希相同。

网盘数据提供后，在本材料根目录恢复 omitted_files.csv 中 dataset_pending_external_download 项的相对路径，并逐文件验证其SHA-256。平台源码项不能作为数据恢复清单；其中原始导出程序仅用于核验来源描述，不属于当前复现代码的已发布入口。完整本地包封存不受本次发布筛选影响。原始PCAP等未纳入完整本地包的记录仍仅清单化，不能用本清单证明其已打包。

## 当前可运行范围

表级重算入口 `python evaluation_package/evaluation/verify_paper_tables.py` 读取已发布的指标表；绘图入口 `python paper_figures/plot_detection.py`、`python paper_figures/plot_localization.py` 读取相邻已发布CSV。它们不需要模型推理或数据集。

逐预测保存值检查、全部检测/重建指标重新计算、数据合同校验、检查点推理和从头训练须按各程序依赖补齐网盘输入后运行。分类逐预测重算是否独立可运行仍以脚本实际依赖为准；不将部分运行成功泛化为完整复现。旧回执证明完整本地包的已执行范围，不证明当前删去输入的发布树可直接运行所有命令。

所有数据相关入口和原输入路径继续保留，供恢复后执行。任何目录中旧的完整包文件清单、Data/Code Availability草稿、旧README与2026-10-03回执必须结合本访问范围解释，不能将旧完成状态理解为网盘已公开或匿名镜像已同步。
