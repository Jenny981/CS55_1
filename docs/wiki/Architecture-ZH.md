# 架构与工作流程

系统以Final为查询，判断提交材料能提供哪些支持。

1. 输入Final和至少一种证据：Storyboard或Animatic。
2. PDF提取Panel候选，用户修正、确认；视频按时间间隔抽帧并筛选近空白帧。
3. Final分别全局检索Storyboard和Animatic；文字辅助排序，结构提供诊断。
4. 产生自动暂定选择；人工可确认、替换、拒绝或暂缓。
5. 计算支持覆盖、顺序一致性，并与声明的Correspondence作事后对照。
6. 独立提取原文件Provenance和时间戳，计算分项评分。
7. 保存JSON，前端展示原因、候选和评分明细。

React界面通过 `web_server.py` 调用后端；Notebook、CLI与界面共用 `src/cs55_demo/` 模块。前端不独立运行模型或生成后端评分。后台采用单工作线程处理任务，界面轮询进度。

详细模块表、API和流程图见 [Architecture](Architecture.md)。系统是本地应用，默认监听127.0.0.1:8505，不是已配置公开部署和多用户权限的在线平台。

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
