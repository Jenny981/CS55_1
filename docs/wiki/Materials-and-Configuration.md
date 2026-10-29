# Materials, panels and configuration

1. Locate the project and load configuration.
2. Generate panel candidates and sample videos.
3. Review every Storyboard page and confirm the panel boundaries retained for matching.
4. Inspect the reviewed panel catalog and optionally declare expected Final correspondence ranges.
5. Run global candidate retrieval and provisional Top-1 decisions.
6. Inspect selected, uncertain, and insufficient-evidence lists.
7. Optionally provide human overrides.
8. Inspect independent provenance scores and timestamp comparisons.

Automatic extraction produces suggestions only. Storyboard matching is blocked in the React UI until the user confirms the panel review. The review can accept or exclude proposals, change their order and pixel boundaries, and add manual boxes. Confirmation re-crops the panels and re-extracts descriptions. The resulting `panel_catalog.json` and `panel_manifest.json` preserve the review trail; final panel IDs follow the confirmed page and order sequence.

## Correspondence
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

## Example configuration
```json
{
  "final_path": "data/final.mp4",
  "storyboard_path": "data/storyboard.pdf",
  "animatic_path": null,
  "output_dir": "outputs",
  "model_name": "openai/clip-vit-base-patch32",
  "inspect_provenance": true,
  "sampling": {
    "final": {"interval_sec": 2.0, "start_sec": 0.0, "end_sec": null, "skip_near_blank": true},
    "animatic": {"interval_sec": 2.0, "start_sec": 0.0, "end_sec": null, "skip_near_blank": true}
  },
  "matching": {
    "acceptance_mode": "range_top1",
    "use_text_reranking": true,
    "text_visual_shortlist": 5,
    "text_max_visual_loss": 0.05,
    "text_rank_weight": 1.25,
    "top_k": 5,
    "min_visual_similarity": 0.25,
    "min_top1_margin": 0.02,
    "require_auxiliary_support": true,
    "text_top_k": 10,
    "structure_top_k": 10,
    "structure_candidate_limit": 20,
    "use_structure": true,
    "neighbor_radius": 2,
    "max_consecutive": 5
  },
  "correspondence_ranges": [
    {"evidence_type": "storyboard", "panel_indices": [1, 2, 3], "final_start_sec": 0.0, "final_end_sec": 10.0}
  ]
}
```

The example is a template: replace material paths and declarations. These are heuristic defaults, not validated universal thresholds. `range_top1` is a legacy name for global retrieval, not a range restriction.

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
