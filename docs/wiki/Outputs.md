# Outputs and reproducibility

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

Record input identities, configuration, model name, sampling windows, confirmed panel order, correspondence declarations and review overrides together. Generated outputs and local material paths should not be committed to a public repository. Export required results before clearing cache.

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
