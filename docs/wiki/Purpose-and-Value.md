# Purpose, value and scope

## The problem
Reviewers receive a completed video alongside heterogeneous production materials. Finding relevant evidence, tracing the sequence and distinguishing missing records from contradictions requires substantial manual work. A similarity value alone does not explain how a material supports the Final.

## What CS55 contributes
- **Final-led evidence organization:** starts with retained Final samples and identifies supporting Storyboard or Animatic candidates. Missing material types remain visible.
- **Focused review:** presents ranked candidates, panel descriptions and editable selections rather than requiring reviewers to search every possible pair manually.
- **Observable disagreements:** keeps global retrieval independent of declared correspondence, allowing outside-baseline results and index regressions to remain visible.
- **Complementary evidence:** visual support, sequence, correspondence, provenance and timestamps answer different questions. Independent scores preserve these distinctions.
- **Traceable explanations:** records automatic versus human decisions, observed values, individual scoring checks and reasons in exportable JSON.
- **Shared implementation:** notebook, CLI and interfaces call common Python modules, reducing duplicated algorithm implementations.

## Who can use it
Students and production teams can organize evidence submissions; supervisors and clients can locate material requiring explanation; developers can reproduce decisions and evaluate retrieval behavior. The intended value is review assistance and accountable reporting.

## What a result means
A selection suggests visual support under the configured rules. A sequence conflict identifies an ordering inconsistency in selected indices. A correspondence deviation identifies disagreement with a declaration. Provenance and timestamp checks describe available support and contradictions. These observations require contextual interpretation.

## Limits and evidence needed
The current system does not certify authorship, detect all AI-generated content, prove fabrication or establish historical file integrity merely by computing a hash. Automatic selections remain provisional. Thresholds and rubric weights are design choices requiring validation.

Reduced workload and improved accuracy are intended benefits, not measured claims. Validate them with independently labeled held-out examples, Top-1 correctness, Top-K recall, appropriate abstention, reviewer correction rate and time per submission. Compare methods under the same inputs, settings and review budget.

## Development priorities
Prioritize reliable panel/text preparation, inspection of ambiguous matches, independently evaluated acceptance rules, stronger source-project verification and clearer evidence-source attribution. Preserve observable uncertainty instead of increasing acceptance solely to raise coverage.

---
[Wiki Home](Home.md) · Updated: 29 October 2026
