"""Portable notebook and CLI entry points for the same evaluation pipeline."""
import json
from pathlib import Path
from datetime import datetime, timezone

import numpy as np

from .automatic import extract_automatic_panels, validate_ranges, allowed_evidence, select_top1, rerank_with_text
from .storyboard_layout import export_reviewed
from .sampling import extract_time_samples
from .storyboard_text import extract_panel_descriptions, annotate_shared_text_groups
from .provenance import inspect_asset_basics, collect_project_file_evidence, build_editing_history, build_provenance_summary
from .provenance_scoring import provenance_scores, timestamp_comparisons


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def load_config(path):
    path = Path(path).resolve()
    config = json.loads(path.read_text(encoding="utf-8"))
    for field in ("final_path", "storyboard_path", "animatic_path", "output_dir", "project_search_root"):
        if config.get(field):
            value = Path(config[field]).expanduser()
            config[field] = str(value if value.is_absolute() else (path.parent / value).resolve())
    for field in ("source_project_paths", "source_project_unsigned_paths"):
        config[field] = {role: str((path.parent / value).resolve())
                         for role, value in config.get(field, {}).items()}
    validate_ranges(config.get("correspondence_ranges", []))
    settings = config.setdefault("matching", {})
    defaults = dict(top_k=5, min_visual_similarity=.25, min_top1_margin=.02,
                    require_auxiliary_support=True,
                    text_top_k=10, structure_top_k=10, structure_candidate_limit=20,
                    neighbor_radius=2, max_consecutive=5, use_structure=True,
                    acceptance_mode="range_top1", use_text_reranking=True,
                    text_visual_shortlist=5, text_max_visual_loss=.05, text_rank_weight=1.25)
    for key, value in defaults.items():
        settings.setdefault(key, value)
    if settings["acceptance_mode"] not in ("range_top1", "strict"):
        raise ValueError("Unknown acceptance mode")
    for key in ("top_k", "text_top_k", "structure_top_k", "structure_candidate_limit", "max_consecutive"):
        if type(settings[key]) is not int or settings[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if type(settings["neighbor_radius"]) is not int or settings["neighbor_radius"] < 0:
        raise ValueError("neighbor_radius must be a nonnegative integer")
    for key in ("min_visual_similarity", "min_top1_margin"):
        if not np.isfinite(settings[key]) or settings[key] < 0:
            raise ValueError(f"Invalid {key}")
    return config


def prepare(config, progress=print):
    assets = {role: Path(config[f"{role}_path"]) for role in ("final", "animatic", "storyboard")
              if config.get(f"{role}_path")}
    if "final" not in assets or not ({"storyboard", "animatic"} & assets.keys()):
        raise ValueError("A Final and at least one evidence material are required")
    for path in assets.values():
        if not path.is_file():
            raise FileNotFoundError(path)
    run = Path(config.get("output_dir", "outputs")) / datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%S_%fZ")
    run.mkdir(parents=True, exist_ok=False)
    save_json(run / "config.json", config)
    panels, manifest, text = [], None, []
    if "storyboard" in assets:
        progress("Automatically extracting usable Storyboard panels")
        panels, manifest = extract_automatic_panels(assets["storyboard"], run / "panels")
        # Full-document indices are assigned once, after quality filtering.
        text = extract_panel_descriptions(assets["storyboard"], panels) if panels else []
        for panel, item in zip(panels, text):
            item["storyboard_index"] = panel["evidence_index"]
        text = annotate_shared_text_groups(text)
        for record, item in zip(panels, text):
            record["text"] = item
        save_json(run / "panel_manifest.json", manifest)
        save_json(run / "panel_catalog.json", panels)
        save_json(run / "storyboard_text.json", text)
    frames = {}
    for role in ("final", "animatic"):
        if role not in assets:
            frames[role] = []
            continue
        progress(f"Sampling {role}")
        options = config.get("sampling", {}).get(role, {})
        table, _ = extract_time_samples(
            assets[role], run / "samples", role,
            interval_sec=options.get("interval_sec", 2.), start_sec=options.get("start_sec", 0.),
            end_sec=options.get("end_sec"), skip_near_blank=options.get("skip_near_blank", True))
        frames[role] = table.to_dict("records")
        for row in frames[role]:
            row["evidence_index"] = row["source_sample_index"]
        save_json(run / f"{role}_samples.json", frames[role])
    prepared = dict(run_dir=str(run), assets={k: str(v) for k, v in assets.items()},
                    panels=panels, frames=frames,
                    panel_review_confirmed="storyboard" not in assets)
    save_json(run / "prepared.json", prepared)
    return prepared


def apply_panel_review(run, reviewed_pages):
    """Replace automatic Storyboard proposals with explicit human selections."""
    run = Path(run)
    if (run / "result.json").exists():
        raise ValueError("Panel review must be completed before matching")
    prepared = json.loads((run / "prepared.json").read_text())
    manifest = json.loads((run / "panel_manifest.json").read_text())
    by_page = {int(page["page_index"]): page for page in reviewed_pages}
    if set(by_page) != {int(page["page_index"]) for page in manifest["pages"]}:
        raise ValueError("Submit a review for every Storyboard page")

    for page in manifest["pages"]:
        submitted = by_page[int(page["page_index"])]
        width, height = page["size"]
        candidates = []
        orders = []
        for position, item in enumerate(submitted.get("candidates", []), 1):
            decision = item.get("decision")
            if decision not in ("accept", "reject"):
                raise ValueError("Mark every panel candidate as accept or reject")
            order = int(item.get("order", position))
            if order in orders:
                raise ValueError("Panel order values must be unique within a page")
            orders.append(order)
            box = [int(round(float(value))) for value in item.get("bbox", [])]
            if len(box) != 4 or not (0 <= box[0] < box[2] <= width and
                                     0 <= box[1] < box[3] <= height):
                raise ValueError(f"Page {page['page_index']} contains an invalid panel boundary")
            candidates.append(dict(item, bbox=box, decision=decision, order=order,
                                   method=item.get("method", "manual_review"),
                                   decision_source="human_panel_review",
                                   needs_boundary_review=False))
        page["candidates"] = sorted(candidates, key=lambda item: item["order"])
        page.update(reviewed=True, review_source="human_panel_review",
                    extraction_status="panels_available" if any(
                        item["decision"] == "accept" for item in candidates) else "not_extracted")

    records = export_reviewed(manifest)
    for evidence_index, record in enumerate(records, 1):
        record.update(evidence_index=evidence_index, review_status="human_accepted",
                      decision_source="human_panel_review")
    descriptions = extract_panel_descriptions(manifest["source_pdf"], records)
    for record, item in zip(records, descriptions):
        item["storyboard_index"] = record["evidence_index"]
    descriptions = annotate_shared_text_groups(descriptions)
    for record, item in zip(records, descriptions):
        record["text"] = item

    prepared.update(panels=records, panel_review_confirmed=True)
    config = json.loads((run / "config.json").read_text())
    config["correspondence_ranges"] = [rule for rule in config.get("correspondence_ranges", [])
                                       if rule.get("evidence_type") != "storyboard"]
    save_json(run / "panel_manifest.json", manifest)
    save_json(run / "panel_catalog.json", records)
    save_json(run / "storyboard_text.json", descriptions)
    save_json(run / "prepared.json", prepared)
    save_json(run / "config.json", config)
    return prepared


class ClipEncoder:
    def __init__(self, model_name):
        import torch
        from transformers import CLIPModel, CLIPProcessor
        self.torch = torch
        self.device = "cuda" if torch.cuda.is_available() else "mps" if torch.backends.mps.is_available() else "cpu"
        self.model = CLIPModel.from_pretrained(model_name).to(self.device).eval()
        self.processor = CLIPProcessor.from_pretrained(model_name)

    def images(self, records):
        from PIL import Image
        import torch.nn.functional as F
        output = []
        for record in records:
            with Image.open(record.get("keyframe_path") or record["panel_path"]) as image:
                pixels = self.processor(images=image.convert("RGB"), return_tensors="pt")["pixel_values"]
            with self.torch.inference_mode():
                pooled = self.model.vision_model(pixel_values=pixels.to(self.device)).pooler_output
                features = self.model.visual_projection(pooled)
                output.append(F.normalize(features.float(), dim=-1).cpu().numpy()[0])
        return np.stack(output) if output else np.empty((0, self.model.config.projection_dim))

    def texts(self, descriptions):
        import torch.nn.functional as F
        output = []
        for start in range(0, len(descriptions), 32):
            inputs = self.processor(text=descriptions[start:start + 32], padding=True,
                                    truncation=True, return_tensors="pt")
            inputs = {k: v.to(self.device) for k, v in inputs.items()
                      if k in ("input_ids", "attention_mask")}
            with self.torch.inference_mode():
                pooled = self.model.text_model(**inputs).pooler_output
                features = self.model.text_projection(pooled)
                output.extend(F.normalize(features.float(), dim=-1).cpu().numpy())
        return np.stack(output) if output else np.empty((0, self.model.config.projection_dim))


def retrieve(config, prepared, encoder=None, progress=print):
    """Rank globally, then retain declared correspondence only as comparison context."""
    settings, ranges = config["matching"], config.get("correspondence_ranges", [])
    validate_ranges(ranges)
    run = Path(prepared["run_dir"])
    encoder = encoder or ClipEncoder(config.get("model_name", "openai/clip-vit-base-patch32"))
    finals, animatic, panels = prepared["frames"]["final"], prepared["frames"]["animatic"], prepared["panels"]
    if not panels and not animatic:
        raise ValueError("No usable evidence was extracted; check panel layout or video sampling")
    vectors = {"final": encoder.images(finals), "animatic": encoder.images(animatic),
               "storyboard": encoder.images(panels)}
    groups = {}
    for i, panel in enumerate(panels):
        item = panel["text"]
        if item.get("description"):
            groups.setdefault(item["text_group_id"], {"description": item["description"], "panels": []})["panels"].append(i)
    group_ids = list(groups)
    text_vectors = encoder.texts([groups[k]["description"] for k in group_ids]) if groups else None
    text_scores = vectors["final"] @ text_vectors.T if groups else None
    feature_cache = {}

    def structure(record):
        from .dual_retrieval import structure_feature
        path = record.get("keyframe_path") or record["panel_path"]
        if path not in feature_cache:
            feature_cache[path] = structure_feature(path)
        return feature_cache[path]

    candidates, decisions = [], []
    for kind, evidence in (("storyboard", panels), ("animatic", animatic)):
        if not evidence:
            continue
        matrix = vectors["final"] @ vectors[kind].T
        route_rows = []
        for fi, final in enumerate(finals):
            expected = allowed_evidence(final, evidence, kind, ranges, require_ranges=True)
            order = sorted(range(len(evidence)),
                           key=lambda i: (-float(matrix[fi, i]), evidence[i]["evidence_index"]))
            group_ranks = {}
            if kind == "storyboard" and groups:
                active_groups = list(range(len(group_ids)))
                active_groups.sort(key=lambda j: -float(text_scores[fi, j]))
                group_ranks = {group_ids[j]: rank for rank, j in enumerate(active_groups, 1)}
            rows = []
            for rank, ei in enumerate(order[:max(settings["top_k"], settings["structure_candidate_limit"])], 1):
                item = evidence[ei]
                text = item.get("text", {})
                text_rank = group_ranks.get(text.get("text_group_id"))
                detail = {}
                if kind == "storyboard" and settings["use_structure"] and rank <= settings["structure_candidate_limit"]:
                    from .local_structure import local_support
                    detail = local_support(structure(item), structure(final))
                row = dict(id=f"final_{kind}:{fi + 1}:{item['evidence_index']}", route=f"final_{kind}",
                           final_index=fi + 1, final_timestamp_sec=final["timestamp_sec"],
                           final_path=final["keyframe_path"], evidence_index=item["evidence_index"],
                           evidence_path=item.get("keyframe_path") or item["panel_path"],
                           evidence_timestamp_sec=item.get("timestamp_sec"),
                           visual_similarity=float(matrix[fi, ei]), visual_rank=rank,
                           declared_range_ids=expected.get(ei, []),
                           within_declared_correspondence=ei in expected,
                           description=text.get("description"),
                           text_group_id=text.get("text_group_id"), text_group_rank=text_rank,
                           shared_panel_count=text.get("shared_panel_count"),
                           text_similarity=float(text_scores[fi, group_ids.index(text["text_group_id"])])
                           if text_rank is not None else None,
                           text_supported=text_rank is not None and text_rank <= settings["text_top_k"],
                           structure=detail, structure_supported=False, neighbor_supported=False)
                if rank == 1:
                    row["runner_up_visual_similarity"] = float(matrix[fi, order[1]]) if len(order) > 1 else None
                rows.append(row)
            structure_order = sorted([r for r in rows if r["structure"].get("assessment") in
                                      ("partial_support", "structural_support")],
                                     key=lambda r: -r["structure"]["oriented_coverage"])
            for rank, row in enumerate(structure_order, 1):
                row["structure_rank"] = rank
                row["structure_supported"] = rank <= settings["structure_top_k"]
            if kind == "storyboard":
                rows = rerank_with_text(rows, settings)
            route_rows.append(rows[:settings["top_k"]])
        for fi, rows in enumerate(route_rows):
            for row in rows:
                neighbors = [j for j in range(max(0, fi - settings["neighbor_radius"]),
                                               min(len(finals), fi + settings["neighbor_radius"] + 1)) if j != fi]
                row["neighbor_supported"] = any(route_rows[j] and
                    route_rows[j][0]["evidence_index"] == row["evidence_index"] for j in neighbors)
            decision = select_top1(rows, settings)
            decision.update(route=f"final_{kind}", final_index=fi + 1,
                            final_timestamp_sec=finals[fi]["timestamp_sec"], decision_source="automatic")
            decisions.append(decision)
            candidates.extend(rows)
        progress(f"Retrieved Final to {kind}")
    # Supplementary relation only; it cannot override either primary route.
    supplementary = []
    if animatic and panels:
        matrix = vectors["animatic"] @ vectors["storyboard"].T
        for ai, values in enumerate(matrix):
            for rank, pi in enumerate(np.argsort(-values, kind="stable")[:settings["top_k"]], 1):
                supplementary.append(dict(animatic_index=animatic[ai]["evidence_index"],
                    storyboard_index=panels[int(pi)]["evidence_index"], visual_rank=rank,
                    visual_similarity=float(values[pi]), status="supplementary_candidate"))
    # Repeat limits flag uncertainty without changing the independently ranked winner.
    for route in ("final_storyboard", "final_animatic"):
        previous, count = None, 0
        lookup = {r["id"]: r for r in candidates}
        for decision in (d for d in decisions if d["route"] == route):
            selected = lookup.get(decision.get("selected_candidate_id"))
            key = selected["evidence_index"] if selected else None
            count = count + 1 if key is not None and key == previous else 1
            previous = key
            if selected and count > settings["max_consecutive"]:
                decision["continuous_reuse_warning"] = True
            if (selected and count > settings["max_consecutive"]
                    and settings.get("acceptance_mode", "strict") == "strict"):
                decision.update(status="requires_review", reason="consecutive_evidence_limit_exceeded",
                                selected_candidate_id=None)
    result = dict(schema_version="cs55-system-v1", candidates=candidates, decisions=decisions,
                  supplementary=supplementary, run_dir=str(run),
                  retrieval_scope="all_extracted_evidence_for_each_route",
                  range_semantics="submitter_declared_correspondence_used_after_retrieval_as_comparison_baseline",
                  thresholds_calibrated=False)
    save_json(run / "result.json", result)
    apply_reviews(run)
    return result


def inspect_provenance(config, prepared, progress=print):
    progress("Inspecting native provenance evidence")
    assets = {role: inspect_asset_basics(role, path) for role, path in prepared["assets"].items()}
    projects = collect_project_file_evidence(config)
    for role, asset in assets.items():
        asset["project_file"] = projects[role]
        asset["editing_history"] = build_editing_history(asset["timestamps"], asset["c2pa_manifest"],
                                                        asset["software"], asset["project_file"])
        asset["provenance_summary"] = build_provenance_summary(
            asset["file_hash"], asset["metadata"], asset["timestamps"], asset["c2pa_manifest"],
            asset["software"], asset["project_file"], asset["editing_history"])
    summary = {role: item["provenance_summary"] for role, item in assets.items()}
    run = Path(prepared["run_dir"])
    for name, value in (("provenance", assets), ("provenance_summary", summary),
                        ("provenance_scores", provenance_scores(summary)),
                        ("timestamp_comparisons", timestamp_comparisons(assets))):
        save_json(run / f"{name}.json", value)
    return summary


def _scores(finals, rows):
    supported = {r["final_index"] for r in rows}
    order = []
    for route in ("final_storyboard", "final_animatic"):
        selected = sorted((r for r in rows if r["route"] == route), key=lambda r: r["final_index"])
        concordant = discordant = tied = 0
        for i, left in enumerate(selected):
            for right in selected[i + 1:]:
                delta = right["evidence_index"] - left["evidence_index"]
                concordant += int(delta > 0)
                discordant += int(delta < 0)
                tied += int(delta == 0)
        comparable = concordant + discordant
        order.append(dict(route=route, confirmed_pair_count=len(selected),
                          concordant_pair_count=concordant, discordant_pair_count=discordant,
                          tied_pair_count=tied, comparable_pair_count=comparable,
                          score=round(100 * concordant / comparable, 2)
                          if comparable and len(selected) >= 3 else None,
                          index_sequence=[r["evidence_index"] for r in selected]))
    eligible = [r for r in order if r["score"] is not None]
    comparable = sum(r["comparable_pair_count"] for r in eligible)
    concordant = sum(r["concordant_pair_count"] for r in eligible)
    sequence = 100 * concordant / comparable if comparable else None
    coverage = 100 * len(supported) / len(finals) if finals else None
    overall = (2 * coverage * sequence / (coverage + sequence) if coverage + sequence else 0.) \
        if coverage is not None and sequence is not None else None
    return dict(total_final_frames=len(finals), supported_final_frames=len(supported),
                visual_support_score=round(coverage, 2) if coverage is not None else None,
                sequence_consistency_score=round(sequence, 2) if sequence is not None else None,
                overall_evidence_score=round(overall, 2) if overall is not None else None,
                route_order=order, coverage_denominator="all_retained_sampled_final_frames",
                formulas=dict(visual="supported / all_retained_final_frames * 100",
                              sequence="concordant / (concordant + discordant) * 100",
                              overall="harmonic_mean(visual, sequence)"))


def _correspondence_diagnostics(config, prepared, selected):
    """Compare globally retrieved pairs with submitter-declared correspondence."""
    ranges = config.get("correspondence_ranges", [])
    finals = prepared["frames"]["final"]
    evidence_by_kind = {"storyboard": prepared["panels"],
                        "animatic": prepared["frames"]["animatic"]}
    selected_by_key = {(row["route"], row["final_index"]): row for row in selected}
    rows, route_summaries = [], []

    for kind, evidence in evidence_by_kind.items():
        if not evidence:
            continue
        route = f"final_{kind}"
        route_rows = []
        declared_ids = set()
        observed_ids = {row["evidence_index"] for row in selected if row["route"] == route}
        for rule in ranges:
            if rule["evidence_type"] != kind:
                continue
            if kind == "storyboard":
                declared_ids.update(rule["panel_indices"])
            else:
                declared_ids.update(record["evidence_index"] for record in evidence
                                    if rule["evidence_start_sec"] <= record["timestamp_sec"] < rule["evidence_end_sec"])

        for final_index, final in enumerate(finals, 1):
            expected_positions = allowed_evidence(final, evidence, kind, ranges, require_ranges=True)
            expected_ids = sorted(evidence[position]["evidence_index"] for position in expected_positions)
            active_range_ids = sorted({range_id for ids in expected_positions.values() for range_id in ids})
            # Preserve an active declaration even if no extracted evidence falls inside it.
            timestamp = float(final["timestamp_sec"])
            active_rules = [(number, rule) for number, rule in enumerate(ranges, 1)
                            if rule["evidence_type"] == kind and
                            rule["final_start_sec"] <= timestamp < rule["final_end_sec"]]
            active_range_ids = sorted(set(active_range_ids) | {number for number, _ in active_rules})
            selected_row = selected_by_key.get((route, final_index))
            selected_id = selected_row["evidence_index"] if selected_row else None
            if not active_rules:
                status = "undeclared_final_interval"
                conforms = None
                reason = "No declared correspondence covers this Final timestamp; the global match cannot be assessed against a baseline."
            elif selected_id is None:
                status = "expected_support_not_observed"
                conforms = False
                reason = "A correspondence baseline exists, but no evidence pair was selected for this Final frame."
            elif selected_id in expected_ids:
                status = "conforms_to_declared_correspondence"
                conforms = True
                reason = "The globally selected evidence falls inside the submitter-declared correspondence."
            else:
                status = "outside_declared_evidence_set"
                conforms = False
                reason = "The globally selected evidence falls outside the evidence set declared for this Final timestamp."
            selected_elsewhere = []
            if selected_id is not None:
                for number, rule in enumerate(ranges, 1):
                    if rule["evidence_type"] != kind or number in active_range_ids:
                        continue
                    belongs = (selected_id in rule.get("panel_indices", []) if kind == "storyboard" else
                               any(record["evidence_index"] == selected_id and
                                   rule["evidence_start_sec"] <= record["timestamp_sec"] < rule["evidence_end_sec"]
                                   for record in evidence))
                    if belongs:
                        selected_elsewhere.append(number)
            record = dict(route=route, final_index=final_index,
                          final_timestamp_sec=timestamp, selected_evidence_index=selected_id,
                          expected_evidence_indices=expected_ids, active_correspondence_ids=active_range_ids,
                          selected_declared_elsewhere_ids=selected_elsewhere,
                          status=status, conforms=conforms, reason=reason)
            rows.append(record)
            route_rows.append(record)

        evaluable = [row for row in route_rows if row["conforms"] is not None]
        conforming = sum(row["conforms"] is True for row in evaluable)
        outside = sum(row["status"] == "outside_declared_evidence_set" for row in evaluable)
        missing = sum(row["status"] == "expected_support_not_observed" for row in evaluable)
        covered_declared = declared_ids & observed_ids
        route_summaries.append(dict(
            route=route, evaluable_final_count=len(evaluable), conforming_final_count=conforming,
            outside_declared_count=outside, expected_support_not_observed_count=missing,
            undeclared_final_count=sum(row["conforms"] is None for row in route_rows),
            correspondence_conformance_score=round(100 * conforming / len(evaluable), 2) if evaluable else None,
            declared_evidence_count=len(declared_ids), observed_declared_evidence_count=len(covered_declared),
            expected_evidence_coverage_score=round(100 * len(covered_declared) / len(declared_ids), 2)
            if declared_ids else None,
            formula="conforming_final_count / evaluable_final_count * 100",
        ))
    summaries = [item for item in route_summaries if item["evaluable_final_count"]]
    evaluable_total = sum(item["evaluable_final_count"] for item in summaries)
    conforming_total = sum(item["conforming_final_count"] for item in summaries)
    return dict(
        method="global_pair_results_compared_with_submitter_declared_correspondence_v1",
        baseline_interpretation="Declared correspondence is treated as the expected relationship for conformance analysis, not as independently verified ground truth.",
        retrieval_restricted_by_correspondence=False,
        correspondence_conformance_score=round(100 * conforming_total / evaluable_total, 2) if evaluable_total else None,
        evaluable_final_route_count=evaluable_total, conforming_final_route_count=conforming_total,
        route_summaries=route_summaries, observations=rows,
    )


def apply_reviews(run, reviews=None):
    """Apply optional human overrides; automatic and human scores stay separate."""
    run = Path(run)
    result = json.loads((run / "result.json").read_text())
    prepared = json.loads((run / "prepared.json").read_text())
    config = json.loads((run / "config.json").read_text())
    review_path = run / "reviews.json"
    if reviews is None:
        reviews = json.loads(review_path.read_text()) if review_path.exists() else []
    candidates = {r["id"]: r for r in result["candidates"]}
    decisions = {(d["route"], d["final_index"]): dict(d) for d in result["decisions"]}
    seen = set()
    for review in reviews:
        key = (review["route"], review["final_index"])
        if key in seen or key not in decisions:
            raise ValueError("Each existing Final/route can have only one review")
        seen.add(key)
        decision = review["decision"]
        candidate_id = review.get("candidate_id")
        if decision not in ("matched", "unmatched", "pending"):
            raise ValueError("Invalid human decision")
        if decision == "matched" and (candidate_id not in candidates or
                (candidates[candidate_id]["route"], candidates[candidate_id]["final_index"]) != key):
            raise ValueError("Selected candidate does not belong to this Final/route")
        decisions[key].update(status="human_confirmed" if decision == "matched" else
                             "insufficient_evidence" if decision == "unmatched" else "requires_review",
                             selected_candidate_id=candidate_id if decision == "matched" else None,
                             decision_source="human", reason=review.get("reason", decision))
    selected = [dict(candidates[d["selected_candidate_id"]], decision_source=d["decision_source"],
                     decision_status=d["status"]) for d in decisions.values() if d.get("selected_candidate_id")]
    final_support, unmatched, pending = [], [], []
    for i, frame in enumerate(prepared["frames"]["final"], 1):
        routes = [d for d in decisions.values() if d["final_index"] == i]
        supports = [r for r in selected if r["final_index"] == i]
        entry = dict(final_index=i, final_path=frame["keyframe_path"],
                     status="supported" if supports else "pending" if any(
                         d["status"] == "requires_review" for d in routes) else "insufficient_evidence",
                     selected_evidence=supports, routes=routes)
        final_support.append(entry)
        if entry["status"] == "pending":
            pending.append(entry)
        elif entry["status"] == "insufficient_evidence":
            unmatched.append(entry)
    human = [r for r in selected if r["decision_source"] == "human"]
    scores = dict(human_confirmed=_scores(prepared["frames"]["final"], human),
                  provisional_and_human=_scores(prepared["frames"]["final"], selected),
                  interpretation="Automatic decisions remain provisional; scores do not measure retrieval accuracy.")
    correspondence = dict(
        human_confirmed=_correspondence_diagnostics(config, prepared, human),
        provisional_and_human=_correspondence_diagnostics(config, prepared, selected),
    )
    diagnostics = {}
    for scope in ("human_confirmed", "provisional_and_human"):
        diagnostics[scope] = []
        for order in scores[scope]["route_order"]:
            sequence = order["index_sequence"]
            diagnostics[scope].append(dict(route=order["route"], index_sequence=sequence,
                adjacent_events=[dict(previous=a, current=b, delta=b-a,
                    relation="backtrack" if b < a else "repeat" if b == a else
                             "forward_gap" if b > a + 1 else "forward")
                    for a, b in zip(sequence, sequence[1:])],
                pairwise_inversion_count=order["discordant_pair_count"],
                interpretation="Backtracks and gaps require context; they may reflect a wrong match or sampling."))
    triangle = []
    supplementary = {(r["animatic_index"], r["storyboard_index"]): r for r in result["supplementary"]}
    for final in final_support:
        by_route = {r["route"]: r for r in final["selected_evidence"]}
        if "final_storyboard" in by_route and "final_animatic" in by_route:
            key = (by_route["final_animatic"]["evidence_index"], by_route["final_storyboard"]["evidence_index"])
            row = supplementary.get(key)
            triangle.append(dict(final_index=final["final_index"], animatic_index=key[0],
                storyboard_index=key[1], supplementary_candidate_present=bool(row),
                supplementary_rank=row["visual_rank"] if row else None,
                status="supporting_context_only", affects_acceptance=False))
    for name, value in (("reviews", reviews), ("matched_list", selected), ("unmatched_list", unmatched),
                        ("pending_list", pending), ("final_support", final_support),
                        ("effective_decisions", list(decisions.values())), ("evidence_scores", scores),
                        ("correspondence_diagnostics", correspondence),
                        ("sequence_index_diagnostics", diagnostics), ("triangle_diagnostics", triangle)):
        save_json(run / f"{name}.json", value)
    return scores


def run_pipeline(config_path):
    config = load_config(config_path)
    prepared = prepare(config)
    result = retrieve(config, prepared)
    if config.get("inspect_provenance", True):
        inspect_provenance(config, prepared)
    return result
