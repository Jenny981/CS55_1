"""UI for the shared CS55 notebook and CLI pipeline."""
import copy
import json
import sys
import uuid
from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
from cs55_demo.system import load_config, prepare, retrieve, inspect_provenance, apply_reviews, save_json
from cs55_demo.automatic import validate_ranges

st.set_page_config(page_title="CS55 Evidence Review", page_icon=":material/fact_check:", layout="wide")


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else default


@st.cache_data(max_entries=64, show_spinner=False)
def thumbnail(path, modified):
    with Image.open(path) as image:
        result = image.convert("RGB")
        result.thumbnail((640, 420))
        return result


def show_image(path, caption):
    source = Path(path)
    if source.is_file():
        st.image(thumbnail(str(source), source.stat().st_mtime_ns), caption=caption)
    else:
        st.warning(f"Image unavailable: {source.name}")


def download(path):
    path = Path(path)
    if path.is_file():
        st.download_button(f"Download {path.name}", path.read_bytes(), file_name=path.name,
                           mime="application/json", key=f"download:{path}")


def revision(prepared, configuration):
    """Reuse extracted material in a fresh run, preserving earlier results."""
    destination = ROOT / "outputs" / ("run_revision_" + uuid.uuid4().hex[:12])
    destination.mkdir(parents=True)
    updated = dict(prepared, run_dir=str(destination))
    save_json(destination / "prepared.json", updated)
    save_json(destination / "config.json", configuration)
    return updated


st.title("CS55 Evidence Review")
st.caption("Final-led retrieval · Declared correspondence ranges · Optional human correction")
if "configuration" not in st.session_state:
    config_path = ROOT / "config.local.json"
    if not config_path.exists():
        config_path = ROOT / "config.example.json"
    st.session_state.configuration = load_config(config_path)

with st.sidebar:
    st.header("Workspace")
    stage = st.radio("Workflow", ["Materials", "Panels and ranges", "Matching", "Review", "Results"])
    existing = sorted((ROOT / "outputs").glob("run_*/prepared.json"), reverse=True)
    selected_run = st.selectbox("Open an existing run", [""] + [str(p.parent) for p in existing],
                                format_func=lambda p: Path(p).name if p else "Choose a run")
    if st.button("Load selected run", disabled=not selected_run):
        st.session_state.prepared = read(Path(selected_run) / "prepared.json")
        st.session_state.configuration = read(Path(selected_run) / "config.json")
        st.rerun()
    st.caption("Source files stay on this computer. Local paths refer to the machine running the app.")

prepared = st.session_state.get("prepared")
run = Path(prepared["run_dir"]) if prepared else None
config = st.session_state.configuration

