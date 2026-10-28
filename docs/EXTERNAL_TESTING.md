# CS55 external testing guide

Updated 28 October 2026. This guide describes the implementation in this repository. Record your exact commit when testing; a separate local development copy may differ.

## Purpose and current behavior

The system compares sampled Final video frames with Storyboard panels and Animatic frames. It retrieves evidence globally, optionally reranks close visual candidates with available text, and compares selected relationships with submitter-declared correspondence ranges.

Global Top-1 mode saves provisional selections automatically when minimum visual similarity is met. Human corrections are optional. Strict support checks are available for a more conservative selection policy. Storyboard extraction produces candidate boxes. In Panel review, check every page, keep or exclude boxes, adjust boundaries and order, or add missing boxes. Confirm panel extraction before matching. Confirmation re-crops panels and refreshes their text and IDs; use the confirmed catalog when declaring correspondence.

The team has used Lumia-generated materials in its own testing. Independent tests are welcome to identify failure cases beyond those tests. No accuracy improvement or reliable AI-forgery detection is claimed.

## Get the version and start the application

For a new checkout:

```bash
git clone https://github.com/Jenny981/CS55_1.git
cd CS55_1
```

For an existing checkout, preserve your local changes before updating:

```bash
git pull --ff-only
```

Record the version:

```bash
git rev-parse HEAD
```

Create and activate a Python environment, then install dependencies:

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Windows PowerShell:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

With a compatible Node.js installation, build and start:

```bash
cd frontend
npm ci
npm run build
cd ..
python web_server.py
```

Open http://localhost:8505. Rebuild the frontend after pulling frontend changes and restart the Python server after backend changes. Initial CLIP use may download model weights. FFprobe is recommended for video metadata; optional C2PA tooling and OCR availability affect extracted evidence. See the main README for those dependencies.

## Run a baseline

1. In Materials, select a Final video and at least one Storyboard PDF or Animatic video. For large files, use local paths on the server machine.
2. Record sampling start, end and interval settings, then prepare the materials.
3. If a Storyboard is submitted, complete Panel review and click Confirm panel extraction. Inspect the confirmed catalog and sample timestamps. Extraction mistakes should be reported separately from matching mistakes.
4. Optionally declare expected evidence-to-Final intervals in Correspondence. Use original-video timestamps and exported panel IDs. Declarations are a comparison baseline, not verified ground truth or search restrictions.
5. Run matching with recorded settings. Save automatic results before applying any human correction.
6. Inspect Assessment and Provenance and download the JSON results.

## Suggested independent tests

Change one factor at a time and keep the baseline results.

| Case | Change | What to inspect |
| --- | --- | --- |
| Reversed Storyboard | Reverse actual panel/page order in the submitted PDF; inspect extracted IDs | Selected evidence indices, inversions and sequence consistency |
| Reversed Animatic | Submit an Animatic with its actual content order reversed | Selected frame indices and temporal diagnostics |
| Mismatched evidence | Substitute evidence from another scene or work | Misleading automatic selections, visual-support coverage and low-support cases |
| Similar AI-generated evidence | Use Lumia-generated process-like materials resembling the Final | Whether similarity produces apparently strong support without establishing genuine production history |
| Incorrect correspondence | Keep assets fixed but change the declared ranges | Outside-baseline selections and conformance; declarations should not restrict global retrieval |
| Ambiguous or repeated images | Repeat or use similar panels | Repeated selections, candidate ambiguity and differences between automatic and strict modes |
| Independent setup | Follow the instructions on another machine | Missing dependencies, startup problems and unclear instructions |

Temporal diagnostics are observations, not guaranteed rejection rules. Reversal will not necessarily lower a score if matching fails, selected indices are tied, or too few comparable matches exist. Sequence scoring requires at least three selected matches and a non-tied comparison.

Reordering an externally selected Final-frame list alone does not change this pipeline's input: it samples the submitted Final video directly. To test input order, change the actual submitted evidence content. If changing panel order, record whether text and image remain paired. Keep the Final fixed for evidence-order tests.

## Interpret the outputs

- Visual similarity is an embedding similarity, not a confidence probability.
- Visual support is the fraction of retained sampled Final frames supported by at least one selected evidence route. It does not measure verified matching accuracy.
- Sequence consistency describes ordering among selected evidence indices; it does not prove a production relationship.
- Correspondence conformance measures agreement with submitted declarations. A disagreement can indicate an incorrect declaration or an incorrect match. Undeclared intervals are not evaluable for this metric.
- Provenance indicators are independent checks of available evidence. Missing C2PA does not establish fabrication; a complete file hash does not establish authorship.
- The Final is the reference for comparison. Its authenticity and the claimed production relationships are not assumed independently verified.

## Generated cache

The sidebar Clear cache action shows generated storage usage and asks for confirmation before removing generated runs, sampled frames, panels, uploaded copies and JSON results from outputs/. Download needed results first. It preserves source files referenced by local paths, dependencies and model weights, and is disabled during processing.

## Report a finding

Open an issue at https://github.com/Jenny981/CS55_1/issues or reply in the existing Discord discussion with:

- Commit SHA, operating system and relevant dependency/tool availability.
- Baseline and modified inputs, or a reproducible description if files cannot be shared.
- Exact manipulation and expected behavior.
- Sampling, selection policy, thresholds and correspondence declarations, preferably via exported config.json.
- Actual behavior, affected Final timestamps and screenshots/errors where useful.
- Relevant exports: result.json, correspondence_diagnostics.json, sequence_index_diagnostics.json, evidence_scores.json, and provenance outputs for provenance findings.
- Whether human overrides were applied; include reviews.json if applicable.

Share only material you are permitted to distribute. A finding is useful even if no score changes: please explain which behavior was misleading or difficult to understand.
