# Troubleshooting and validation

| Symptom | Check |
|---|---|
| requirements.txt missing | Change into the actual project directory before creating the environment or installing. |
| Module missing in notebook | Select the same virtual-environment kernel and install requirements with that Python. |
| Port 8505 already occupied | Identify the existing service; reuse it or stop the correct process before restarting. |
| Web page missing after source download | Build `frontend/` using `npm ci` and `npm run build`. |
| Poor panel extraction | Inspect proposals; edit boxes/order, add regions and confirm review before matching. |
| Missing descriptions | Check PDF embedded text and optional OCR availability; no arbitrary-language guarantee is made. |
| Large video upload or memory issue | Use a server-local file path, shorten sampling windows or increase sampling interval. |
| Few samples | Check trim windows and near-blank filtering; inspect saved sample records. |
| High visual coverage but wrong pairs | Coverage measures selections, not correctness. Inspect candidates and apply corrections. |
| C2PA zero | Inspect manifest availability, verification tooling and raw errors; absence is not fabrication. |
| Timestamp N/A | No comparable timestamps may be available. Check both sides and field source. |
| Close-timing deduction zero | Filesystem-only proximity is flagged without an extra deduction. |

## Verification
```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

Tests use synthetic inputs and injected feature vectors; they verify constraints, scoring denominators and decision behavior, rather than measuring model accuracy. Real visual accuracy and auto-accept precision require held-out labeled examples.

For model evaluation, use independently verified held-out pairs. Report Top-1 correctness, Top-K recall, abstention behavior and review effort separately from coverage and ordering. Keep sampling, model, thresholds and review scope fixed when comparing versions. No diagnostic score alone establishes authenticity.

---
[Wiki Home](Home.md) · Documentation snapshot: 29 October 2026
