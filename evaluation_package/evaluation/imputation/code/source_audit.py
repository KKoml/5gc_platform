from experiment import *
dictionary=pd.read_csv(PKG/'metadata/EXPERIMENT_KPI_DICTIONARY.csv');d=dictionary[dictionary.feature.isin(F)].copy();assert set(d.feature)==set(F);d['used_as_input']=True;d['mask_group']=d.feature.map(lambda f:'Silver_interface_6' if f.startswith('core-if-upfgtp-silver__') else ('host_local_4' if f.startswith('core-host-local__') else 'auxiliary_NF'));d.to_csv(ROOT/'metadata/source_group_ledger.csv',index=False)
a=pd.read_csv(ROOT/'metadata/alias_audit.csv');assert not a.exact_equal.any();assert not ((~a.same_group)&(a.linear_max_error<1e-8)).any()
role=pd.read_csv(ROOT/'metadata/runs.csv');q=[]
for r in role.itertuples():
    ep=pd.read_csv(PKG/r.data_path/'episodes.csv');q.append(dict(slot=r.slot,episodes=len(ep),quality_counts=ep.quality.value_counts().to_dict(),label_basis_counts=ep.label_basis.value_counts().to_dict()))
dump('metadata/event_label_quality.json',q)
(ROOT/'metadata/SOURCE_AUDIT_ZH.md').write_text('''# 采集源及直接反推检查\n24列均来自封存白名单与KPI字典。Silver接口比特率、包率、drop/error六列统一遮蔽；host CPU、内存占比、loadavg、swap四列统一遮蔽。剩余字段为NF资源及Ready观测，白名单不含第二接口比特率别名、累计收发字节计数、宿主机CPU分项或原始累计CPU计数。未引入时间、run ID、事件标签、源年龄作为模型输入。\n训练原始行逐一检查三个目标与其余23列：无完全相同别名，无组外精确单列仿射反推；这不是对任意非线性代数关系的形式证明。采集字典来源与派生关系的可见边界为封存材料。详见source_group_ledger.csv及alias_audit.csv。\n接口源年龄在训练数据中最大约124–130秒，NF更新慢于5秒网格；人工遮蔽相邻点时可能仍有重复观测可见，允许在本任务中利用，但不能据此认证每5秒物理变化。重复值统计和源年龄另存csv。\n事件标签质量与依据原样统计，不升级为人工核实真值。恢复层仅使用封存end_exclusion恢复排除区间；未知或未记录干预不能从正常背景层中排除。\n''')
print('SOURCE AUDIT PASS')
