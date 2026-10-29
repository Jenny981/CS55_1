# 输出、缓存与复现

每次执行在output_dir创建运行目录。结果重新匹配可创建revision，引用已准备材料，保留之前的结果与审核记录。

| 文件 | 内容 |
|---|---|
| config.json / prepared.json | 参数、输入和预处理记录 |
| panel_manifest.json / panel_catalog.json / storyboard_text.json | Panel框、审核和文字关联 |
| final_samples.json / animatic_samples.json | 保留帧索引与原视频时间 |
| result.json / effective_decisions.json | 原始候选、自动决定与覆盖后的决定 |
| matched_list.json | 已选匹配，标明自动或人工来源 |
| unmatched_list.json / pending_list.json | 无支持Final与需要审核的无支持Final |
| final_support.json | 每个Final的路线状态 |
| evidence_scores.json | 人工确认范围和自动加人工范围的评分 |
| correspondence_diagnostics.json | 声明对照及偏离原因 |
| sequence_index_diagnostics.json / triangle_diagnostics.json | 索引异常和补充三角关系 |
| provenance.json / provenance_summary.json / provenance_scores.json | 提取证据及独立评分 |
| timestamp_comparisons.json | 时间戳、分数和扣分明细 |

Clear cache删除本地outputs下的生成记录，包括上传副本、抽帧、Panel与结果；不删除通过路径引用的原文件、代码、依赖和模型权重。运行任务时禁用清理。先导出需要保留的结果。

复现需同时记录输入文件身份、配置、模型、抽帧窗口、Panel顺序、声明与人工覆盖。不要把本地绝对路径、私人材料、虚拟环境和生成缓存提交GitHub。

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
