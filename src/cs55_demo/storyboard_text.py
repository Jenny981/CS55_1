"""Map reviewed storyboard panels to nearby PDF text blocks.

This uses document layout only. Extracted descriptions remain submitted text;
they are not ground truth and do not verify a production relationship.
"""
from pathlib import Path
import hashlib
import json
import platform
import re
import subprocess
import tempfile

import fitz
from PIL import Image


SHOT_PATTERN = re.compile(r"\bShot\s*\d+\s*:?", re.IGNORECASE)


def _vertical_overlap(a, b):
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def _clean(text):
    return " ".join(text.split())


def annotate_shared_text_groups(records):
    """Attach stable many-to-many text groups to panel text records.

    Records that point to the same extracted PDF block share one text group.
    OCR-only records may share a group when their normalized text on the same
    page is identical. Missing text remains panel-specific. This metadata lets
    retrieval encode and rank a submitted description once, then project that
    auxiliary evidence onto every panel linked to it.
    """
    annotated = [dict(record) for record in records]
    grouped = {}
    for position, record in enumerate(annotated):
        description = _clean(record.get("description") or "")
        bbox = record.get("description_block_bbox")
        if description and bbox:
            rounded_bbox = tuple(round(float(value), 2) for value in bbox)
            identity = ("pdf_block", int(record["page_index"]), rounded_bbox,
                        description.casefold())
        elif description:
            identity = ("ocr_text", int(record["page_index"]),
                        description.casefold())
        else:
            identity = ("missing", int(record.get("storyboard_index", position + 1)))
        grouped.setdefault(identity, []).append(position)

    for identity, positions in grouped.items():
        digest = hashlib.sha256(
            json.dumps(identity, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:12]
        group_id = f"text_{digest}"
        panel_indices = [
            int(annotated[position].get("storyboard_index", position + 1))
            for position in positions
        ]
        shared = len(panel_indices) > 1
        for position in positions:
            annotated[position].update({
                "text_group_id": group_id,
                "shared_panel_indices": panel_indices,
                "shared_panel_count": len(panel_indices),
                "text_evidence_scope": "shared" if shared else "panel_specific",
            })
    return annotated


def _vision_ocr(image):
    """Use macOS Vision with automatic language detection when available."""
    if platform.system() != "Darwin":
        return [], "ocr_unavailable_on_this_platform"
    binary = Path(__file__).with_name("vision_ocr")
    if not binary.is_file():
        return [], "ocr_helper_missing"
    with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
        image.save(temporary.name)
        completed = subprocess.run([str(binary), temporary.name], capture_output=True,
                                   text=True, timeout=120, check=False)
    if completed.returncode != 0:
        return [], "ocr_failed"
    try:
        items = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return [], "ocr_invalid_output"
    items = [item for item in items if _clean(item.get("text", ""))]
    return items, "macos_vision_automatic_language"


def _ocr_right_of_panel(page, panel, sx, sy):
    """OCR only the row to the right of the visual panel."""
    pix = page.get_pixmap(matrix=fitz.Matrix(sx, sy), alpha=False)
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    left = max(0, min(image.width, round(panel.x1*sx)))
    top = max(0, min(image.height, round(panel.y0*sy)))
    bottom = max(top, min(image.height, round(panel.y1*sy)))
    if left >= image.width or top >= bottom:
        return None, None, "ocr_region_empty", []
    region = image.crop((left, top, image.width, bottom))
    items, method = _vision_ocr(region)
    description = _clean(" ".join(item["text"] for item in items)) or None
    confidence = (sum(float(item.get("confidence", 0)) for item in items) / len(items)
                  if items else None)
    return description, confidence, method, items


def extract_panel_descriptions(pdf_path, panel_records):
    """Return one record per reviewed panel, preserving input order.

    Panel bounding boxes are in rendered-page pixels. Their scale is inferred
    from the PDF page and rendered page dimensions recorded during review.
    Narrative text is selected from blocks to the right of the panel with
    vertical overlap. Shot labels are selected independently.
    """
    pdf_path = Path(pdf_path).resolve()
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)
    records = list(panel_records)
    results = []
    with fitz.open(pdf_path) as document:
        for storyboard_index, record in enumerate(records, 1):
            page_index = int(record["page_index"])
            if not 1 <= page_index <= len(document):
                raise ValueError(f"Invalid page_index: {page_index}")
            box = record.get("bbox")
            if not isinstance(box, (list, tuple)) or len(box) != 4:
                raise ValueError("Every panel requires bbox [left, top, right, bottom]")
            page = document[page_index - 1]
            # Review pages are rendered at Matrix(2, 2). Infer the actual
            # ratio instead of hard-coding it, so integer rounding is handled.
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            sx, sy = pix.width / page.rect.width, pix.height / page.rect.height
            panel = fitz.Rect(box[0] / sx, box[1] / sy, box[2] / sx, box[3] / sy)
            blocks = []
            for raw in page.get_text("blocks"):
                block = fitz.Rect(raw[:4])
                value = _clean(raw[4])
                if value:
                    blocks.append((block, value))

            narrative = []
            all_labels = []
            for block, value in blocks:
                overlap = _vertical_overlap(panel, block)
                if SHOT_PATTERN.search(value):
                    all_labels.append((block.y0, value, block))
                elif overlap > 0 and block.x0 >= panel.x1 - 8:
                    narrative.append((overlap, block.y0, value, block))

            narrative.sort(key=lambda item: (-item[0], item[1]))
            description = narrative[0][2] if narrative else None
            ocr_confidence, ocr_items = None, []
            mapping_method = "same_page_right_block_with_vertical_overlap"
            if not description:
                description, ocr_confidence, mapping_method, ocr_items = \
                    _ocr_right_of_panel(page, panel, sx, sy)
            # Labels sit just above the image region in this common layout and
            # may not overlap the image rectangle. Pair by row start instead.
            row_y = narrative[0][3].y0 if narrative else panel.y0
            labels = sorted(all_labels, key=lambda item: abs(item[0] - row_y))
            max_label_distance = max(20.0, panel.height * 0.5)
            label_text = labels[0][1] if labels and abs(labels[0][0] - row_y) <= max_label_distance else None
            label_match = SHOT_PATTERN.search(label_text or "")
            results.append({
                "storyboard_index": storyboard_index,
                "page_index": page_index,
                "panel_index": int(record["panel_index"]),
                "panel_path": str(record["panel_path"]),
                "shot_label": label_match.group(0).rstrip(":").strip() if label_match else None,
                "description": description,
                "text_mapping_status": ("mapped_ocr" if description and mapping_method.startswith("macos_vision")
                                        else "mapped" if description else "missing_text"),
                "description_block_bbox": list(narrative[0][3]) if narrative else None,
                "mapping_method": mapping_method,
                "ocr_average_confidence": ocr_confidence,
                "ocr_items": ocr_items,
            })
    return annotate_shared_text_groups(results)