if stage == "Materials":
    st.header("Materials and sampling")
    mode = st.radio("Material source", ["Local paths", "Upload files"], horizontal=True)
    paths, uploads = {}, {}
    for role in ("final", "storyboard", "animatic"):
        label = role.title() + (" (required)" if role == "final" else " (optional)")
        if mode == "Local paths":
            paths[role] = st.text_input(label, value=config.get(f"{role}_path") or "",
                                        key=f"path:{role}")
        else:
            uploads[role] = st.file_uploader(label, type=["pdf"] if role == "storyboard"
                                            else ["mp4", "mov", "mkv", "avi", "webm"], key=f"upload:{role}")
    project_root = st.text_input("Source-project search directory (optional)",
                                 value=config.get("project_search_root") or "")
    with st.form("sampling"):
        sampling = {}
        for role in ("final", "animatic"):
            st.subheader(f"{role.title()} sampling")
            current = config.get("sampling", {}).get(role, {})
            columns = st.columns(3)
            start = columns[0].number_input(f"{role.title()} start (seconds)", min_value=0.,
                                             value=float(current.get("start_sec", 0.)))
            end = columns[1].text_input(f"{role.title()} end (blank = full duration)",
                                         value=str(current.get("end_sec") or ""))
            interval = columns[2].number_input(f"{role.title()} interval (seconds)", min_value=.1,
                                                 value=float(current.get("interval_sec", 2.)))
            sampling[role] = dict(start_sec=start, end_sec=end, interval_sec=interval,
                                  skip_near_blank=st.checkbox(f"Skip near-black / near-white {role} frames", value=True))
        submitted = st.form_submit_button("Prepare materials", type="primary")
    if submitted:
        try:
            settings = copy.deepcopy(config)
            settings["project_search_root"] = str(Path(project_root).expanduser().resolve()) if project_root.strip() else None
            settings["sampling"] = sampling
            for options in sampling.values():
                options["end_sec"] = float(options["end_sec"]) if options["end_sec"].strip() else None
            if mode == "Upload files":
                if uploads["final"] is None or not any(uploads[k] for k in ("storyboard", "animatic")):
                    raise ValueError("Submit a Final and at least one evidence material")
                destination = ROOT / "outputs" / ("uploads_" + uuid.uuid4().hex[:12])
                destination.mkdir(parents=True)
                for role, uploaded in uploads.items():
                    if uploaded is not None:
                        target = destination / (role + Path(uploaded.name).suffix.lower())
                        with target.open("wb") as handle:
                            handle.write(uploaded.getbuffer())
                        paths[role] = str(target)
            for role in ("final", "storyboard", "animatic"):
                value = paths.get(role, "").strip().strip('"').strip("'")
                settings[f"{role}_path"] = str(Path(value).expanduser().resolve()) if value else None
            settings["output_dir"] = str(ROOT / "outputs")
            # New materials require new declarations, not stale mappings from a previous run.
            settings["correspondence_ranges"] = []
            with st.status("Preparing materials", expanded=True) as status:
                new_prepared = prepare(settings, progress=st.write)
                status.update(label="Materials prepared", state="complete")
            st.session_state.prepared = new_prepared
            st.session_state.configuration = settings
            st.success("Open Panels and ranges to declare correspondence intervals.")
        except Exception as error:
            st.error(str(error))

elif prepared is None:
    st.info("Prepare materials or open an existing run first.")

