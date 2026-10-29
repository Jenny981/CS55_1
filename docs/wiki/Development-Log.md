# Development log and design decisions

## Reading this log
This is a retrospective engineering log reconstructed from project discussions and the current documented implementation. Periods below identify discussion milestones, not verified release or commit dates. The inspected local Git history contains only an initial recoverable demo snapshot dated 23 September 2026 (`87d8e36`); it cannot substantiate a commit for every later change. No quantitative performance improvement is asserted without a controlled evaluation.

| Discussion period | Problem and decision | Outcome / status |
|---|---|---|
| September–early October 2026 | Extend content matching with hashes, metadata, timestamps, C2PA, software, projects and editing history. | Shared evidence extraction and separate provenance rubrics are documented in the current system. |
| Early–mid October | Fixed dataset layouts and stage assumptions limited new material inputs. | Move toward configurable materials and shared modules; extraction remains format-sensitive and should not be called universal. |
| 16 October | Colour/change-based shot detection and fixed panel rules were unreliable for new storyboards. | Time sampling, trim windows, blank-frame filtering and editable panel preparation became core workflow controls. |
| 16 October | CLIP confused sparse sketches and blank/dark frames; small subjects remained hard to identify. | DINO, structural features, local matching and subject crops were explored. These experiments are not all active production methods. Current documented retrieval is CLIP-led with optional text reranking and structural diagnostics. |
| 16–20 October | Mandatory sequence constraints could conceal evidence reordering. | Final-led retrieval retains index regressions; subsequent order diagnostics report contradictions rather than enforcing a monotonic path. |
| 19–22 October | Review cost, descriptions, optional evidence types and large-file handling needed attention. | Candidate selection, shared panel text, separate Final routes, local paths and bounded display handling support the review workflow. |
| 20–27 October | Scores needed explicit reasons and provenance/timestamp interpretation. | Independent rubric checks and timestamp availability, chronology and proximity explanations were introduced. Missing support is distinguished from proof of fabrication. |
| 22–27 October | Notebook workflows needed reusable execution and a usable interface. | Shared Python package, CLI, notebook and React/shadcn/Radix interface documented; Streamlit remains an alternative. |
| 27 October | Restricting retrieval to correspondence intervals hid disagreement with the declaration. | Retrieve globally, then compare with declared intervals; keep conforming, outside, unobserved and undeclared states. |
| 27–28 October | Automatic panel extraction remained imperfect; results needed clearer explanations. | Restore editable panel review; document cache clearing, score explanations and output semantics. |
| 28–29 October | Team handover needed a consistent system explanation. | Bilingual Word guides and a system-wide bilingual Wiki prepared, including purpose, scoring limits and this log. |

## Important decisions retained
1. Final is the query reference, not a declaration that all Final content is authentic.
2. A candidate list and a confirmed relationship are different objects.
3. One Final may have one selected match per evidence route; the same evidence may support multiple Final samples.
4. Text can support multiple panels and only reranks a restricted visual shortlist.
5. Correspondence is a post-retrieval baseline, not automatically verified ground truth.
6. Order, support coverage and provenance are separate measurements, not matching accuracy.
7. A local structure diagnostic or supplementary triangle does not independently establish a correct match.

## Open work
- Build a held-out annotated evaluation set and measure actual retrieval and review effort.
- Calibrate thresholds and test sparse, blurred and distant-subject cases.
- Improve multilingual text extraction and unusual page layouts with explicit failure reporting.
- Strengthen project-file relationship verification and timestamp-source interpretation.
- Record future changes with commit links, affected modules and actual validation evidence.

## Future entry template
```text
Date / commit:
Problem:
Changed behavior:
Affected modules:
Validation performed and observed result:
Known limitations / follow-up:
```
Do not backfill unverified dates, test results or improvement percentages.

---
[Wiki Home](Home.md) · Updated: 29 October 2026
