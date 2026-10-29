# Installation and operation

Requires Python 3.10 or later. Run commands from the actual project directory containing `pyproject.toml`.

macOS/Linux:

```bash
cd CS55_1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m jupyter lab
```

Windows PowerShell:

```powershell
cd CS55_1
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m jupyter lab
```

Open `notebooks/CS55_Evidence_System.ipynb`, or run:

```bash
python run_demo.py --config config.local.json
```

## Web interfaces
### React, shadcn/ui and Radix frontend

The new UI lives in `frontend/`. It uses official shadcn components with Radix primitives and a local Starlette API in `web_server.py`. Preparation, matching, review overrides and provenance call the same Python modules as the notebook. Jobs run in a single background worker with polled progress; images are resized for display. The interface is English.

Build once and launch the local server:

```bash
cd frontend
npm ci
npm run build
cd ..
python web_server.py
```

Open `http://localhost:8505`. The built frontend and API are served together. Node.js is needed for building; only Python is needed to serve an existing build. For frontend development, run `npm run dev` in a second terminal; Vite proxies API calls to port 8505.

Use **Materials** to upload files, enter paths, or open the macOS native file chooser. **Panel review** shows every detected PDF region before matching: users can keep or exclude candidates, edit pixel boundaries and order, or add manual boxes. **Correspondence** offers first/last reviewed-panel selectors, endpoint previews and a panel library. **Matching workspace** provides a Final frame browser, ranked evidence cards, semantic reranking indicators and optional corrections. **Assessment** shows metrics and JSON downloads. **Provenance** exposes individual rubric checks and timestamp comparisons.

The sidebar **Clear cache** action reports the current generated-output size and opens a destructive-action confirmation dialog. It removes only children of the local `outputs/` directory: generated runs, sampled frames, extracted panels, browser-upload copies and JSON results. It is disabled while processing is active. It does not remove source files referenced by path, code, dependencies, virtual environments or downloaded model weights.

The server binds to loopback. Local paths and native selection refer to the server machine. Uploaded material is streamed to the local `outputs/` directory. Source ZIPs include frontend code and the npm lockfile, excluding `node_modules` and generated builds.

### Streamlit frontend

The frontend is included in the same directory and calls the shared system modules directly:

```bash
python -m streamlit run streamlit_app.py --server.port 8504
```

Open `http://localhost:8504`. Choose **Materials**, prepare files using local paths or uploads, then open **Panels and ranges** to declare correspondence intervals. **Matching** runs the shared algorithm. **Review** allows optional candidate corrections, and **Results** shows separate automatic/human metrics, provenance details, and JSON downloads. Existing runs can be reopened from the sidebar. Local paths avoid browser upload limits and refer to the server machine.

Choose first and last Storyboard panels to add a batch correspondence rule. Changing ranges or rerunning matching after results exist creates a new result revision and reuses extracted material. Earlier results and reviews are preserved. Human review overrides remain editable. The application uses bounded thumbnail caching and does not retain a model in the global UI cache.

Copy `config.example.json` to `config.local.json` and set your material paths. Paths are resolved relative to the configuration file. FFprobe is recommended for video metadata. C2PA can use c2patool or the optional c2pa-python dependency. CLIP downloads its model on first use. Optional macOS Vision OCR requires the existing compiled `vision_ocr` helper; without it, PDF embedded text is used and missing OCR is reported. No native binary or credentials are bundled.

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