elif stage == "Panels and ranges":
    st.header("Automatically extracted panels")
    panels = prepared["panels"]
    st.caption("Usable proposals are retained automatically. Extraction may omit panels; use the catalog IDs below.")
    described = sum(bool(p.get("text", {}).get("description")) for p in panels)
    st.caption(f"Extracted panels: {len(panels)} · With text: {described} · Without text: {len(panels) - described}. Text reranking is available only where distinct descriptions exist.")
    st.dataframe(pd.DataFrame([{k: p.get(k) for k in ("evidence_index", "page_index", "panel_index", "panel_path")}
                              for p in panels]), hide_index=True)
    if panels:
        panel_id = st.selectbox("Preview panel", [p["evidence_index"] for p in panels])
        panel = next(p for p in panels if p["evidence_index"] == panel_id)
        show_image(panel["panel_path"], f"Panel {panel_id}")
        st.write(panel.get("text", {}).get("description") or "No extracted description")
    st.header("Declare correspondence ranges")
    st.caption("Original video seconds; start included, end excluded. Panel IDs may be comma-separated. Overlapping ranges form a union.")
    rules = config.get("correspondence_ranges", [])
    evidence_types = (["storyboard"] if panels else []) + (["animatic"] if prepared["frames"]["animatic"] else [])
    if evidence_types:
        st.subheader("Add a scene or panel range")
        kind = st.selectbox("Evidence material", evidence_types)
        selected_panels = []
        if kind == "storyboard":
            ids = [p["evidence_index"] for p in panels]
            left, right = st.columns(2)
            first = left.selectbox("First Storyboard panel", ids, key=f"first:{run}")
            last = right.selectbox("Last Storyboard panel", [i for i in ids if i >= first],
                                    key=f"last:{run}")
            selected_panels = [p for p in panels if first <= p["evidence_index"] <= last]
            st.caption(f"{len(selected_panels)} extracted panels selected")
            for column, panel in zip(st.columns(2), [selected_panels[0], selected_panels[-1]]):
                with column:
                    show_image(panel["panel_path"], f"Panel {panel['evidence_index']}")
                    st.write(panel.get("text", {}).get("description") or "No extracted description")
        with st.form("add_range"):
            left, right = st.columns(2)
            final_start = left.number_input("Final range start (seconds)", min_value=0., value=0.)
            final_end = right.number_input("Final range end (seconds)", min_value=0., value=10.)
            new_rule = dict(evidence_type=kind, final_start_sec=final_start, final_end_sec=final_end)
            if kind == "storyboard":
                new_rule["panel_indices"] = [p["evidence_index"] for p in selected_panels]
            else:
                new_rule["evidence_start_sec"] = left.number_input("Animatic range start (seconds)", min_value=0., value=0.)
                new_rule["evidence_end_sec"] = right.number_input("Animatic range end (seconds)", min_value=0., value=10.)
            added = st.form_submit_button("Add correspondence range", type="primary")
        if added:
            try:
                validate_ranges([new_rule])
                new_config = copy.deepcopy(config)
                new_config["correspondence_ranges"] = rules + [new_rule]
                if (run / "result.json").exists():
                    st.session_state.prepared = revision(prepared, new_config)
                else:
                    save_json(run / "config.json", new_config)
                st.session_state.configuration = new_config
                st.rerun()
            except ValueError as error:
                st.error(str(error))
    st.subheader("Saved ranges")
    rows = [dict(evidence_type=r["evidence_type"], panel_indices=", ".join(map(str, r.get("panel_indices", []))),
                 final_start_sec=float(r["final_start_sec"]), final_end_sec=float(r["final_end_sec"]),
                 evidence_start_sec=r.get("evidence_start_sec"), evidence_end_sec=r.get("evidence_end_sec")) for r in rules]
    columns = ["evidence_type", "panel_indices", "final_start_sec", "final_end_sec", "evidence_start_sec", "evidence_end_sec"]
    edited = st.data_editor(pd.DataFrame(rows, columns=columns), num_rows="dynamic", hide_index=True,
        column_config={"evidence_type": st.column_config.SelectboxColumn(options=["storyboard", "animatic"], required=True)},
        key=f"ranges:{run}")
    if st.button("Save ranges", type="primary"):
        try:
            saved = []
            for row in edited.to_dict("records"):
                rule = dict(evidence_type=row["evidence_type"], final_start_sec=float(row["final_start_sec"]),
                            final_end_sec=float(row["final_end_sec"]))
                if rule["evidence_type"] == "storyboard":
                    rule["panel_indices"] = [int(v.strip()) for v in str(row["panel_indices"]).split(",") if v.strip()]
                    unknown = set(rule["panel_indices"]) - {p["evidence_index"] for p in panels}
                    if unknown:
                        raise ValueError(f"Unknown extracted panel IDs: {sorted(unknown)}")
                else:
                    if not prepared["frames"]["animatic"]:
                        raise ValueError("No Animatic was submitted")
                    rule.update(evidence_start_sec=float(row["evidence_start_sec"]), evidence_end_sec=float(row["evidence_end_sec"]))
                saved.append(rule)
            validate_ranges(saved)
            if (run / "result.json").exists() and saved != rules:
                new_config = dict(config, correspondence_ranges=saved)
                st.session_state.prepared = revision(prepared, new_config)
                st.session_state.configuration = new_config
                st.rerun()
            config["correspondence_ranges"] = saved
            save_json(run / "config.json", config)
            st.success("Ranges saved")
        except (ValueError, TypeError, KeyError) as error:
            st.error(str(error))

