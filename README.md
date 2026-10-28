# CS55 Evidence System

The notebook and CLI use the same Python modules. The system extracts usable Storyboard panels automatically, samples videos by time, searches all extracted evidence, and compares the resulting pairs with submitter-declared correspondence before optional human review.

## External testing

See the [external testing guide](docs/EXTERNAL_TESTING.md) for setup, suggested red-team cases, metric interpretation and issue reporting.

## Install and run

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

## Frontend

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

## Notebook steps

1. Locate the project and load configuration.
2. Generate panel candidates and sample videos.
3. Review every Storyboard page and confirm the panel boundaries retained for matching.
4. Inspect the reviewed panel catalog and optionally declare expected Final correspondence ranges.
5. Run global candidate retrieval and provisional Top-1 decisions.
6. Inspect selected, uncertain, and insufficient-evidence lists.
7. Optionally provide human overrides.
8. Inspect independent provenance scores and timestamp comparisons.

Automatic extraction produces suggestions only. Storyboard matching is blocked in the React UI until the user confirms the panel review. The review can accept or exclude proposals, change their order and pixel boundaries, and add manual boxes. Confirmation re-crops the panels and re-extracts descriptions. The resulting `panel_catalog.json` and `panel_manifest.json` preserve the review trail; final panel IDs follow the confirmed page and order sequence.

## Declared correspondence ranges

Ranges are submitter-provided expected relationships, not automatically verified Ground Truth and not retrieval constraints. Ranges are half-open `[start, end)` in seconds on the original video timeline, even when video sampling starts later.

Storyboard:

```json
{"evidence_type":"storyboard", "panel_indices":[1,2,3],
 "final_start_sec":45, "final_end_sec":52}
```

Animatic:

```json
{"evidence_type":"animatic", "evidence_start_sec":10, "evidence_end_sec":18,
 "final_start_sec":45, "final_end_sec":52}
```

Overlapping declarations form a union for post-retrieval comparison. A Final outside all declarations can still receive a global visual candidate, but its correspondence conformance is marked not evaluable. A selected candidate outside the active declaration is recorded as `outside_declared_evidence_set` rather than silently excluded.

## Selection algorithm

For each retained Final frame, rank CLIP visual similarities across all extracted evidence for that route. Text descriptions are encoded once per text group and may support multiple panels. For the top five visual candidates within 0.05 of the best visual similarity, text may change the order using reciprocal ranks: `1 / visual_rank + 1.25 / text_group_rank`. The text contribution is enabled only when multiple distinct text groups are present. Scores are used to order candidates, not as calibrated confidence values. Valid local structure and neighbouring candidates remain supporting diagnostics. No monotonic matching path is imposed, so evidence-index regressions remain observable.

Default `range_top1` (shown as Global Top-1 in the UI for backward configuration compatibility) automatically selects the global best candidate after optional text reranking, provided minimum visual similarity is met. The selected pair is then compared with active correspondence declarations. Small score margins or missing auxiliary evidence do not require human approval in this mode. Continuous reuse is recorded as a warning. Optional `strict` mode additionally checks Top-1/Top-2 separation, auxiliary support and consecutive reuse, sending uncertainty to review. Current thresholds and rank weights are configurable heuristics and have not been calibrated against labeled validation data. More automatic acceptance does not demonstrate higher matching accuracy.

Animatic-to-Storyboard candidates provide supplementary context. They do not override the primary Final relationships or automatically reject triangle conflicts. Text and structure scores are recorded separately and are not added to raw CLIP scores.

## Outputs

Each execution creates a fresh directory under `output_dir`:

- `prepared.json`, `config.json`: reproducible inputs and preparation records.
- `panel_manifest.json`, `panel_catalog.json`, `storyboard_text.json`: candidate boundaries, human panel decisions and refreshed shared text mapping.
- `final_samples.json`, `animatic_samples.json`: retained sample indices and original-video timestamps.
- `correspondence_diagnostics.json`: global selected pairs compared with the declared baseline, including conformance, outside-baseline, missing-support and expected-evidence coverage observations.
- `result.json`: all retained candidates, automatic decisions, supplementary relationships.
- `effective_decisions.json`: automatic decisions plus optional human overrides.
- `matched_list.json`: provisional and human matches, explicitly tagged by source.
- `unmatched_list.json`: Final frames with insufficient evidence on all available routes.
- `pending_list.json`: unsupported Final frames with at least one uncertain route.
- `final_support.json`: all retained Final frames and their route-level decisions.
- `evidence_scores.json`: human-confirmed scores and combined provisional/human scores, reported separately. Coverage includes every retained sampled Final frame, including those without candidates. Sequence scores compare all eligible pairs, excluding ties, and require three selected matches.
- `sequence_index_diagnostics.json`: adjacent backtracks, repeats, forward gaps, and pairwise inversions for each decision source scope.
- `triangle_diagnostics.json`: supplementary support for the selected Final/Animatic/Storyboard combinations; it does not change acceptance.
- `provenance.json`, `provenance_summary.json`, `provenance_scores.json`, `timestamp_comparisons.json`: native evidence and unchanged independent rubrics.

Optional human overrides use one record per Final/route:

```json
[{"route":"final_storyboard", "final_index":1, "decision":"matched",
  "candidate_id":"final_storyboard:1:2", "reason":"Pose and composition agree"}]
```

Use `decision: "unmatched"` or `"pending"` without a candidate ID for other outcomes.

```bash
python run_demo.py --review-run outputs/RUN_DIRECTORY --reviews reviews.json
```

## Repository layout

```text
CS55_system/
  streamlit_app.py           # English frontend using the shared pipeline
  notebooks/CS55_Evidence_System.ipynb
  src/cs55_demo/
    automatic.py             # Panel quality filtering, range constraints, acceptance
    system.py                # Shared orchestration, CLIP, review and support scoring
    sampling.py              # Original notebook time sampling functions
    storyboard_layout.py     # Existing PDF layout detectors
    storyboard_text.py       # Shared text extraction and grouping
    dual_retrieval.py         # Existing normalized edge/HOG features
    local_structure.py        # Existing directional local structure diagnostics
    provenance.py            # Existing provenance extraction
    source_project.py        # Existing explicit project verification
    provenance_scoring.py    # Existing independent score rubrics
  tests/test_workflow.py
  run_demo.py
  config.example.json
  pyproject.toml
  requirements.txt
  .gitignore
```

Only source, a clean notebook, tests, and example configuration belong in GitHub. Material files, generated outputs, virtual environments, and local settings are excluded. Generated outputs and local settings should remain outside source control.

## Verification

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests use synthetic inputs and injected feature vectors; they verify constraints, scoring denominators and decision behavior, rather than measuring model accuracy. Real visual accuracy and auto-accept precision require held-out labeled examples.
