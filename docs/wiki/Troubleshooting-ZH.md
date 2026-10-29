# 常见问题与验证

- 找不到requirements.txt：先进入实际项目目录。
- Notebook缺模块：检查kernel是否使用已安装依赖的虚拟环境。
- 页面打不开：检查8505服务及frontend构建，不要同时启动两个占用同端口的服务。
- Panel切错：修正候选框、顺序或手动添加，确认后再匹配。
- 文字为空：检查PDF是否有可提取文字和OCR工具是否可用；不能保证任意语言都能正确识别。
- 大文件卡顿：用本地路径，减少抽帧范围或增大时间间隔。
- 匹配很多但不准：支持覆盖统计已选关系，不等于正确匹配；检查候选并修正。
- C2PA为0：查看是否缺manifest、工具不可用或验证失败，不能据此判断造假。
- 时间分数N/A：检查是否有两侧均可解析的时间字段。
- 时间接近却不扣分：仅文件系统时间接近只提示；它仍可能影响时间顺序分。

在项目目录执行逻辑测试：
```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```
以上环境变量写法适用macOS/Linux；PowerShell先执行 `$env:PYTHONPATH="src"`，再运行 `python -m unittest discover -s tests -v`。

测试验证流程、评分分母及决定规则，不衡量真实检索准确率。真实效果需要独立标注的留出样本，统计Top-1、Top-K、拒绝匹配是否合理和审核时间；调参、人工修正与最终验证应分开。

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