elif stage == "Matching":
    st.header("Range-constrained matching")
    mode = st.selectbox("Automatic selection policy", ["Range Top-1", "Strict support checks"],
                        index=1 if config["matching"].get("acceptance_mode") == "strict" else 0)
    st.caption("Range Top-1 automatically selects the best candidate inside your declared range when minimum visual support is met. Review is optional. Strict mode can send ambiguous cases to review.")
    with st.form("matching_settings"):
        settings = copy.deepcopy(config["matching"])
        settings["acceptance_mode"] = "range_top1" if mode == "Range Top-1" else "strict"
        settings["use_text_reranking"] = st.checkbox("Use text semantics to rerank visually similar panels", value=settings.get("use_text_reranking", True))
        settings["text_visual_shortlist"] = 5
        settings["text_max_visual_loss"] = st.number_input("Maximum visual similarity loss for text reranking", 0., 1., float(settings.get("text_max_visual_loss", .05)), step=.01)
        settings["text_rank_weight"] = 1.25
        settings["top_k"] = st.number_input("Candidates per Final and material", 1, 50, int(settings["top_k"]))
        settings["min_visual_similarity"] = st.number_input("Minimum visual similarity", 0., 1., float(settings["min_visual_similarity"]), step=.01)
        if mode == "Strict support checks":
            settings["min_top1_margin"] = st.number_input("Minimum Top-1 / Top-2 margin", 0., 2., float(settings["min_top1_margin"]), step=.01)
            settings["max_consecutive"] = st.number_input("Maximum consecutive reuse", 1, 100, int(settings["max_consecutive"]))
        settings["use_structure"] = st.checkbox("Use local structure for Storyboard", value=settings["use_structure"])
        if mode == "Strict support checks":
            settings["require_auxiliary_support"] = st.checkbox("Require auxiliary support for automatic acceptance", value=settings["require_auxiliary_support"])
        st.caption("Acceptance thresholds are configurable heuristics and have not been calibrated against labeled data.")
        submitted = st.form_submit_button("Run matching", type="primary")
    if submitted:
        try:
            if not config.get("correspondence_ranges"):
                raise ValueError("Save at least one declared correspondence range first")
            config["matching"] = settings
            if (run / "result.json").exists():
                prepared = revision(prepared, config)
                st.session_state.prepared = prepared
                run = Path(prepared["run_dir"])
            save_json(run / "config.json", config)
            with st.status("Retrieving candidates", expanded=True) as status:
                retrieve(config, prepared, progress=st.write)
                status.update(label="Matching complete", state="complete")
            st.success("Automatic results saved. Open Results to inspect selected matches; Review is optional.")
        except Exception as error:
            st.error(str(error))
    if (run / "result.json").exists():
        st.info("Rerunning creates a new result revision and reuses extracted material. Earlier results are preserved.")

