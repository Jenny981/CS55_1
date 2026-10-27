"""Best-effort panel extraction and global retrieval decisions."""
import math
from pathlib import Path

import numpy as np
from PIL import Image

from .storyboard_layout import propose_panels, export_reviewed


def extract_automatic_panels(pdf_path, output_root):
    """Keep useful proposals; retain quality reasons and original page order."""
    manifest = propose_panels(pdf_path, output_root)
    for page in manifest["pages"]:
        with Image.open(page["page_path"]) as image:
            for candidate in page["candidates"]:
                x0, y0, x1, y1 = candidate["bbox"]
                reason = "usable_visual_proposal"
                if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
                    reason = "invalid_boundary"
                else:
                    crop = np.asarray(image.crop((x0, y0, x1, y1)).convert("L"))
                    if min(crop.shape) < 32 or crop.size < image.width * image.height * .005:
                        reason = "too_small"
                    elif float(crop.std()) < 3 or float((crop >= 250).mean()) > .995:
                        reason = "insufficient_visual_information"
                accepted = reason == "usable_visual_proposal"
                candidate.update(decision="accept" if accepted else "reject",
                                 decision_source="automatic_quality_filter",
                                 quality_reason=reason, needs_boundary_review=False)
        # This flag authorizes export, not a claim of human approval.
        page.update(reviewed=True, review_source="automatic_quality_filter")
        page["extraction_status"] = ("panels_available" if any(
            c["decision"] == "accept" for c in page["candidates"])
            else "not_extracted")
    records = export_reviewed(manifest) if any(
        c["decision"] == "accept" for p in manifest["pages"] for c in p["candidates"]
    ) else []
    for page in manifest["pages"]:
        accepted = [c for c in page["candidates"] if c["decision"] == "accept"]
        for record, candidate in zip(
                [r for r in records if r["page_index"] == page["page_index"]], accepted):
            # Preserve pre-filter ID: exclusions must not renumber later panels.
            record["evidence_index"] = sum(len(p["candidates"]) for p in manifest["pages"]
                                           if p["page_index"] < page["page_index"]) + \
                page["candidates"].index(candidate) + 1
            record["review_status"] = "automatically_extracted"
            record["decision_source"] = "automatic_quality_filter"
    return records, manifest


def validate_ranges(ranges):
    """Validate explicit mappings; no matches are inferred from array order."""
    for number, item in enumerate(ranges, 1):
        if item.get("evidence_type") not in ("storyboard", "animatic"):
            raise ValueError(f"Range {number}: invalid evidence_type")
        start, end = item.get("final_start_sec"), item.get("final_end_sec")
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                   and math.isfinite(v) for v in (start, end)) or not 0 <= start < end:
            raise ValueError(f"Range {number}: Final range must satisfy 0 <= start < end")
        if item["evidence_type"] == "storyboard":
            ids = item.get("panel_indices", [])
            if not ids or any(type(i) is not int or i < 1 for i in ids):
                raise ValueError(f"Range {number}: positive panel_indices required")
        else:
            a, b = item.get("evidence_start_sec"), item.get("evidence_end_sec")
            if not all(isinstance(v, (int, float)) and not isinstance(v, bool)
                       and math.isfinite(v) for v in (a, b)) or not 0 <= a < b:
                raise ValueError(f"Range {number}: invalid Animatic time range")


def allowed_evidence(final_record, evidence, evidence_type, ranges, require_ranges=True):
    relevant = [(i, r) for i, r in enumerate(ranges, 1)
                if r["evidence_type"] == evidence_type]
    timestamp = float(final_record["timestamp_sec"])
    active = [(i, r) for i, r in relevant
              if r["final_start_sec"] <= timestamp < r["final_end_sec"]]
    allowed = {}
    if not active and not require_ranges and not relevant:
        return {i: [] for i in range(len(evidence))}
    for i, record in enumerate(evidence):
        ids = []
        for range_id, rule in active:
            if evidence_type == "storyboard":
                found = record["evidence_index"] in rule["panel_indices"]
            else:
                found = (rule["evidence_start_sec"] <= record["timestamp_sec"]
                         < rule["evidence_end_sec"])
            if found:
                ids.append(range_id)
        if ids:
            allowed[i] = ids
    return allowed


def rerank_with_text(rows, settings):
    """Text breaks close visual alternatives using ranks, without adding raw scores."""
    rows = [dict(row) for row in rows]
    if not rows:
        return rows
    best = max(row["visual_similarity"] for row in rows)
    maximum_loss = settings.get("text_max_visual_loss", .05)
    shortlist = settings.get("text_visual_shortlist", 5)
    eligible = [row for row in rows if row["visual_rank"] <= shortlist
                and best - row["visual_similarity"] <= maximum_loss]
    use_text = (settings.get("use_text_reranking", True)
                and len({r.get("text_group_id") for r in eligible if r.get("text_group_rank")}) > 1)
    for row in rows:
        row["text_reranking_applied"] = bool(use_text and row in eligible)
        row["retrieval_rank_score"] = (1 / row["visual_rank"] +
            settings.get("text_rank_weight", 1.25) / row["text_group_rank"]
            if row["text_reranking_applied"] and row.get("text_group_rank") else
            1 / row["visual_rank"])
    eligible_ids = {row["id"] for row in eligible}
    rows.sort(key=lambda row: (0 if row["id"] in eligible_ids else 1,
                              -row["retrieval_rank_score"], row["visual_rank"]))
    for rank, row in enumerate(rows, 1):
        row["retrieval_rank"] = rank
    return rows


def select_top1(rows, settings):
    """Top-1 is provisional only when explicit support checks pass."""
    if not rows:
        return {"status": "insufficient_evidence", "reason": "no_candidate_available",
                "selected_candidate_id": None}
    rows = sorted(rows, key=lambda r: (r.get("retrieval_rank", r.get("visual_rank", 1)),
                                     -r["visual_similarity"], r["evidence_index"]))
    first = rows[0]
    runner_score = (rows[1]["visual_similarity"] if len(rows) > 1
                    else first.get("runner_up_visual_similarity"))
    margin = first["visual_similarity"] - runner_score if runner_score is not None else None
    supported = bool(first.get("text_supported") or first.get("structure_supported")
                     or first.get("neighbor_supported"))
    reason = "top1_passed_configured_support_checks"
    status = "provisionally_matched"
    if first["visual_similarity"] < settings["min_visual_similarity"]:
        status, reason = "insufficient_evidence", "visual_support_below_threshold"
    elif settings.get("acceptance_mode", "strict") == "range_top1":
        reason = "global_top1_automatically_selected"
    elif margin is not None and margin < settings["min_top1_margin"]:
        status, reason = "requires_review", "top1_top2_ambiguous"
    elif settings.get("require_auxiliary_support", True) and not supported:
        status, reason = "requires_review", "no_independent_support"
    return dict(status=status, reason=reason,
                selected_candidate_id=first["id"] if status == "provisionally_matched" else None,
                proposed_candidate_id=first["id"], top1_margin=margin,
                acceptance_mode=settings.get("acceptance_mode", "strict"),
                acceptance_basis="configurable_uncalibrated_heuristics")
