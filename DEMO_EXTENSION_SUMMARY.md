# CS55_1_demo 扩展说明

## 1. 文档范围

本文说明当前 `CS55_1_demo` 相比原始 Demo 增加或修改了哪些内容、这些内容位于什么文件，以及它们在 Notebook 的第几个单元格中展示。

Notebook 单元格编号按文件中从上到下的物理顺序计算，共 18 个单元格；它不是 Jupyter 显示的 `In [n]` 运行次数。

当前默认数据集已经恢复为内置 `SampleDemo`：

```python
CONFIG_FILE = "config.sample.json"
```

## 2. 原始 Demo 与当前 Demo 的区别

原始 Demo 主要负责内容一致性分析：

```text
Storyboard → Animatic → Final
          → CLIP embeddings
          → sequence-aware matching
          → coherence / confidence / coverage / completeness
          → libevchain evidence-chain JSON
```

当前 Demo 保留上述流程，并为 Storyboard、Animatic、Final 三类资产统一增加 provenance/authenticity evidence：

```text
file_hash
metadata
timestamps
c2pa_manifest
software
project_file
editing_history
```

新增证据不会参与原始内容一致性分数。系统只将证据归纳为四项 `available` / `not_available` 状态，不计算真实性总分：

1. File Integrity
2. C2PA Provenance
3. Source Project Evidence
4. Editing / AI Transparency

`not_available` 表示已经检查但没有发现相应证据，不表示文件为假。

## 3. 当前目录结构

以下结构只列出与运行和本次扩展直接相关的部分：

```text
CS55_1_demo/
├── CS55_1_demo.ipynb                    # 已修改：默认 SampleDemo 及三阶段展示
├── DEMO_EXTENSION_SUMMARY.md            # 新增：本文档
├── run_demo.py                           # 原文件：命令行入口，默认使用 sample
├── config.sample.json                    # 已修改：增加 project_search_root
├── config.sollevante.example.json        # 已修改：增加工程文件搜索配置示例
├── config.sollevante.json                # 新增：真实 SolLevante 相对路径配置
├── requirements.txt                      # 已修改：增加 PDF/视频提取依赖
├── pyproject.toml                        # 已修改：同步运行依赖
│
├── data/
│   └── sample/
│       ├── storyboard.pdf
│       ├── animatic.mp4
│       ├── final.mp4
│       ├── storyboard_panels/
│       ├── animatic_keyframes/
│       └── final_keyframes/
│
├── cache/
│   ├── SampleDemo_embeddings.pt          # 原/运行缓存：内置 sample 特征
│   └── SolLevante_embeddings.pt          # 新增运行产物：真实数据特征缓存
│
├── outputs/
│   ├── final_evidence_chain_result.json  # 运行生成：完整结果与 provenance
│   └── evidence_chain_bundle.json        # 运行生成：libevchain bundle
│
├── src/
│   ├── cs55_demo/
│   │   ├── __init__.py                   # 已修改：导出 provenance 入口
│   │   ├── config.py                     # 已修改：解析 project_search_root
│   │   ├── embeddings.py                 # 原内容层
│   │   ├── matching.py                   # 原内容层
│   │   ├── metrics.py                    # 原内容层
│   │   ├── evchain_integration.py        # 原 libevchain 接入层
│   │   ├── evidence_chain_builder.py     # 已修改：哈希复用及 provenance 扩展
│   │   ├── pipeline_runner.py            # 已修改：主流程接入 provenance
│   │   └── provenance.py                 # 新增：provenance 核心模块
│   │
│   └── libevchain/                       # 保持原始代码不变
│
└── test/
    ├── test_cs55_smoke.py                # 已修改：检查新输出契约
    ├── test_provenance.py                # 新增：provenance 测试
    ├── test_loader.py                     # 原测试
    ├── test_pipeline.py                   # 原测试
    └── test_score.py                      # 原测试
```

## 4. 新增和修改的文件

### 4.1 `src/cs55_demo/provenance.py` — 新增

这是新增功能的核心文件，统一处理三类资产：

```text
storyboard
animatic
final
```

主要功能包括：

- 计算 SHA-256 文件哈希；
- 使用 PyMuPDF 提取 PDF metadata；
- 使用视频工具提取分辨率、时长、帧率、编码器等信息；
- 提取文件系统时间和媒体内部时间；
- 调用 `c2patool` 检查 C2PA manifest；
- 读取 C2PA creation/editing actions；
- 解释 AI-generated、AI-modified、AI disclosure 和修改区域；
- 从 C2PA、PDF、视频容器中提取软件信息；
- 搜索并关联 PSD、AEP、PRPROJ、BLEND 等工程文件；
- 将时间戳、C2PA actions 和工程文件信息组成 editing history；
- 生成四项不评分的 provenance 状态。

