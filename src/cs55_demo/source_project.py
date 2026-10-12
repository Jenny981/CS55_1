"""Reproducible export check for a small, explicit CS55 editing project.

This verifies project-to-export correspondence, not authorship or history.
It does not parse Premiere, Resolve, or Lumina native projects.
"""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def load_project(path, role='final'):
    path = Path(path).resolve()
    project = json.loads(path.read_text(encoding='utf-8'))
    if role == 'storyboard' and project.get('schema') == 'cs55-pdf-project/v1':
        if project.get('asset_role') != role:
            raise ValueError('Asset role mismatch')
        settings = project['export']
        for key in ('width', 'height'):
            if type(settings[key]) is not int or not 1 <= settings[key] <= 1920:
                raise ValueError('Invalid PDF dimensions')
        panels = project['panels']
        if not isinstance(panels, list) or not 1 <= len(panels) <= 8:
            raise ValueError('Expected 1 to 8 panels')
        sources = []
        for panel in panels:
            source = (path.parent / panel['path']).resolve()
            if not source.is_relative_to(path.parent) or source.suffix.lower() != '.png':
                raise ValueError('Panel must be a PNG inside the project folder')
            if not source.is_file() or digest(source) != panel.get('sha256'):
                raise ValueError('Panel missing or hash mismatch')
            sources.append(source)
        return project, sources
    if project.get('schema') != 'cs55-edit-project/v1' or project.get('asset_role') != role:
        raise ValueError('Unsupported project schema or asset role')
    settings = project['export']
    for key, maximum in [('width', 1920), ('height', 1080), ('fps', 60)]:
        value = settings[key]
        if type(value) is not int or not 1 <= value <= maximum:
            raise ValueError(f'Invalid export {key}')
    if settings['width'] % 2 or settings['height'] % 2:
        raise ValueError('Dimensions must be even')
    media = project['source']
    source = (path.parent / media['path']).resolve()
    if not source.is_relative_to(path.parent) or source.suffix.lower() != '.mp4':
        raise ValueError('Source must be an MP4 inside the project folder')
    if not source.is_file():
        raise ValueError('Source media missing')
    if digest(source) != media.get('sha256'):
        raise ValueError('Source media hash mismatch')
    clips = project['clips']
    if not isinstance(clips, list) or not 1 <= len(clips) <= 8:
        raise ValueError('Expected 1 to 8 clips')
    duration = 0
    for clip in clips:
        start, end = clip['start_seconds'], clip['end_seconds']
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in (start, end)):
            raise ValueError('Invalid clip time')
        if not 0 <= start < end <= 30:
            raise ValueError('Invalid clip range')
        duration += end - start
    if duration > 30:
        raise ValueError('Test export duration exceeds 30 seconds')
    return project, source


def render_project(project_path, destination, role='final'):
    project, source = load_project(project_path, role)
    if project['schema'] == 'cs55-pdf-project/v1':
        import pymupdf as fitz
        with fitz.open() as doc:
            for panel in source:
                page = doc.new_page(width=project['export']['width'], height=project['export']['height'])
                page.insert_image(page.rect, filename=str(panel), keep_proportion=True)
            doc.set_metadata({'title': 'Umbrella controlled storyboard export',
                              'creator': 'CS55 test PDF project',
                              'subject': 'CS55_TEST_FIXTURE_NOT_LUMINA'})
            doc.save(destination, deflate=True, no_new_id=True)
        return project
    import imageio_ffmpeg
    count = len(project['clips'])
    filters = [f'[0:v]split={count}' + ''.join(f'[s{i}]' for i in range(count))]
    for i, clip in enumerate(project['clips']):
        filters.append(f"[s{i}]trim=start={clip['start_seconds']}:end={clip['end_seconds']},setpts=PTS-STARTPTS[v{i}]")
    settings = project['export']
    filters.append(''.join(f'[v{i}]' for i in range(count)) +
                   f"concat=n={count}:v=1:a=0,scale={settings['width']}:{settings['height']},fps={settings['fps']}[out]")
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
               '-y', '-i', str(source), '-filter_complex', ';'.join(filters), '-map', '[out]',
               '-an', '-map_metadata', '-1', '-c:v', 'libx264', '-preset', 'fast', '-crf', '18',
               '-pix_fmt', 'yuv420p', '-threads', '1', '-fflags', '+bitexact',
               '-flags:v', '+bitexact', str(destination)]
    subprocess.run(command, check=True, capture_output=True, timeout=120)
    return project


