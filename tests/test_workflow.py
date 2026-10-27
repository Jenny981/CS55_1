import json
import hashlib
import tempfile
import unittest
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from cs55_demo.automatic import allowed_evidence, validate_ranges, select_top1, extract_automatic_panels, rerank_with_text
from cs55_demo.system import (load_config, retrieve, apply_reviews,
                              apply_panel_review, save_json, _scores)
from cs55_demo.provenance_scoring import timestamp_comparisons


class FakeEncoder:
    def images(self, records):
        return np.array([r["test_vector"] for r in records]) if records else np.empty((0, 2))

    def texts(self, descriptions):
        return np.array([[1., 0.] for _ in descriptions])


class WorkflowTests(unittest.TestCase):
    def test_timestamp_score_combines_availability_chronology_and_proximity(self):
        def asset(created, modified, fs_created, fs_modified):
            return {
                "timestamps": {
                    "media": {"creation_time": created, "modification_time": modified},
                    "filesystem": {"created_at": fs_created, "modified_at": fs_modified},
                },
                "c2pa_manifest": {},
            }

        result = timestamp_comparisons({
            "storyboard": asset("2026-01-01T08:00:00Z", "2026-01-01T11:30:00Z",
                                "2026-01-01T08:00:00Z", "2026-01-01T11:30:00Z"),
            "final": asset("2026-01-01T12:00:00Z", "2026-01-01T12:00:00Z",
                           "2026-01-01T12:00:00Z", "2026-01-01T12:00:00Z"),
        })
        relationship = result["relationships"][0]
        self.assertEqual(relationship["availability_score"], 100.0)
        self.assertEqual(relationship["chronology_consistency"], 100.0)
        self.assertEqual(relationship["base_timestamp_score"], 100.0)
        self.assertEqual(relationship["proximity_deduction"], 15.0)
        self.assertEqual(relationship["timestamp_score"], 85.0)
        self.assertTrue(relationship["review_recommended"])

    def test_timestamp_missingness_caps_score_and_filesystem_proximity_does_not_deduct(self):
        result = timestamp_comparisons({
            "animatic": {
                "timestamps": {"media": {}, "filesystem": {
                    "created_at": "2026-01-01T11:30:00Z", "modified_at": "2026-01-01T11:45:00Z"}},
                "c2pa_manifest": {},
            },
            "final": {
                "timestamps": {"media": {}, "filesystem": {
                    "created_at": "2026-01-01T12:00:00Z", "modified_at": "2026-01-01T12:00:00Z"}},
                "c2pa_manifest": {},
            },
        })
        relationship = result["relationships"][0]
        self.assertEqual(relationship["availability_score"], 35.0)
        self.assertEqual(relationship["proximity_deduction"], 0.0)
        self.assertEqual(relationship["timestamp_score"], 35.0)

    def test_timestamp_full_chain_reports_rapid_generation(self):
        def asset(hour):
            value = f"2026-01-01T{hour:02d}:00:00Z"
            return {"timestamps": {"media": {"creation_time": value}, "filesystem": {}},
                    "c2pa_manifest": {}}

        result = timestamp_comparisons({"storyboard": asset(8), "animatic": asset(9), "final": asset(10)})
        self.assertEqual(result["production_chain_analysis"]["status"], "rapid_full_chain_generation")
        self.assertTrue(result["production_chain_analysis"]["review_recommended"])

    def test_timestamp_filesystem_chain_does_not_claim_rapid_creation(self):
        def asset(hour):
            value = f"2026-01-01T{hour:02d}:00:00Z"
            return {"timestamps": {"media": {}, "filesystem": {"created_at": value}},
                    "c2pa_manifest": {}}

        result = timestamp_comparisons({"storyboard": asset(8), "animatic": asset(8), "final": asset(8)})
        chain = result["production_chain_analysis"]
        self.assertEqual(chain["status"], "filesystem_chain_proximity_observed")
        self.assertIn("copying", chain["reason"])

    def test_text_changes_choice_only_for_close_visual_candidates(self):
        rows = [dict(id="a", evidence_index=1, visual_rank=1, visual_similarity=.80,
                     text_group_id="a", text_group_rank=2, declared_range_ids=[1]),
                dict(id="b", evidence_index=2, visual_rank=2, visual_similarity=.79,
                     text_group_id="b", text_group_rank=1, declared_range_ids=[1])]
        ranked = rerank_with_text(rows, {})
        self.assertEqual(ranked[0]["id"], "b")
        self.assertTrue(ranked[0]["text_reranking_applied"])
        choice = select_top1(ranked, dict(acceptance_mode="range_top1", min_visual_similarity=.25))
        self.assertEqual(choice["selected_candidate_id"], "b")
        rows[1]["visual_similarity"] = .5
        self.assertEqual(rerank_with_text(rows, {})[0]["id"], "a")

    def test_range_mode_does_not_require_manual_acceptance_for_ambiguity(self):
        rows = [dict(id="a", evidence_index=1, visual_rank=1, visual_similarity=.8,
                     declared_range_ids=[1], runner_up_visual_similarity=.799)]
        settings = dict(acceptance_mode="range_top1", min_visual_similarity=.25,
                        min_top1_margin=.02, require_auxiliary_support=True)
        self.assertEqual(select_top1(rows, settings)["status"], "provisionally_matched")
        settings["acceptance_mode"] = "strict"
        self.assertEqual(select_top1(rows, settings)["status"], "requires_review")

    def test_range_boundaries_and_union(self):
        ranges = [dict(evidence_type="storyboard", panel_indices=[1], final_start_sec=2, final_end_sec=4),
                  dict(evidence_type="storyboard", panel_indices=[3], final_start_sec=3, final_end_sec=5)]
        evidence = [dict(evidence_index=i) for i in (1, 2, 3)]
        validate_ranges(ranges)
        self.assertEqual(set(allowed_evidence(dict(timestamp_sec=3), evidence, "storyboard", ranges)), {0, 2})
        self.assertEqual(set(allowed_evidence(dict(timestamp_sec=4), evidence, "storyboard", ranges)), {2})
        self.assertEqual(allowed_evidence(dict(timestamp_sec=5), evidence, "storyboard", ranges), {})
        with self.assertRaises(ValueError):
            validate_ranges([dict(evidence_type="animatic", final_start_sec=0, final_end_sec=1,
                                  evidence_start_sec=2, evidence_end_sec=1)])

    def test_top1_cannot_pass_by_rank_alone(self):
        settings = dict(min_visual_similarity=.5, min_top1_margin=.1, require_auxiliary_support=True)
        rows = [dict(id="one", evidence_index=1, visual_similarity=.9, text_supported=False,
                     declared_range_ids=[1])]
        self.assertEqual(select_top1(rows, settings)["status"], "requires_review")
        rows[0].update(text_supported=True, runner_up_visual_similarity=.85)
        self.assertEqual(select_top1(rows, settings)["reason"], "top1_top2_ambiguous")
        rows[0]["runner_up_visual_similarity"] = .6
        self.assertEqual(select_top1(rows, settings)["status"], "provisionally_matched")

    def test_automatic_panel_filter_handles_empty_page(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with fitz.open() as doc:
                doc.new_page()
                doc.save(root / "empty.pdf")
            records, manifest = extract_automatic_panels(root / "empty.pdf", root / "panels")
            self.assertEqual(records, [])
            self.assertEqual(manifest["pages"][0]["extraction_status"], "not_extracted")

    def test_human_panel_review_recrops_and_confirms_storyboard(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pdf_path = root / "storyboard.pdf"
            with fitz.open() as document:
                page = document.new_page(width=100, height=100)
                page.draw_rect(fitz.Rect(10, 10, 90, 90), color=(0, 0, 0))
                document.save(pdf_path)
            page_path = root / "page.png"
            Image.new("RGB", (200, 200), "white").save(page_path)
            manifest = {
                "source_pdf": str(pdf_path),
                "source_sha256": hashlib.sha256(pdf_path.read_bytes()).hexdigest(),
                "run_dir": str(root),
                "pages": [{"page_index": 1, "page_path": str(page_path),
                           "preview_path": str(page_path), "size": [200, 200],
                           "content_bbox": [0, 0, 200, 200], "reviewed": False,
                           "candidates": [{"bbox": [0, 0, 50, 50], "method": "automatic",
                                           "decision": "accept"}]}],
            }
            save_json(root / "panel_manifest.json", manifest)
            save_json(root / "prepared.json", {"run_dir": str(root),
                      "assets": {"storyboard": str(pdf_path)}, "panels": [],
                      "frames": {"final": [], "animatic": []},
                      "panel_review_confirmed": False})
            save_json(root / "config.json", {"correspondence_ranges": []})

            prepared = apply_panel_review(root, [{"page_index": 1, "candidates": [
                {"bbox": [20, 30, 120, 150], "method": "manual_review",
                 "decision": "accept", "order": 1}]}])

            self.assertTrue(prepared["panel_review_confirmed"])
            self.assertEqual(prepared["panels"][0]["bbox"], [20, 30, 120, 150])
            self.assertEqual(prepared["panels"][0]["decision_source"], "human_panel_review")
            with Image.open(prepared["panels"][0]["panel_path"]) as panel_image:
                self.assertEqual(panel_image.size, (100, 120))

    def test_global_retrieval_observes_correspondence_deviation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            save_json(config_path, dict(matching=dict(use_structure=False, top_k=1),
                correspondence_ranges=[dict(evidence_type="storyboard", panel_indices=[2],
                                           final_start_sec=0, final_end_sec=2)]))
            config = load_config(config_path)
            frames = [dict(timestamp_sec=t, keyframe_path=f"final{t}.png", test_vector=[1., 0.])
                      for t in (0., 1., 2.)]
            panels = [dict(evidence_index=i, panel_path=f"panel{i}.png", test_vector=v,
                           text=dict(description="A shared action", text_group_id="shared",
                                     shared_panel_count=2))
                      for i, v in ((1, [1., 0.]), (2, [.7, .714]))]
            prepared = dict(run_dir=str(root), panels=panels, frames=dict(final=frames, animatic=[]))
            save_json(root / "prepared.json", prepared)
            result = retrieve(config, prepared, encoder=FakeEncoder(), progress=lambda _: None)
            self.assertTrue(result["candidates"])
            self.assertTrue(all(r["evidence_index"] == 1 for r in result["candidates"]))
            self.assertTrue(all(not r["within_declared_correspondence"] for r in result["candidates"]))
            scores = json.loads((root / "evidence_scores.json").read_text())
            self.assertEqual(scores["provisional_and_human"]["total_final_frames"], 3)
            self.assertEqual(scores["provisional_and_human"]["visual_support_score"], 100.0)
            self.assertEqual(scores["human_confirmed"]["visual_support_score"], 0)
            correspondence = json.loads((root / "correspondence_diagnostics.json").read_text())
            combined = correspondence["provisional_and_human"]
            route = combined["route_summaries"][0]
            self.assertEqual(route["outside_declared_count"], 2)
            self.assertEqual(route["undeclared_final_count"], 1)
            self.assertEqual(route["correspondence_conformance_score"], 0.0)
            reviews = [dict(route="final_storyboard", final_index=1, decision="unmatched")]
            apply_reviews(root, reviews)
            self.assertEqual(len(json.loads((root / "matched_list.json").read_text())), 2)
            with self.assertRaises(ValueError):
                apply_reviews(root, [dict(route="final_storyboard", final_index=1,
                                         decision="matched", candidate_id="final_storyboard:2:2")])

    def test_global_retrieval_does_not_require_correspondence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "config.json"
            save_json(config_path, dict(matching=dict(use_structure=False, top_k=1),
                                        correspondence_ranges=[]))
            config = load_config(config_path)
            prepared = dict(
                run_dir=str(root),
                panels=[dict(evidence_index=1, panel_path="panel1.png", test_vector=[1., 0.],
                             text=dict(description="A shared action", text_group_id="shared",
                                       shared_panel_count=1))],
                frames=dict(final=[dict(timestamp_sec=0., keyframe_path="final.png",
                                         test_vector=[1., 0.])], animatic=[]),
            )
            save_json(root / "prepared.json", prepared)

            result = retrieve(config, prepared, encoder=FakeEncoder(), progress=lambda _: None)

            self.assertEqual(result["decisions"][0]["status"], "provisionally_matched")
            self.assertEqual(result["decisions"][0]["reason"], "global_top1_automatically_selected")
            correspondence = json.loads((root / "correspondence_diagnostics.json").read_text())
            combined = correspondence["provisional_and_human"]
            self.assertIsNone(combined["correspondence_conformance_score"])
            self.assertEqual(combined["observations"][0]["status"], "undeclared_final_interval")
            self.assertFalse(combined["retrieval_restricted_by_correspondence"])

    def test_sequence_can_observe_reverse_order(self):
        rows = [dict(route="final_animatic", final_index=i, evidence_index=j)
                for i, j in enumerate((3, 2, 1), 1)]
        score = _scores([{}, {}, {}], rows)
        route = next(r for r in score["route_order"] if r["route"] == "final_animatic")
        self.assertEqual(route["discordant_pair_count"], 3)
        self.assertEqual(route["score"], 0)


if __name__ == "__main__":
    unittest.main()