统一入口是：

```python
collect_basic_provenance(config)
```

### 4.2 `src/cs55_demo/pipeline_runner.py` — 修改

在原始内容分析完成后执行：

```python
provenance = collect_basic_provenance(config)
provenance_authenticity_evidence = simplify_provenance_indicators(provenance)
```

然后将两部分内容写入最终结果：

```text
provenance
provenance_authenticity_evidence
```

原始内容指标仍然保存在：

```text
final_score
chain_metrics
stage_metrics
coverage_breakdown
```

### 4.3 `src/cs55_demo/evidence_chain_builder.py` — 修改

保留原始 Evidence Chain 的必要字段：

```text
hash_method
final_artefact_hash
artefacts
```

同时完成：

- 将 provenance 加入 bundle；
- 复用 Animatic 和 Final 已经计算的 SHA-256；
- 避免对大型视频重复计算哈希。

### 4.4 `src/cs55_demo/config.py` — 修改

新增对以下配置的支持：

```json
"project_search_root": "data/sample"
```

所有相对路径都按配置文件所在目录解析，因此 Windows 和 macOS 可以使用同一套目录结构。

### 4.5 `src/cs55_demo/__init__.py` — 修改

导出 `collect_basic_provenance`，允许 Notebook 和其他 Python 模块从 `cs55_demo` 统一调用。

### 4.6 配置文件 — 修改或新增

`config.sample.json`：

- 当前默认配置；
- 使用 `data/sample` 内置文件；
- 增加 `project_search_root`。

`config.sollevante.example.json`：

- 提供真实数据配置模板；
- 增加工程文件搜索路径示例。

`config.sollevante.json`：

- 保存本机 SolLevante 的相对路径配置；
- 当前不作为 Notebook 默认配置。

### 4.7 依赖文件 — 修改

`requirements.txt` 和 `pyproject.toml` 增加：

```text
pymupdf>=1.24
opencv-python>=4.10
```

它们分别用于 PDF 和视频信息提取。C2PA 检查还会使用系统中的 `c2patool`；如果没有安装，结果会明确显示工具不可用，而不会伪造证据。

### 4.8 测试文件 — 新增或修改

`test/test_provenance.py` 检查：

- SHA-256；
- metadata；
- timestamps；
- C2PA 解析；
- software；
- project files；
- editing history；
- 四项指标；
- JSON 可序列化；
- 大文件哈希复用。

`test/test_cs55_smoke.py` 检查：

- 原始 Evidence Chain 契约；
- provenance 三阶段结构；
- 四项简化状态；
- result 与 bundle 一致性。

当前共 22 项测试，全部通过。

## 5. Notebook 单元格对应表

| 单元格 | 类型 | 标题或入口 | 对应文件/数据 | 作用及新增内容 |
|---:|---|---|---|---|
| 1 | Markdown | `# CS55_1_demo` | 整体系统 | 说明 Storyboard → Animatic → Final 的原始流程。 |
| 2 | Markdown | `## 1. Choose dataset` | 配置文件 | 提示选择数据集。 |
| 3 | Code | `CONFIG_FILE` | `config.sample.json` | 已改回内置 SampleDemo；如需真实数据可手动换成 `config.sollevante.json`。 |
| 4 | Markdown | `## 2. Load the packaged CS55-1 system` | `src/` | 说明加载项目代码。 |
| 5 | Code | 加载系统 | `src/cs55_demo/__init__.py`、`config.py` | 设置 `src` 路径，调用 `load_config()`，打印数据集名称。 |
| 6 | Markdown | `## 3. Run` | 主流水线 | 说明即将运行完整分析。 |
| 7 | Code | `run_full_pipeline()` | `pipeline_runner.py`、`provenance.py`、`evidence_chain_builder.py`、`cache/SampleDemo_embeddings.pt` | 运行原内容层和新增 provenance 层，返回 `result` 与 `bundle`。 |
| 8 | Markdown | `## 4. Content consistency results` | 原内容层 | 强调内容一致性与真实性证据不是同一概念。 |
| 9 | Code | 内容结果表 | `result["chain_metrics"]`、`stage_metrics`、`evidence_chain` | 展示 coherence、confidence、coverage、completeness、两阶段相似度和证据链数量。 |
| 10 | Markdown | `## 5. Four provenance indicators — no score` | 新证据层 | 说明四项指标只表示证据可用性，不评分。 |
| 11 | Code | 四项指标总表 | `result["provenance_authenticity_evidence"]` | 同时展示 Storyboard、Animatic、Final 的四项 `available` / `not_available` 状态。 |
| 12 | Markdown | `## 6. Indicator inspection details` | 新证据层 | 说明下面将展示三个阶段的判断理由和检查过程。 |
| 13 | Code | 三阶段指标检查 | `result["provenance"][asset]["provenance_summary"]` | 已改为循环展示 Storyboard、Animatic、Final；显示每项原因、checks、source、warnings 和 conflicts。 |
| 14 | Markdown | `## 7. Detailed provenance evidence` | 新证据层 | 说明详细显示 C2PA、软件、工程文件和编辑历史。 |
| 15 | Code | 三阶段详细证据 | `provenance.py` 的输出 | 已改为循环展示 Storyboard、Animatic、Final 的 C2PA、software、project file、editing history。 |
| 16 | Markdown | `## 8. Save JSON outputs` | 输出模块 | 说明保存最终 JSON。 |
| 17 | Code | `save_outputs()` | `outputs/final_evidence_chain_result.json`、`outputs/evidence_chain_bundle.json` | 保存完整结果及 Evidence Chain Bundle。 |
| 18 | Markdown | `## 9. Expected SampleDemo reference (rounded)` | SampleDemo 参考结果 | 已由 SolLevante 参考值改为 SampleDemo 参考值。 |

