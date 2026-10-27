"""Run the same pipeline used by the notebook."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from cs55_demo.system import run_pipeline, apply_reviews

parser = argparse.ArgumentParser()
parser.add_argument("--config", type=Path)
parser.add_argument("--review-run", type=Path)
parser.add_argument("--reviews", type=Path)
args = parser.parse_args()
if args.review_run:
    if not args.reviews:
        parser.error("--review-run requires --reviews")
    scores = apply_reviews(args.review_run, json.loads(args.reviews.read_text()))
    print(json.dumps(scores, indent=2))
elif args.config:
    result = run_pipeline(args.config)
    print("Results:", result["run_dir"])
else:
    parser.error("Provide --config or --review-run with --reviews")
