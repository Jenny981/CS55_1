# 材料、Panel审核与配置

Final必需；Storyboard和Animatic至少提交一种。两种都存在时有Final→Storyboard、Final→Animatic两条主路线，以及Animatic→Storyboard补充路线。

在Materials上传或选择本机路径。大型视频优先路径读取。Final和Animatic分别设置开始、结束时间与抽帧间隔；保留原视频时间轴，不把截取起点重置为零。

Panel提取仅产生建议：检查页面，接受或排除区域，修改像素边界和顺序，也可补框。React界面要求确认后再匹配。确认后重新裁剪并关联文字，Panel索引遵循已确认页序和框序。一个文字组可以支持多个Panel，不必强制一段文字只对应一图。

Correspondence是提交者声明的预期关系。Final时间区间采用左闭右开 `[start,end)`；Storyboard指定Panel索引，Animatic指定证据时间区间。重叠声明取并集。声明不限制候选搜索，匹配后才比较；未覆盖的Final仍可检索，但符合度标为不可评估。

配置路径相对配置文件解析。默认每2秒抽帧、候选数5、视觉最低相似度0.25；这些是可调整启发式值，不是准确率保证。完整示例和所有字段见 [Materials and configuration](Materials-and-Configuration.md)。

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