## 6. 三阶段 provenance 输出结构

最终结果中的三个阶段结构一致：

```json
{
  "provenance": {
    "storyboard": {
      "file_hash": {},
      "metadata": {},
      "timestamps": {},
      "c2pa_manifest": {},
      "software": {},
      "project_file": {},
      "editing_history": {},
      "provenance_summary": {}
    },
    "animatic": {
      "file_hash": {},
      "metadata": {},
      "timestamps": {},
      "c2pa_manifest": {},
      "software": {},
      "project_file": {},
      "editing_history": {},
      "provenance_summary": {}
    },
    "final": {
      "file_hash": {},
      "metadata": {},
      "timestamps": {},
      "c2pa_manifest": {},
      "software": {},
      "project_file": {},
      "editing_history": {},
      "provenance_summary": {}
    }
  }
}
```

因此 provenance 并不是只处理 Storyboard。三个阶段使用相同字段，只是实际可发现的证据可能不同。

## 7. 当前 SampleDemo 运行结果

当前参考结果为：

```text
Chain Coherence:              0.9801
Confidence:                   0.9738
Evidence Coverage:            0.2500
Completeness:                 0.6250
Storyboard → Animatic:        0.9670
Animatic → Final:             0.9870
EvidenceChain artefacts:      6
Evidence relationships:       5
```

Sample 文件没有附带 C2PA manifest 和真实工程源文件，因此这两类指标会显示 `not_available`。但三个阶段均已执行哈希、metadata、timestamps、C2PA、software、project file 和 editing history 检查。

## 8. 输出文件

`outputs/final_evidence_chain_result.json` 包含：

```text
dataset_name
evidence_chain
final_score
provenance
provenance_authenticity_evidence
chain_metrics
stage_metrics
coverage_breakdown
```

`outputs/evidence_chain_bundle.json` 保留原格式：

```text
hash_method
final_artefact_hash
artefacts
```

并追加：

```text
provenance
provenance_authenticity_evidence
```

项目自带的 `libevchain` 只读取原有必要字段，并允许存在额外顶层字段，因此保持兼容。

## 9. 未修改的核心部分

以下内容保持原始逻辑：

- `src/libevchain/`；
- CLIP embedding 流程；
- sequence-aware matching；
- coherence、confidence、coverage、completeness 的计算方法；
- Storyboard → Animatic 和 Animatic → Final 的相似度算法。

provenance 是在原始内容层运行结果之上增加的证据描述，不会改变原始内容计算。

## 10. 运行方式

macOS/Linux（项目放在 Downloads 时）：

```bash
cd ~/Downloads/CS55_1_demo
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_demo.py --config config.sample.json
```

如果项目不在 Downloads，请将第一行替换为实际位置，例如：

```bash
cd "/path/to/CS55_1_demo"
```

不要把原电脑创建的 `.venv` 直接交给其他 Mac 或 Windows 电脑；接收者应使用上面的 `python3 -m venv .venv` 在自己的电脑上重新创建环境。项目配置和 SampleDemo 数据使用相对路径，因此只要保留整个 `CS55_1_demo` 文件夹结构，不需要填写原作者的用户名或个人绝对路径。

Windows PowerShell：

```powershell
cd "C:\你的路径\CS55_1_demo"
py -3.11 -m venv .venv
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python run_demo.py --config config.sample.json
```

运行结束后会更新 `outputs/` 中的两个 JSON 文件。