elif stage == "Review":
    st.header("Optional human correction")
    result = read(run / "result.json")
    if not result:
        st.info("Run matching first.")
    else:
        decisions = read(run / "effective_decisions.json", result["decisions"])
        status_filter = st.selectbox("Show decisions", ["requires_review", "provisionally_matched", "insufficient_evidence", "not_evaluated", "human_confirmed", "All"])
        shown = [d for d in decisions if status_filter == "All" or d["status"] == status_filter]
        st.caption(f"{len(shown)} route decisions. Changes are applied only when saved.")
        if shown:
            with st.form(f"review:{run}:{status_filter}"):
                proposed = []
                for decision in shown:
                    route, index = decision["route"], decision["final_index"]
                    rows = [r for r in result["candidates"] if r["route"] == route and r["final_index"] == index]
                    st.subheader(f"Final {index} · {route.replace('_', ' → ', 1)}")
                    st.caption(f"{decision['status']} · {decision['reason']}")
                    frame = prepared["frames"]["final"][index - 1]
                    show_image(frame["keyframe_path"], f"Final {index} at {frame['timestamp_sec']:.2f}s")
                    for row in rows:
                        show_image(row["evidence_path"], f"Evidence {row['evidence_index']} · visual rank {row['visual_rank']} · {row['visual_similarity']:.3f}")
                        if row.get("description"):
                            st.write(row["description"])
                    options = ["Keep current decision", "No match", "Pending"] + [r["id"] for r in rows]
                    choice = st.selectbox("Decision", options, key=f"choice:{run}:{route}:{index}")
                    note = st.text_input("Reason (optional)", key=f"note:{run}:{route}:{index}")
                    if choice != options[0]:
                        proposed.append(dict(route=route, final_index=index,
                            decision="unmatched" if choice == "No match" else "pending" if choice == "Pending" else "matched",
                            candidate_id=choice if choice not in options[:3] else None, reason=note))
                submitted = st.form_submit_button("Save review decisions", type="primary")
            if submitted:
                try:
                    previous = {(r["route"], r["final_index"]): r for r in read(run / "reviews.json", [])}
                    previous.update({(r["route"], r["final_index"]): r for r in proposed})
                    apply_reviews(run, list(previous.values()))
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))

elif stage == "Results":
    st.header("Evidence assessment")
    scores = read(run / "evidence_scores.json")
    if scores:
        effective = read(run / "effective_decisions.json", [])
        if effective:
            st.dataframe(pd.DataFrame(effective).groupby(["route", "status"]).size().rename("count").reset_index(), hide_index=True)
        st.caption("A material with no declared correspondence range is not evaluated. Add its ranges in Panels and ranges if required.")
        scope = st.selectbox("Scoring basis", ["provisional_and_human", "human_confirmed"])
        item = scores[scope]
        for column, field in zip(st.columns(3), ["visual_support_score", "sequence_consistency_score", "overall_evidence_score"]):
            value = item.get(field)
            column.metric(field.replace("_", " ").title(), "N/A" if value is None else f"{value:.2f}")
        st.caption(scores["interpretation"])
        st.dataframe(pd.DataFrame(item["route_order"]), hide_index=True)
        for name in ("matched_list", "pending_list", "unmatched_list"):
            st.write(f"{name.replace('_', ' ').title()}: {len(read(run / (name + '.json'), []))}")
        if st.toggle("Show automatically selected evidence", value=True):
            matched = read(run / "matched_list.json", [])
            for row in matched:
                st.subheader(f"Final {row['final_index']} · {row['route'].replace('_', ' → ', 1)} · evidence {row['evidence_index']}")
                left, right = st.columns(2)
                with left:
                    show_image(row["final_path"], "Final")
                with right:
                    show_image(row["evidence_path"], "Selected evidence")
                if row.get("description"):
                    st.write(row["description"])
                st.caption(f"Decision: {row.get('decision_source')} · visual rank: {row['visual_rank']} · text rank: {row.get('text_group_rank')} · text reranking: {row.get('text_reranking_applied', False)}")
    st.subheader("Provenance and timestamps")
    if st.button("Inspect provenance", disabled=(run / "provenance_scores.json").exists()):
        try:
            with st.status("Inspecting provenance", expanded=True):
                inspect_provenance(config, prepared, progress=st.write)
            st.rerun()
        except Exception as error:
            st.error(str(error))
    provenance = read(run / "provenance_scores.json")
    if provenance:
        st.caption(provenance["score_interpretation"])
        for asset, item in provenance["assets"].items():
            st.write(asset.title())
            st.dataframe(pd.DataFrame(item["indicator_scores"]).T, height=220)
        if st.checkbox("Show timestamp comparisons"):
            st.json(read(run / "timestamp_comparisons.json"))
    st.subheader("Download native outputs")
    for path in sorted(run.glob("*.json")):
        download(path)

if run:
    st.caption(f"Current output directory: {run}")
