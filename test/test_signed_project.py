import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cs55_demo.source_project import digest, render_project, verify_project, verify_signed_project
from cs55_demo.config import load_config


def setup_fixture(folder):
    source = folder / 'source.mp4'
    source.write_bytes(b'media')
    project = folder / 'final.cs55project.json'
    project.write_text(json.dumps({'schema': 'cs55-edit-project/v1', 'asset_role': 'final',
        'source': {'path': 'source.mp4', 'sha256': digest(source)},
        'export': {'width': 1280, 'height': 720, 'fps': 24},
        'clips': [{'start_seconds': 0, 'end_seconds': 2}]}))
    unsigned = folder / 'unsigned.mp4'
    unsigned.write_bytes(b'export')
    signed = folder / 'signed.mp4'
    signed.write_bytes(b'signed export')
    credential = {'status': 'verified', 'signature_valid': True, 'trusted': False,
        'manifest': {'assertions': [{'label': 'org.cs55.export_binding.v1', 'data': {
            'schema': 'cs55-export-binding/v1', 'asset_role': 'final',
            'project_sha256': digest(project), 'unsigned_export_sha256': digest(unsigned)}}]}}
    return project, unsigned, signed, credential


def mock_render(project, destination, role):
    destination.write_bytes(b'export')


def check_fixture(folder, mutate=None, visual=None):
    project, unsigned, signed, credential = setup_fixture(folder)
    if mutate:
        mutate(credential)
    with patch('cs55_demo.source_project.render_project', side_effect=mock_render), \
         patch('cs55_demo.provenance.inspect_c2pa', return_value=credential), \
         patch('cs55_demo.source_project.visual_payload_digest', side_effect=visual or ['same', 'same']):
        return verify_signed_project(project, signed, unsigned, 'final')


@pytest.mark.parametrize('label', ['org.cs55.export_binding', 'org.cs55.export_binding.v1'])
def test_untrusted_test_certificate_is_explicit_not_historical_authentication(label):
    with tempfile.TemporaryDirectory() as folder:
        def mutate(credential):
            credential['manifest']['assertions'][0]['label'] = label
        result = check_fixture(Path(folder), mutate)
        assert result['relationship_verified']
        assert result['signer_trusted'] is False
        assert result['production_history_verified'] is False


@pytest.mark.parametrize('field,value', [('asset_role', 'animatic'), ('schema', 'unknown'),
                                       ('project_sha256', 'wrong'), ('unsigned_export_sha256', 'wrong')])
def test_signed_binding_field_mismatch_rejected(field, value):
    with tempfile.TemporaryDirectory() as folder:
        def mutate(credential):
            credential['manifest']['assertions'][0]['data'][field] = value
        assert not check_fixture(Path(folder), mutate)['relationship_verified']


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'invalid_signature', 'invalid_status'])
def test_incomplete_or_invalid_credential_rejected(change):
    with tempfile.TemporaryDirectory() as folder:
        def mutate(credential):
            if change == 'missing':
                credential['manifest']['assertions'] = []
            elif change == 'duplicate':
                credential['manifest']['assertions'] *= 2
            elif change == 'invalid_signature':
                credential['signature_valid'] = False
            else:
                credential['status'] = 'invalid'
        assert not check_fixture(Path(folder), mutate)['relationship_verified']


def test_valid_signature_cannot_hide_changed_pictures():
    with tempfile.TemporaryDirectory() as folder:
        assert not check_fixture(Path(folder), visual=['different', 'same'])['relationship_verified']


def test_actual_pdf_project_reexports_deterministically():
    import pymupdf as fitz
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 32, 18), False)
        pixmap.clear_with(180)
        panel = folder / 'panel.png'
        pixmap.save(panel)
        project = folder / 'storyboard.cs55project.json'
        project.write_text(json.dumps({'schema': 'cs55-pdf-project/v1', 'asset_role': 'storyboard',
            'export': {'width': 960, 'height': 540},
            'panels': [{'path': 'panel.png', 'sha256': digest(panel)}]}))
        output = folder / 'storyboard.pdf'
        render_project(project, output, 'storyboard')
        assert verify_project(project, output, 'storyboard')['relationship_verified']
        panel.write_bytes(b'changed')
        assert not verify_project(project, output, 'storyboard')['relationship_verified']


def test_config_resolves_unsigned_map():
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        config = {key: 'asset' for key in ('storyboard_path', 'animatic_path', 'final_path',
                  'storyboard_processed_dir', 'animatic_processed_dir', 'final_processed_dir')}
        config['source_project_unsigned_paths'] = {'final': 'unsigned/final.mp4'}
        path = folder / 'config.json'
        path.write_text(json.dumps(config))
        assert load_config(path)['source_project_unsigned_paths']['final'] == folder / 'unsigned/final.mp4'
