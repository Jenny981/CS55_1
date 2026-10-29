# Scores and result interpretation

## 5 Visual support coverage

V is the proportion of retained Final samples with at least one selected supporting route. A Final supported on both routes counts once. If 70 of 100 frames have selected evidence, V=70%.

This is neither average CLIP similarity nor retrieval accuracy. An incorrect automatic selection still contributes coverage until corrected.

## 6 Sequence consistency and anomalies

Sort selected evidence indices in Final order and compare every pair. An increasing evidence index is concordant, a decreasing index discordant and an equal index a tie. Ties are excluded. A route needs at least three selected matches and one non-tied comparison to receive a score.

The project score pools C and D across eligible routes instead of averaging route percentages. If one route has C=14, D=0 and another C=0, D=5, the result is 14/19=73.68%.

Adjacent-index events are also recorded as backtrack, repeat, forward_gap or forward. Backtracks may result from reordered evidence or retrieval error; gaps may arise from sampling and editing and do not automatically prove missing material.

The code also exports overall_evidence_score, the harmonic mean 2VQ/(V+Q) when both metrics exist, with zero when both are zero. The current interface mainly displays the separate metrics.

## 7 Correspondence comparison

Correspondence is a user-declared expected relationship checked after retrieval. For example, Final [10,20) seconds may correspond to panels 5–8. Intervals include the start and exclude the end.

Conforming means the selected evidence belongs to the declaration. Outside baseline means a selection outside it. Expected not observed means a declaration exists but no evidence was selected. Undeclared means no declaration covers that Final time and is excluded from the denominator.

A Final declared on both routes contributes two evaluations. Expected evidence coverage measures the fraction of unique declared evidence indices selected anywhere on that route, including at the wrong Final time; it must be interpreted alongside conformance.

Per-frame records include actual and expected indices, declaration IDs, deviation status, reasons and whether the selection belongs to another declaration. Declarations require independent verification before being used as an accuracy benchmark.

## 8 Provenance extraction and independent scores

Each original asset is inspected for SHA 256, metadata, embedded and filesystem timestamps, C2PA, software, project clues and editing events. Video metadata prefers FFprobe with OpenCV fallback. C2PA requires an available verification library or tool.

Each indicator divides awarded points by its applicable maximum and multiplies by 100. Without a C2PA manifest, that indicator is forced to zero; absence of reported errors cannot earn validation credit. The four indicators are not added or averaged into a single provenance score.

A completed hash establishes a fingerprint of the current file. Without a trusted historical reference it cannot prove the file was never modified. Software, times and history are observable clues. Low scores indicate limited support, not proof of fabrication.

| Indicator | Point allocation |
| --- | --- |
| File integrity | SHA 256 completion 70; bytes read 30 |
| C2PA provenance | Manifest 20; valid signature 35; credential trust 20; no validation errors 15; warning condition 10 |
| Source project | Candidate found 25; project hash 25; verified relationship 50 |
| Editing AI transparency | Actions, declared history, timestamps, software and metadata: 20 each |

## 9 Timestamp scoring

Compare Storyboard → Final and Animatic → Final separately. Both timestamps must parse. Weights are embedded creation 35%, embedded modification 30%, filesystem creation 20% and filesystem modification 15%. Missing fields reduce available weight.

Individual chronology scores are 100 when Evidence is not later than Final, 70 when up to 24 hours later, 25 when one to seven days later, and 0 when more than seven days later. A is available weight as a fraction from 0 to 1; C is weighted chronology from 0 to 100.

The base score is A×(30+0.7C). Embedded creation lead time deducts 15 for ≤1 hour, 10 for >1 to 6 hours and 5 for >6 to 24 hours. Absolute embedded modification gaps deduct 5 for <1 hour and 2 for 1–6 hours. Total deduction is capped at 15.

Filesystem-only proximity is reported without deduction because copying, upload, download or batch export can reset these values. With no comparable timestamps the result is N/A. The project score averages available relationship scores and separately records production-chain ordering or rapid-generation signals.

These weights and bands are designed heuristics requiring independent validation. Embedded metadata can also be self-declared; close timing is a review signal and does not establish invalid evidence.

## 10 How to read awarded points and missing values

passed or Satisfied means one specific check was satisfied, not that the entire file is authentic. points_awarded is earned credit and maximum_points is the maximum for that check. Read reason, observed_value, source and explanation together. Without a C2PA manifest, the overall C2PA indicator is gated to zero even if a cleanliness check appears true.

Zero is a calculated zero under a rubric; N/A means no valid score can be formed; Undeclared means no baseline declaration applies. They are not interchangeable. Missing provenance credit may reflect unavailable fields or failed checks; consult extraction data and errors rather than assuming the file contains no such information.

For timestamps, distinguish unearned points from additional deductions. Missing fields limit available credit, chronology reduces earned order credit, and close timing is an additional deduction from the base score. Filesystem-only proximity is reported without an extra deduction, but a filesystem time later than Final may still lower chronology credit.

## 12 Present anomalies without overstating conclusions

For each important anomaly, show Final, selected evidence, expected evidence or range, candidate rank, decision source and the specific deviation. Separate observations, possible causes and unresolved questions. For example: an outside-baseline selection is observed; retrieval error, a declaration issue or editing differences are possible explanations; the cause remains unconfirmed.

Repeated indices may reflect a shot lasting multiple samples; gaps may reflect fixed-interval sampling or unused panels; backtracks may arise from reordering or mismatching. Index diagnostics locate review targets but do not prove omission or tampering. A supplementary triangle also does not automatically validate all three associations.

## Formula reference
```text
Visual coverage = supported distinct Final samples / all retained Final samples * 100
Sequence = concordant / (concordant + discordant) * 100
Correspondence = conforming / declared evaluable Final-route items * 100
Timestamp = max(0, A * (30 + 0.7 * C) - D)
A: comparable timestamp weight, 0..1; C: weighted chronology, 0..100
D: additional proximity deduction, capped at 15
```

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
