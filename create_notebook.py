"""Generate the clean notebook entry point for the shared package."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
cells = []


def add(kind, source):
    cell = dict(cell_type=kind, metadata={}, source=source.strip().splitlines(keepends=True))
    if kind == "code":
        cell.update(execution_count=None, outputs=[])
    cells.append(cell)


add("markdown", """
# CS55 Production Evidence Evaluation

Automatic panel extraction and range-constrained Final-led matching.
The notebook calls the same modules as `run_demo.py`. Automatic matches remain provisional.
""")
add("markdown", """
## 1. Project and configuration

Set `PROJECT_ROOT` only if this notebook is opened outside the packaged project.
Copy `config.example.json` to `config.local.json`, then enter your file paths.
All relative material paths are resolved relative to the configuration file.
""")
add("code", '''
from pathlib import Path
import sys
import json
import pandas as pd
from IPython.display import display, Image as DisplayImage

# If this notebook is outside the project, enter the CS55_system directory here.
PROJECT_ROOT = None
if PROJECT_ROOT is None:
    candidates = [Path.cwd(), *Path.cwd().parents]
    PROJECT_ROOT = next((p for p in candidates if (p / "src/cs55_demo/system.py").is_file()), None)
if PROJECT_ROOT is None:
    raise ValueError("Set PROJECT_ROOT to the CS55_system project directory")
PROJECT_ROOT = Path(PROJECT_ROOT).expanduser().resolve()
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from cs55_demo.system import load_config, prepare, retrieve, inspect_provenance, apply_reviews, save_json

CONFIG_PATH = PROJECT_ROOT / "config.local.json"
if not CONFIG_PATH.exists():
    raise FileNotFoundError("Copy config.example.json to config.local.json and enter your material paths first")
config = load_config(CONFIG_PATH)
display(pd.DataFrame([config.get("sampling", {})]))
''')
add("markdown", """
## 2. Automatic panels and video samples

Usable panel proposals are exported automatically; no mandatory page review.
Empty, tiny and invalid regions are excluded and recorded. Detection can be incomplete.
Video start/end times and sample intervals are configured independently for Final and Animatic.
""")
add("code", '''
prepared = prepare(config)
RUN_DIR = Path(prepared["run_dir"])
panel_catalog = pd.DataFrame(prepared["panels"])
catalog_fields = [k for k in ("evidence_index", "page_index", "panel_index", "panel_path", "review_status") if k in panel_catalog]
display(panel_catalog[catalog_fields])
print("Panel catalog:", RUN_DIR / "panel_catalog.json")
print("Output directory:", RUN_DIR)
''')
add("markdown", """
## 3. Declare correspondence ranges

Use `evidence_index` from the panel catalog. A rule may cover several panels.
Times use the original video timeline, with half-open intervals `[start, end)`.
These are declared constraints, not verified Ground Truth.
Final frames outside the declared ranges remain in the coverage denominator.
""")
add("code", '''
# Edit these ranges or edit correspondence_ranges in config.local.json.
# Storyboard example:
# {"evidence_type": "storyboard", "panel_indices": [1, 2],
#  "final_start_sec": 45.0, "final_end_sec": 52.0}
# Animatic example:
# {"evidence_type": "animatic", "evidence_start_sec": 10.0, "evidence_end_sec": 18.0,
#  "final_start_sec": 45.0, "final_end_sec": 52.0}
CORRESPONDENCE_RANGES = config.get("correspondence_ranges", [])
config["correspondence_ranges"] = CORRESPONDENCE_RANGES
save_json(RUN_DIR / "config.json", config)
display(pd.DataFrame(CORRESPONDENCE_RANGES))
''')
add("markdown", """
## 4. Range-constrained matching and automatic decisions

Visual CLIP ranks candidates inside each declared range. Grouped text and valid local structure
provide Storyboard support; neighbouring candidates provide additional context.
Top-1 requires minimum visual similarity, a sufficient margin when a runner-up exists,
and auxiliary support. Excessive continuous reuse requires review.
Thresholds are configurable heuristics; validate their accuracy before trusting automation.
No monotonic path is imposed before sequence assessment.
""")
add("code", '''
result = retrieve(config, prepared)
decisions = pd.DataFrame(result["decisions"])
display(decisions)
display(decisions.groupby(["route", "status"]).size().rename("count").reset_index())
''')
add("markdown", """
## 5. Inspect results and optionally correct uncertain cases

Only review cases you need to correct. A human choice overrides one Final/route.
The candidate ID must belong to that exact Final/route. Leave `HUMAN_REVIEWS` empty for fully automatic execution.
""")
add("code", '''
candidate_table = pd.DataFrame(result["candidates"])
display(candidate_table)

def show_candidate(candidate_id):
    row = next(r for r in result["candidates"] if r["id"] == candidate_id)
    print("Final", row["final_index"], "Evidence", row["evidence_index"])
    display(DisplayImage(filename=row["final_path"], width=480))
    display(DisplayImage(filename=row["evidence_path"], width=480))
    print(row.get("description") or "No extracted description")

# show_candidate("final_storyboard:1:2")
HUMAN_REVIEWS = []
# Example:
# HUMAN_REVIEWS = [{"route": "final_storyboard", "final_index": 1,
#                  "decision": "matched", "candidate_id": "final_storyboard:1:2",
#                  "reason": "Pose and composition agree"}]
scores = apply_reviews(RUN_DIR, HUMAN_REVIEWS if HUMAN_REVIEWS else None)
display(pd.DataFrame(scores["provisional_and_human"]["route_order"]))
print(json.dumps(scores, indent=2))
''')
add("markdown", """
## 6. Native provenance and timestamp comparisons

Inspect each submitted asset. Four provenance indicators retain their independent check-level rubrics.
Timestamp comparisons are separate. No aggregate provenance authenticity score is calculated.
""")
add("code", '''
provenance_summary = inspect_provenance(config, prepared)
display(pd.DataFrame(provenance_summary).T[["status", "coverage"]])
provenance_scores = json.loads((RUN_DIR / "provenance_scores.json").read_text())
for asset, item in provenance_scores["assets"].items():
    print(asset)
    display(pd.DataFrame(item["indicator_scores"]).T[["label", "score", "reason"]])
display(json.loads((RUN_DIR / "timestamp_comparisons.json").read_text()))
''')
add("markdown", """
## 7. Saved outputs

`matched_list.json` includes the decision source; automatic matches remain provisional.
`unmatched_list.json` means insufficient supporting evidence, while `pending_list.json` contains unresolved cases.
Human-confirmed metrics and provisional-plus-human metrics are reported separately.
""")
add("code", '''
for name in ("matched_list", "unmatched_list", "pending_list"):
    path = RUN_DIR / (name + ".json")
    rows = json.loads(path.read_text())
    print(name, len(rows), path)
print("All JSON files:")
for path in sorted(RUN_DIR.glob("*.json")):
    print(path.name)
''')
notebook = dict(cells=cells, metadata=dict(kernelspec=dict(display_name="Python 3", language="python", name="python3"),
                language_info=dict(name="python", version="3.10")), nbformat=4, nbformat_minor=4)
target = ROOT / "notebooks/CS55_Evidence_System.ipynb"
target.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(target)
