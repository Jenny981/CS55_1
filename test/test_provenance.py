import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from subprocess import CompletedProcess
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
sys.path.insert(0, str(SRC))

from cs55_demo import load_config
from cs55_demo.provenance import (
    build_editing_history,
    build_provenance_summary,
    collect_basic_provenance,
    compute_sha256,
    collect_project_file_evidence,
    discover_project_files,
    extract_asset_software,
    inspect_c2pa,
    parse_pdf_datetime,
    simplify_provenance_indicators,
)
from cs55_demo.evidence_chain_builder import build_libevchain_bundle


class ProvenanceTests(unittest.TestCase):
    def test_sha256_and_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'asset.bin'
            path.write_bytes(b'CS55 provenance')

            result = compute_sha256(path, chunk_size=4)
            self.assertEqual(result['status'], 'computed')
            self.assertEqual(result['algorithm'], 'sha256')
            self.assertEqual(result['bytes_hashed'], len(b'CS55 provenance'))
            self.assertEqual(
                result['value'],
                hashlib.sha256(b'CS55 provenance').hexdigest(),
            )

            missing = compute_sha256(Path(directory) / 'missing.bin')
            self.assertEqual(missing['status'], 'file_missing')
            self.assertIsNone(missing['value'])

    def test_pdf_datetime_parser(self):
        self.assertEqual(
            parse_pdf_datetime("D:20260924123045+10'00'"),
            '2026-09-24T12:30:45+10:00',
        )
        self.assertEqual(
            parse_pdf_datetime('D:20260924Z'),
            '2026-09-24T00:00:00+00:00',
        )
        self.assertIsNone(parse_pdf_datetime(None))
        self.assertEqual(parse_pdf_datetime('unknown'), 'unknown')

    def test_sample_assets_have_json_safe_basic_provenance(self):
        config = load_config(ROOT / 'config.sample.json')
        result = collect_basic_provenance(config)

        self.assertEqual(
            set(result),
            {'storyboard', 'animatic', 'final'},
        )

        for asset_name, asset in result.items():
            self.assertEqual(asset['file_hash']['status'], 'computed')
            self.assertRegex(
                asset['file_hash']['value'],
                r'^[0-9a-f]{64}$',
            )
            self.assertIn(
                asset['metadata']['status'],
                {'extracted', 'partial'},
            )
            self.assertIn(
                asset['timestamps']['status'],
                {'extracted', 'partial'},
            )
            self.assertEqual(
                asset['type'],
                'storyboard' if asset_name == 'storyboard' else 'video',
            )
            self.assertEqual(asset['c2pa_manifest']['status'], 'no_manifest')
            self.assertIsNone(asset['c2pa_manifest']['signature_valid'])

            if asset_name == 'storyboard':
                self.assertEqual(asset['software']['status'], 'not_identified')
            else:
                self.assertEqual(asset['software']['status'], 'identified')
                self.assertTrue(asset['software']['candidates'])
            self.assertEqual(asset['project_file']['status'], 'not_found')
            self.assertEqual(asset['editing_history']['status'], 'assembled')
            self.assertGreater(asset['editing_history']['event_count'], 0)
            summary = asset['provenance_summary']
            self.assertEqual(summary['assessment_model'], (
                'four_evidence_indicators_no_score_v1'
            ))
            self.assertEqual(summary['coverage'], '1/4')
            self.assertEqual(
                summary['available_indicators'],
                ['file_integrity'],
            )
            self.assertNotIn('score', summary)
            for indicator in summary['indicators'].values():
                self.assertNotIn('score', indicator)
                self.assertNotIn('weight', indicator)

        json.dumps(result, ensure_ascii=False, allow_nan=False)

        simplified = simplify_provenance_indicators(result)
        for indicators in simplified.values():
            self.assertEqual(indicators, {
                'File Integrity': 'available',
                'C2PA Provenance': 'not_available',
                'Source Project Evidence': 'not_available',
                'Editing / AI Transparency': 'not_available',
            })

    def test_c2pa_missing_file(self):
        result = inspect_c2pa('/path/that/does/not/exist.mov')
        self.assertEqual(result['status'], 'file_missing')
        self.assertEqual(result['manifest_count'], 0)

    def test_c2pa_verified_ai_modified_manifest(self):
        manifest_label = 'urn:uuid:test'
        report = {
            'active_manifest': manifest_label,
            'validation_status': [
                {'code': 'claimSignature.validated', 'passed': True},
                {'code': 'signingCredential.trusted', 'passed': True},
            ],
            'manifests': {
                manifest_label: {
                    'validation_state': 'Trusted',
                    'signature_info': {
                        'issuer': 'Test Issuer',
                        'time': '2026-09-25T01:02:03Z',
                        'alg': 'es256',
                    },
                    'assertions': [
                        {
                            'label': 'c2pa.actions.v2',
                            'data': {
                                'actions': [
                                    {
                                        'action': 'c2pa.edited',
                                        'digitalSourceType': (
                                            'http://cv.iptc.org/newscodes/'
                                            'digitalsourcetype/'
                                            'compositeWithTrainedAlgorithmicMedia'
                                        ),
                                        'changes': [{'region': 'frame 4'}],
                                    },
                                ],
                            },
                        },
                        {
                            'label': 'c2pa.ai-disclosure',
                            'data': {
                                'modelType': 'generator',
                                'modelName': 'Example Model',
                            },
                        },
                    ],
                },
            },
        }

        with tempfile.TemporaryDirectory() as directory:
            asset_path = Path(directory) / 'asset.mov'
            asset_path.write_bytes(b'asset')
            subprocess_results = [
                CompletedProcess(
                    args=['c2patool', '--version'],
                    returncode=0,
                    stdout='c2patool 1.0\n',
                    stderr='',
                ),
                CompletedProcess(
                    args=['c2patool', str(asset_path)],
                    returncode=0,
                    stdout=json.dumps(report),
                    stderr='',
                ),
            ]
            with patch(
                'cs55_demo.provenance.subprocess.run',
                side_effect=subprocess_results,
            ):
                result = inspect_c2pa(asset_path, executable='c2patool')

        self.assertEqual(result['status'], 'verified')
        self.assertTrue(result['signature_valid'])
        self.assertTrue(result['trusted'])
        self.assertEqual(result['issuer'], 'Test Issuer')
        self.assertEqual(result['validation_state'], 'Trusted')
        self.assertEqual(len(result['validation_successes']), 2)
        self.assertEqual(result['validation_warnings'], [])
        self.assertTrue(result['ai_disclosure']['present'])
        self.assertEqual(result['ai_usage']['classification'], 'ai_modified')
        self.assertEqual(len(result['ai_usage']['modified_regions']), 1)
        json.dumps(result, allow_nan=False)

    def test_project_files_are_relative_hashed_candidates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project_dir = root / 'Selected AE Project files'
            project_dir.mkdir()
            project_path = project_dir / 'shot.aep'
            project_path.write_bytes(b'after-effects-project')
            ignored_dir = root / '.git'
            ignored_dir.mkdir()
            (ignored_dir / 'ignored.aep').write_bytes(b'ignored')

            candidates = discover_project_files(root)
            evidence = collect_project_file_evidence({
                'project_search_root': root,
            })

        self.assertEqual(len(candidates), 1)
        self.assertEqual(
            candidates[0]['path'],
            'Selected AE Project files/shot.aep',
        )
        self.assertEqual(candidates[0]['file_hash']['status'], 'computed')
        self.assertEqual(evidence['storyboard']['status'], 'not_found')
        for asset_name in ('animatic', 'final'):
            result = evidence[asset_name]
            self.assertEqual(result['status'], 'found')
            self.assertEqual(result['selected']['path'], candidates[0]['path'])
            self.assertFalse(result['selected']['relationship_verified'])

        json.dumps(evidence, allow_nan=False)

    def test_project_file_search_requires_configuration(self):
        result = collect_project_file_evidence({})
        for evidence in result.values():
            self.assertEqual(evidence['status'], 'not_configured')
            self.assertEqual(evidence['candidates'], [])

    def test_editing_history_separates_verified_and_inferred_events(self):
        timestamp_result = {
            'status': 'extracted',
            'filesystem': {
                'created_at': '2026-09-01T00:00:00+00:00',
                'modified_at': '2026-09-03T00:00:00+00:00',
            },
            'media': {
                'creation_time': '2026-09-02T00:00:00+00:00',
                'modification_time': None,
            },
        }
        c2pa_result = {
            'signature_valid': True,
            'trusted': False,
            'ai_usage': {
                'creation_actions': [],
                'editing_actions': [
                    {
                        'action': 'c2pa.edited',
                        'when': '2026-09-04T00:00:00+00:00',
                        'description': 'AI-assisted cleanup',
                        'digital_source_type': (
                            'http://cv.iptc.org/newscodes/'
                            'digitalsourcetype/'
                            'compositeWithTrainedAlgorithmicMedia'
                        ),
                        'software_agent': 'Editor/2.0',
                        'software_agent_index': None,
                        'parameters': {'strength': 0.2},
                    },
                ],
                'modified_regions': [
                    {
                        'action': 'c2pa.edited',
                        'region': {'frame': 4},
                    },
                ],
            },
        }
        software_result = {
            'primary': {
                'name': 'Editor',
                'version': '2.0',
                'source': 'c2pa.manifest.claim_generator_info',
            },
        }
        project_file_result = {
            'selected': {
                'path': 'Selected AE Project files/shot.aep',
                'file_hash': {
                    'status': 'computed',
                    'algorithm': 'sha256',
                    'value': 'a' * 64,
                },
                'relationship_basis': 'file_extension_and_asset_role',
            },
            'candidates': [],
        }

        result = build_editing_history(
            timestamp_result,
            c2pa_result,
            software_result,
            project_file_result,
        )

        self.assertEqual(result['status'], 'assembled')
        self.assertEqual(result['event_count'], 5)
        c2pa_event = next(
            event
            for event in result['events']
            if event['source'] == 'c2pa.actions'
        )
        self.assertTrue(c2pa_event['verified'])
        self.assertFalse(c2pa_event['evidence']['manifest_trusted'])
        self.assertEqual(c2pa_event['regions'], [{'frame': 4}])
        project_event = result['events'][-1]
        self.assertEqual(project_event['record_type'], 'inferred')
        self.assertFalse(project_event['verified'])
        self.assertIn('Project-file associations', result['warnings'][0])
        json.dumps(result, allow_nan=False)

    def test_indicator_summary_reports_checks_without_scoring(self):
        summary = build_provenance_summary(
            {
                'status': 'computed',
                'value': 'a' * 64,
                'bytes_hashed': 10,
            },
            {'status': 'extracted'},
            {
                'status': 'partial',
                'filesystem': {},
                'media': {},
            },
            {
                'status': 'verified',
                'active_manifest': 'urn:test',
                'manifest': {'assertions': []},
                'signature_valid': True,
                'trusted': False,
                'actions': [{'action': 'c2pa.created'}],
                'ai_disclosure': {'present': False, 'assertions': []},
                'ai_usage': {
                    'ai_generated': False,
                    'ai_modified': False,
                    'modified_regions': [],
                },
                'validation_errors': [],
                'validation_warnings': ['untrusted credential'],
            },
            {'status': 'identified', 'primary': {'name': 'Editor'}},
            {
                'candidates': [
                    {
                        'relationship_verified': True,
                        'file_hash': {'status': 'computed'},
                    },
                ],
            },
            {
                'events': [
                    {'record_type': 'declared'},
                ],
            },
        )

        self.assertEqual(summary['coverage'], '4/4')
        self.assertEqual(summary['status'], 'complete')
        trust_check = next(
            check
            for check in summary['indicators']['c2pa_provenance']['checks']
            if check['name'] == 'signing_credential_trusted'
        )
        self.assertFalse(trust_check['result'])
        self.assertNotIn('score', summary)
        self.assertNotIn('weight', summary)
        for indicator in summary['indicators'].values():
            self.assertNotIn('score', indicator)
            self.assertNotIn('weight', indicator)
        json.dumps(summary, allow_nan=False)

    def test_software_combines_c2pa_actions_and_video_metadata(self):
        metadata = {
            'status': 'extracted',
            'values': {
                'tags': {'encoder': 'Container Encoder'},
                'streams': [
                    {
                        'index': 0,
                        'tags': {'encoder': 'Stream Encoder'},
                    },
                ],
            },
        }
        c2pa = {
            'status': 'verified',
            'manifest': {
                'claim_generator_info': [
                    {'name': 'Signed App', 'version': '2.0'},
                ],
            },
            'actions': [
                {
                    'action': 'c2pa.edited',
                    'softwareAgent': 'Action App/3.0',
                },
            ],
        }

        result = extract_asset_software('final', metadata, c2pa)

        self.assertEqual(result['status'], 'identified')
        self.assertEqual(
            result['primary'],
            {
                'name': 'Signed App',
                'version': '2.0',
                'source': 'c2pa.manifest.claim_generator_info',
            },
        )
        self.assertEqual(
            [candidate['name'] for candidate in result['candidates']],
            [
                'Signed App',
                'Action App/3.0',
                'Container Encoder',
                'Stream Encoder',
            ],
        )
        json.dumps(result, allow_nan=False)

    def test_bundle_reuses_animatic_and_final_provenance_hashes(self):
        provenance = {
            'animatic': {
                'file_hash': {
                    'status': 'computed',
                    'algorithm': 'sha256',
                    'value': 'a' * 64,
                },
            },
            'final': {
                'file_hash': {
                    'status': 'computed',
                    'algorithm': 'sha256',
                    'value': 'f' * 64,
                },
            },
        }
        config = {
            'animatic_path': '/must/not/be/read/animatic.mov',
            'final_path': '/must/not/be/read/final.mov',
        }

        with patch(
            'cs55_demo.evidence_chain_builder.calculate_sha256',
            return_value='1' * 64,
        ) as calculate_hash:
            bundle = build_libevchain_bundle(
                config,
                ['storyboard-panel.png'],
                provenance=provenance,
            )

        calculate_hash.assert_called_once_with('storyboard-panel.png')
        self.assertEqual(bundle['final_artefact_hash'], 'f' * 64)
        self.assertEqual(bundle['artefacts'][-2]['artefact_hash'], 'a' * 64)
        self.assertEqual(bundle['provenance'], provenance)


if __name__ == '__main__':
    unittest.main()