def select_joint_topk_matches(candidate_rows, final_records, top_k=5):
    """Select at most one Storyboard match per Final from rank intersection.

    A pair qualifies only when both independent ranks are within ``top_k``.
    Visual rank is the primary ordering; text rank and Storyboard index break
    ties. This is rank-agreement automation, not correctness calibration.
    """
    if not isinstance(top_k, int) or top_k < 1:
        raise ValueError("top_k must be a positive integer")
    final_records = list(final_records)
    qualified = []
    for row in candidate_rows:
        image_rank = row.get("image_rank")
        text_rank = row.get("text_rank")
        if image_rank is None or text_rank is None:
            continue
        if int(image_rank) <= top_k and int(text_rank) <= top_k:
            qualified.append({**row, "status": "rank_agreement_candidate"})
    qualified.sort(key=lambda row: (
        int(row["final_index"]), int(row["image_rank"]),
        int(row["text_rank"]), int(row["storyboard_index"])
    ))
    selected = []
    seen = set()
    for row in qualified:
        final_index = int(row["final_index"])
        if final_index in seen:
            continue
        selected.append({**row, "status": "automatic_rank_agreement_match"})
        seen.add(final_index)
    skipped = []
    for final_index, record in enumerate(final_records, 1):
        if final_index not in seen:
            skipped.append({
                "final_index": final_index,
                "final_timestamp_sec": float(record["timestamp_sec"]),
                "final_path": str(record["keyframe_path"]),
                "status": "skipped",
                "reason": f"no_storyboard_in_both_top_{top_k}",
            })
    return qualified, selected, skipped