def verify_project(project_path, asset_path, role='final'):
    project_path, asset_path = Path(project_path), Path(asset_path)
    report = {'status': 'not_verified', 'relationship_verified': False,
              'method': 'reexport_and_compare_sha256',
              'scope': 'Reproducible export only; no claim of historical authorship.',
              'production_history_verified': False}
    try:
        if not asset_path.is_file():
            raise ValueError('Output asset missing')
        project, source = load_project(project_path, role)
        report.update({'project_sha256': digest(project_path), 'output_sha256': digest(asset_path)})
        if isinstance(source, list):
            report['source_sha256_list'] = [digest(p) for p in source]
            report['panel_count'] = len(source)
        else:
            report.update({'source_sha256': digest(source), 'clip_count': len(project['clips'])})
        with tempfile.TemporaryDirectory(prefix='cs55_project_verify_') as folder:
            rebuilt = Path(folder) / ('reexport.pdf' if role == 'storyboard' else 'reexport.mp4')
            render_project(project_path, rebuilt, role)
            report['reexport_sha256'] = digest(rebuilt)
        matched = report['output_sha256'] == report['reexport_sha256']
        report['relationship_verified'] = matched
        report['status'] = 'verified' if matched else 'output_mismatch'
    except (ValueError, KeyError, TypeError, OSError, ImportError, subprocess.SubprocessError) as error:
        report['error'] = str(error)
    return report


def visual_payload_digest(path, role):
    """Check decoded content independently of the signer's export declaration."""
    value = hashlib.sha256()
    if role == 'storyboard':
        import pymupdf as fitz
        with fitz.open(path) as doc:
            if not len(doc):
                raise ValueError('Empty PDF')
            for page in doc:
                pixmap = page.get_pixmap(alpha=False)
                value.update(str((pixmap.width, pixmap.height)).encode())
                value.update(pixmap.samples)
        return value.hexdigest()
    import cv2
    video = cv2.VideoCapture(str(path))
    try:
        if not video.isOpened():
            raise ValueError('Video cannot be decoded')
        value.update(str(video.get(cv2.CAP_PROP_FPS)).encode())
        count = 0
        while True:
            ok, frame = video.read()
            if not ok:
                break
            value.update(str(frame.shape).encode())
            value.update(frame.tobytes())
            count += 1
        if count != int(video.get(cv2.CAP_PROP_FRAME_COUNT)) or count == 0:
            raise ValueError('Incomplete video decoding')
        return value.hexdigest()
    finally:
        video.release()


def verify_signed_project(project_path, asset_path, unsigned_path, role):
    from .provenance import inspect_c2pa, normalize_c2pa_assertions
    report = verify_project(project_path, unsigned_path, role)
    report['method'] = 'reexport_and_verified_c2pa_export_binding_and_visual_match'
    report['scope'] = ('Reproducible test export and signed association with unchanged decoded pictures; '
                       'not original Lumina projects or authenticated production history. Audio is not checked.')
    if not report['relationship_verified']:
        return report
    report['relationship_verified'] = False
    try:
        credential = inspect_c2pa(asset_path)
        report['signer_trusted'] = credential.get('trusted')
        if credential.get('status') != 'verified' or credential.get('signature_valid') is not True:
            raise ValueError('Signed output credential invalid or missing')
        # The SDK normalizes a .v1 assertion label to the unversioned base label.
        bindings = [a.get('data') for a in normalize_c2pa_assertions(credential.get('manifest'))
                    if a.get('label') in ('org.cs55.export_binding', 'org.cs55.export_binding.v1')]
        expected = {'schema': 'cs55-export-binding/v1', 'asset_role': role,
                    'project_sha256': digest(project_path),
                    'unsigned_export_sha256': digest(unsigned_path)}
        if len(bindings) != 1 or not isinstance(bindings[0], dict):
            raise ValueError('Expected exactly one signed export binding')
        if any(bindings[0].get(key) != value for key, value in expected.items()):
            raise ValueError('Signed project/export binding mismatch')
        report['decoded_visual_match'] = (visual_payload_digest(asset_path, role) ==
                                          visual_payload_digest(unsigned_path, role))
        if not report['decoded_visual_match']:
            raise ValueError('Signed output pictures differ from project export')
        report['signed_output_sha256'] = digest(asset_path)
        report['signed_export_binding'] = expected
        report.update(status='verified', relationship_verified=True)
    except (ValueError, KeyError, TypeError, OSError, ImportError, RuntimeError) as error:
        report.update(status='signed_binding_not_verified', error=str(error))
    return report


def add_explicit_project_evidence(config, evidence):
    configured = config.get('source_project_paths', {})
    for role, project_path in configured.items():
        if role not in evidence:
            continue
        path = Path(project_path)
        if not path.name.endswith('.cs55project.json'):
            continue
        unsigned = config.get('source_project_unsigned_paths', {}).get(role)
        report = (verify_signed_project(path, config[f'{role}_path'], unsigned, role)
                  if unsigned else verify_project(path, config[f'{role}_path'], role))
        candidate = {'path': str(path), 'name': path.name, 'extension': '.cs55project.json',
                     'possible_roles': [role], 'relationship': 'reproducible_export_project',
                     'relationship_basis': report['method'],
                     'relationship_verified': report['relationship_verified'],
                     'verification': report,
                     'file_hash': {'status': 'computed' if report.get('project_sha256') else 'not_computed',
                                   'algorithm': 'sha256', 'value': report.get('project_sha256')}}
        evidence[role]['candidates'].append(candidate)
        evidence[role]['selected'] = candidate if report['relationship_verified'] else None
        evidence[role]['status'] = 'found'
        evidence[role]['warnings'] = [report['scope']]
    return evidence
