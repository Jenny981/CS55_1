# Retrieval and human review

For each retained Final frame, rank CLIP visual similarities across all extracted evidence for that route. Text descriptions are encoded once per text group and may support multiple panels. For the top five visual candidates within 0.05 of the best visual similarity, text may change the order using reciprocal ranks: `1 / visual_rank + 1.25 / text_group_rank`. The text contribution is enabled only when multiple distinct text groups are present. Scores are used to order candidates, not as calibrated confidence values. Valid local structure and neighbouring candidates remain supporting diagnostics. No monotonic matching path is imposed, so evidence-index regressions remain observable.

Default `range_top1` (shown as Global Top-1 in the UI for backward configuration compatibility) automatically selects the global best candidate after optional text reranking, provided minimum visual similarity is met. The selected pair is then compared with active correspondence declarations. Small score margins or missing auxiliary evidence do not require human approval in this mode. Continuous reuse is recorded as a warning. Optional `strict` mode additionally checks Top-1/Top-2 separation, auxiliary support and consecutive reuse, sending uncertainty to review. Current thresholds and rank weights are configurable heuristics and have not been calibrated against labeled validation data. More automatic acceptance does not demonstrate higher matching accuracy.

Animatic-to-Storyboard candidates provide supplementary context. They do not override the primary Final relationships or automatically reject triangle conflicts. Text and structure scores are recorded separately and are not added to raw CLIP scores.

## Review decisions
A Final frame can retain one Storyboard match and one Animatic match. Selecting one does not require selecting the other. Human overrides may confirm a candidate, mark unmatched, or leave pending. Candidate count is not accepted-match count.

Automatic selections are provisional. The system exports both human-confirmed and combined automatic/human score scopes. At Final level, any selected route supplies support; no support with an uncertain route yields pending; otherwise it is insufficient evidence.

```bash
python run_demo.py --review-run outputs/RUN_DIRECTORY --reviews reviews.json
```
Use a candidate ID from the actual run; do not fabricate candidate IDs. See Outputs for the JSON contract.

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