def select_visual_primary_auxiliary_matches(
        candidate_rows, final_records, strong_visual_top_k=5,
        broad_visual_top_k=20, auxiliary_top_k=10,
        max_candidates_per_final=3):
    """Use strong visual evidence or visual-plus-auxiliary evidence.

    A candidate qualifies either when visual rank is within the strict visual
    threshold, or when visual rank is within the broader threshold and text or
    valid structure rank is within the auxiliary threshold. No raw scores are
    fused. Up to ``max_candidates_per_final`` candidates are retained for
    inspection, while the best candidate is selected for temporal analysis.
    """
    settings = (strong_visual_top_k, broad_visual_top_k, auxiliary_top_k,
                max_candidates_per_final)
    if any(not isinstance(value, int) or value < 1 for value in settings):
        raise ValueError("All rank thresholds and candidate limits must be positive integers")
    if strong_visual_top_k > broad_visual_top_k:
        raise ValueError("strong_visual_top_k cannot exceed broad_visual_top_k")
    finals = list(final_records)
    qualified = []
    for original in candidate_rows:
        row = dict(original)
        image_rank = row.get("image_rank")
        text_rank = row.get("text_rank")
        structure_rank = row.get("structure_rank")
        strong_visual_ok = (
            image_rank is not None and int(image_rank) <= strong_visual_top_k
        )
        broad_visual_ok = (
            image_rank is not None and int(image_rank) <= broad_visual_top_k
        )
        text_ok = text_rank is not None and int(text_rank) <= auxiliary_top_k
        structure_ok = (
            structure_rank is not None and int(structure_rank) <= auxiliary_top_k
        )
        joint_ok = broad_visual_ok and (text_ok or structure_ok)
        if not (strong_visual_ok or joint_ok):
            continue
        routes = []
        if text_ok:
            routes.append("text")
        if structure_ok:
            routes.append("structure")
        if strong_visual_ok:
            confidence_tier = "strong_support"
            support_routes = "strong_visual"
            if routes:
                support_routes += "+" + "+".join(routes)
        else:
            confidence_tier = "possible_support"
            support_routes = "visual+" + "+".join(routes)
        row.update(
            support_routes=support_routes,
            confidence_tier=confidence_tier,
            strong_visual_passed=bool(strong_visual_ok),
            text_gate_passed=bool(text_ok),
            structure_gate_passed=bool(structure_ok),
            status="tiered_retrieval_candidate",
        )
        qualified.append(row)

    def auxiliary_rank(row):
        ranks = [row.get("text_rank"), row.get("structure_rank")]
        available = [int(rank) for rank in ranks if rank is not None]
        return min(available, default=10**9)

    qualified.sort(key=lambda row: (
        int(row["final_index"]),
        0 if row["confidence_tier"] == "strong_support" else 1,
        int(row["image_rank"]),
        -int(row["text_gate_passed"] and row["structure_gate_passed"]),
        auxiliary_rank(row), int(row["storyboard_index"]),
    ))
    retained, selected, counts = [], [], {}
    for row in qualified:
        final_index = int(row["final_index"])
        count = counts.get(final_index, 0)
        if count >= max_candidates_per_final:
            continue
        retained.append({**row, "candidate_rank_for_final": count + 1})
        counts[final_index] = count + 1
        if count == 0:
            selected.append({**row, "candidate_rank_for_final": 1,
                             "status": "automatic_tiered_rank_match"})
    seen = set(counts)
    skipped = []
    for final_index, record in enumerate(finals, 1):
        if final_index not in seen:
            skipped.append({
                "final_index": final_index,
                "final_timestamp_sec": float(record["timestamp_sec"]),
                "final_path": str(record["keyframe_path"]),
                "status": "skipped",
                "reason": (
                    f"no_visual_top_{strong_visual_top_k}_or_visual_top_"
                    f"{broad_visual_top_k}_with_auxiliary_top_{auxiliary_top_k}"
                ),
            })
    return retained, selected, skipped
