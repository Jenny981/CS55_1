# 安装与运行

需要 Python 3.10 或更新版本。先进入实际含有 `pyproject.toml` 的项目目录，不能假定项目位于用户主目录。

macOS / Linux：
```bash
cd /实际路径/CS55_1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```
Windows PowerShell：
```powershell
cd C:\实际路径\CS55_1
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```
React前端首次使用需要 Node.js 构建：
```bash
cd frontend
npm ci
npm run build
cd ..
python web_server.py
```
打开 http://localhost:8505 。已有构建时只需运行最后一条命令。端口8504是可选的Streamlit版本，不是React服务。

Notebook：运行 `python -m jupyter lab`，打开 `notebooks/CS55_Evidence_System.ipynb`，选择同一虚拟环境的kernel。
CLI：复制 `config.example.json` 为 `config.local.json`，修改路径后运行 `python run_demo.py --config config.local.json`。

首次使用CLIP需要下载模型。FFprobe用于视频元数据；C2PA需要可用验证工具。原生文件选择和路径读取针对服务所在电脑。

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
