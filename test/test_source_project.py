import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from cs55_demo.source_project import digest, verify_project
from cs55_demo.provenance import collect_project_file_evidence
from cs55_demo.config import load_config


def fixture(folder):
    source = folder / 'source.mp4'
    source.write_bytes(b'media')
    project = folder / 'edit.cs55project.json'
    project.write_text(json.dumps({'schema': 'cs55-edit-project/v1', 'asset_role': 'final',
        'source': {'path': 'source.mp4', 'sha256': digest(source)},
        'export': {'width': 1280, 'height': 720, 'fps': 24},
        'clips': [{'start_seconds': 0, 'end_seconds': 2}]}))
    output = folder / 'final.mp4'
    output.write_bytes(b'export')
    return project, source, output


def reexport(project, destination, role):
    destination.write_bytes(b'export')


def test_matching_export_passes():
    with tempfile.TemporaryDirectory() as folder:
        project, source, output = fixture(Path(folder))
        with patch('cs55_demo.source_project.render_project', side_effect=reexport):
            assert verify_project(project, output)['relationship_verified'] is True


def test_wrong_output_fails():
    with tempfile.TemporaryDirectory() as folder:
        project, source, output = fixture(Path(folder))
        output.write_bytes(b'wrong export')
        with patch('cs55_demo.source_project.render_project', side_effect=reexport):
            assert verify_project(project, output)['status'] == 'output_mismatch'


def test_changed_source_fails_before_render():
    with tempfile.TemporaryDirectory() as folder:
        project, source, output = fixture(Path(folder))
        source.write_bytes(b'changed')
        with patch('cs55_demo.source_project.render_project') as render:
            assert verify_project(project, output)['relationship_verified'] is False
            render.assert_not_called()


def test_missing_source_fails():
    with tempfile.TemporaryDirectory() as folder:
        project, source, output = fixture(Path(folder))
        source.unlink()
        assert verify_project(project, output)['relationship_verified'] is False


def test_role_mismatch_fails():
    with tempfile.TemporaryDirectory() as folder:
        project, source, output = fixture(Path(folder))
        assert verify_project(project, output, 'animatic')['relationship_verified'] is False


def test_path_escape_fails():
    with tempfile.TemporaryDirectory() as folder:
        project, source, output = fixture(Path(folder))
        data = json.loads(project.read_text())
        data['source']['path'] = '../source.mp4'
        project.write_text(json.dumps(data))
        assert verify_project(project, output)['relationship_verified'] is False


def test_config_resolves_explicit_project_path():
    with tempfile.TemporaryDirectory() as folder:
        folder = Path(folder)
        config = {key: 'asset' for key in ('storyboard_path','animatic_path','final_path',
                  'storyboard_processed_dir','animatic_processed_dir','final_processed_dir')}
        config['source_project_paths'] = {'final': 'edit.cs55project.json'}
        path = folder / 'config.json'
        path.write_text(json.dumps(config))
        assert load_config(path)['source_project_paths']['final'] == folder / 'edit.cs55project.json'


def test_collection_is_opt_in():
    with tempfile.TemporaryDirectory() as folder:
        project, source, output = fixture(Path(folder))
        evidence = collect_project_file_evidence({'project_search_root': folder})
        assert not evidence['final']['candidates']
        with patch('cs55_demo.source_project.render_project', side_effect=reexport):
            evidence = collect_project_file_evidence({'project_search_root': folder,
                'source_project_paths': {'final': project}, 'final_path': output})
        assert evidence['final']['selected']['relationship_verified'] is True
        assert not evidence['storyboard']['candidates']
