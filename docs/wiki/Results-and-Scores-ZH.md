# 评分与结果解释

## 5 视觉支持覆盖率

V 是至少获得一条路线支持的 Final 数占全部保留 Final 数的比例。同一 Final 被两条路线支持只计一次。例如 100 张中 70 张有选中证据，V=70%。

该分数不是 CLIP 平均值或匹配准确率。自动选错的 pair 在被纠正前仍会贡献覆盖率。

## 6 顺序一致性与异常

按 Final 顺序排列已选证据编号，并检查所有两两组合。后一个证据编号较大为 concordant，较小为 discordant，相同为 tie。重复编号不进入分母；路线至少三个已选匹配且有非重复比较才评分。

项目级分数汇总符合条件路线的 C 与 D，而不是简单平均路线百分比。例如一条路线 C=14、D=0，另一条 C=0、D=5，项目结果为 14/19=73.68%。

系统另记录相邻编号的 backtrack、repeat、forward_gap 和 forward。回退可能来自证据乱序或视觉匹配错误；跳号可能来自采样和剪辑，不能自动证明缺失。

代码还输出覆盖率 V 与顺序 Q 的调和平均 overall_evidence_score，即两者可用时 2VQ/(V+Q)；两者均为 0 时取 0。当前页面主要分别展示各项。

## 7 Correspondence 对照

correspondence 是用户声明的预期关系，检索完成后再检查。例如 Final [10,20) 秒对应 panel 5–8；区间包含开始、不包含结束。

Conforming 表示选中证据属于声明集合；Outside baseline 表示选中范围外证据；Expected not observed 表示有声明但没选出证据；Undeclared 表示没有覆盖该 Final 时间的声明。Undeclared 不进符合率分母。

同一 Final 在两条路线有声明时计两项。Expected evidence coverage 则计算声明证据中曾被选中过的唯一编号比例，当前实现即使在错误时间被选中也计入，需要与符合率一起解读。

逐帧记录包括实际选择、预期编号、声明 ID、偏离状态、原因以及所选证据是否属于其他声明。只有声明经过独立核验后，才适合进一步作为准确率评估基准。

## 8 Provenance 提取与独立评分

对各原始材料提取 SHA 256、元数据、内嵌与文件系统时间、C2PA、软件、项目线索和编辑事件。视频元数据优先 FFprobe，必要时回退 OpenCV。C2PA 需要可用的验证库或工具。

各指标按已得分除以适用最高分乘 100。没有 C2PA manifest 时该指标总分归零，不能因未报告错误而获得验证分。四项不相加或平均成统一 provenance 总分。

哈希完成只建立当前文件指纹，没有可信历史哈希对照不能证明从未修改。软件标识、时间和历史主要是可观察线索。低分表示支持材料有限，不直接证明伪造。

| 指标 | 分值组成 |
| --- | --- |
| File integrity | SHA 256 完成 70；成功读取字节 30 |
| C2PA provenance | manifest 20；有效签名 35；凭证信任 20；无验证错误 15；warnings 条件 10 |
| Source project | 候选存在 25；项目哈希 25；关系验证 50 |
| Editing AI transparency | actions、声明历史、时间、软件、元数据各 20 |

## 9 Timestamp 评分

分别比较 Storyboard → Final 与 Animatic → Final。双方都能解析才可比较。权重为内嵌创建 35%、内嵌修改 30%、文件系统创建 20%、文件系统修改 15%。缺失字段降低可用权重。

单项顺序分：Evidence 不晚于 Final 得 100；晚不超过 24 小时得 70；晚 1–7 天得 25；晚超过 7 天得 0。A 为可比较权重比例 0–1，C 为可比较项的加权顺序分 0–100。

基础分为 A×(30+0.7C)。内嵌创建时间领先 Final 不超过 1 小时扣 15，超过 1 至 6 小时扣 10，超过 6 至 24 小时扣 5。内嵌修改时间绝对间隔小于 1 小时扣 5，1–6 小时扣 2。合计最多扣 15。

仅文件系统时间接近只报告不扣分；复制、上传、下载或批量导出可能改变这些值。完全不可比较时为 N/A。项目分数取可用关系分数平均值，并另记录三阶段顺序或快速生成信号。

这些权重与区间是当前设计的启发式评分，尚需独立样本验证。内嵌元数据也可能是自声明信息；时间接近只能提示复核，不能证明材料无效。

## 10 结果字段的得分与缺失如何解释

passed 或 Satisfied 表示某一具体检查条件被满足，不代表整个文件真实。points_awarded 是该项实得分，maximum_points 是该项最高分；reason、observed_value、source 和 explanation 应一起用于追溯。C2PA 没有 manifest 时，整个 C2PA 指标门控为 0，即使某些清洁度检查表面为真也不能获得该指标得分。

## 12 如何展示异常而不夸大结论

建议每个重点异常展示 Final、实际选中证据、预期证据或区间、候选排名、决策来源、具体偏离原因。将结论分成已观察事实、可能原因和待核查内容。例如：观察到范围外选择；可能是检索误配、声明配置问题或实际剪辑差异；尚未确认原因。

重复可能来自同一镜头持续多帧；跳号可能来自均匀抽帧或未使用的分镜；回退可能来自重排或误匹配。局部检查可定位问题，但不能仅从编号证明缺失或篡改。三方补充关系存在也不能自动证明三个匹配都正确。

## Formula reference
```text
Visual coverage = supported distinct Final samples / all retained Final samples * 100
Sequence = concordant / (concordant + discordant) * 100
Correspondence = conforming / declared evaluable Final-route items * 100
Timestamp = max(0, A * (30 + 0.7 * C) - D)
A: comparable timestamp weight, 0..1; C: weighted chronology, 0..100
D: additional proximity deduction, capped at 15
```

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
