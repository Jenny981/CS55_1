from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

try:
    import pymupdf
except ImportError:  # Optional at import time; reported as tool_unavailable.
    pymupdf = None

try:
    import cv2
except ImportError:  # ffprobe remains the preferred video extractor.
    cv2 = None


ASSET_PATH_KEYS = {
    'storyboard': 'storyboard_path',
    'animatic': 'animatic_path',
    'final': 'final_path',
}

ASSET_TYPES = {
    'storyboard': 'storyboard',
    'animatic': 'video',
    'final': 'video',
}

C2PA_NO_MANIFEST_MESSAGES = (
    'no claim found',
    'no manifest',
    'manifest not found',
    'no jumbf',
    'no c2pa',
)

C2PA_UNSUPPORTED_MESSAGES = (
    'unsupported format',
    'unsupported file',
    'unsupported type',
)

AI_GENERATED_SOURCE_TYPES = {
    'trainedalgorithmicmedia',
}

AI_MODIFIED_SOURCE_TYPES = {
    'compositewithtrainedalgorithmicmedia',
    'compositedwithtrainedalgorithmicmedia',
}

PROJECT_FILE_ROLES = {
    '.storyboard': {'storyboard'},
    '.sbpz': {'storyboard'},
    '.clip': {'storyboard'},
    '.kra': {'storyboard'},
    '.psd': {'storyboard', 'animatic', 'final'},
    '.ai': {'storyboard', 'animatic', 'final'},
    '.prproj': {'animatic', 'final'},
    '.aep': {'animatic', 'final'},
    '.aepx': {'animatic', 'final'},
    '.drp': {'animatic', 'final'},
    '.fcpxml': {'animatic', 'final'},
    '.veg': {'animatic', 'final'},
    '.blend': {'animatic', 'final'},
    '.nk': {'animatic', 'final'},
    '.ma': {'animatic', 'final'},
    '.mb': {'animatic', 'final'},
}

PROJECT_SEARCH_EXCLUDED_DIRS = {
    '.git',
    '.venv',
    '__pycache__',
    'outputs',
}


def compute_sha256(file_path, chunk_size=8 * 1024 * 1024):
    """Hash a file in chunks and return a JSON-safe evidence record."""
    path = Path(file_path)

    if not path.exists():
        return {
            'status': 'file_missing',
            'algorithm': 'sha256',
            'value': None,
            'bytes_hashed': 0,
        }

    if not path.is_file():
        return {
            'status': 'invalid_path',
            'algorithm': 'sha256',
            'value': None,
            'bytes_hashed': 0,
        }

    digest = hashlib.sha256()
    bytes_hashed = 0

    try:
        with path.open('rb') as handle:
            while chunk := handle.read(chunk_size):
                digest.update(chunk)
                bytes_hashed += len(chunk)
    except OSError as error:
        return {
            'status': 'read_error',
            'algorithm': 'sha256',
            'value': None,
            'bytes_hashed': bytes_hashed,
            'error': str(error),
        }

    return {
        'status': 'computed',
        'algorithm': 'sha256',
        'value': digest.hexdigest(),
        'bytes_hashed': bytes_hashed,
    }


def extract_pdf_metadata(file_path):
    path = Path(file_path)

    if not path.exists():
        return {
            'status': 'file_missing',
            'extractor': 'PyMuPDF',
            'values': {},
            'warnings': [],
        }

    if not path.is_file():
        return {
            'status': 'invalid_path',
            'extractor': 'PyMuPDF',
            'values': {},
            'warnings': ['Source path is not a file'],
        }

    if pymupdf is None:
        return {
            'status': 'tool_unavailable',
            'extractor': 'PyMuPDF',
            'values': {},
            'warnings': ['PyMuPDF is not installed'],
        }

    try:
        with pymupdf.open(path) as document:
            first_page_size = None
            if len(document) > 0:
                rect = document[0].rect
                first_page_size = {
                    'width_points': float(rect.width),
                    'height_points': float(rect.height),
                }

            metadata = document.metadata or {}
            values = {
                'file_size_bytes': path.stat().st_size,
                'format': metadata.get('format'),
                'page_count': len(document),
                'first_page_size': first_page_size,
                'document_properties': {
                    key: value
                    for key, value in metadata.items()
                    if key != 'format' and value not in (None, '')
                },
            }
    except Exception as error:
        return {
            'status': 'extraction_error',
            'extractor': 'PyMuPDF',
            'values': {},
            'warnings': [str(error)],
        }

    return {
        'status': 'extracted',
        'extractor': 'PyMuPDF',
        'values': values,
        'warnings': [],
    }


def extract_video_metadata_with_opencv(file_path, warning=None):
    path = Path(file_path)
    warnings = [warning] if warning else []

    if cv2 is None:
        warnings.append('OpenCV is not installed')
        return {
            'status': 'tool_unavailable',
            'extractor': 'OpenCV',
            'values': {},
            'warnings': warnings,
        }

    capture = cv2.VideoCapture(str(path))
    try:
        if not capture.isOpened():
            warnings.append('OpenCV could not open the video')
            return {
                'status': 'extraction_error',
                'extractor': 'OpenCV',
                'values': {},
                'warnings': warnings,
            }

        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fourcc_value = int(capture.get(cv2.CAP_PROP_FOURCC))
        codec = ''.join(
            chr((fourcc_value >> (8 * index)) & 0xFF)
            for index in range(4)
        ).strip('\x00')
    finally:
        capture.release()

    warnings.append(
        'ffprobe unavailable or failed; metadata is limited to OpenCV fields'
    )
    return {
        'status': 'partial',
        'extractor': 'OpenCV',
        'values': {
            'file_size_bytes': path.stat().st_size,
            'format': path.suffix.lower().lstrip('.'),
            'duration_seconds': frame_count / fps if fps > 0 else None,
            'video_stream': {
                'codec_tag': codec or None,
                'width': width,
                'height': height,
                'fps': fps,
                'frame_count': frame_count,
            },
        },
        'warnings': warnings,
    }


def extract_video_metadata(file_path, timeout_seconds=120):
    path = Path(file_path)

    if not path.exists():
        return {
            'status': 'file_missing',
            'extractor': 'ffprobe',
            'values': {},
            'warnings': [],
        }

    if not path.is_file():
        return {
            'status': 'invalid_path',
            'extractor': 'ffprobe',
            'values': {},
            'warnings': ['Source path is not a file'],
        }

    ffprobe_path = shutil.which('ffprobe')
    if ffprobe_path is None:
        return extract_video_metadata_with_opencv(
            path,
            warning='ffprobe was not found on PATH',
        )

    command = [
        ffprobe_path,
        '-v',
        'error',
        '-show_format',
        '-show_streams',
        '-of',
        'json',
        str(path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
            timeout=timeout_seconds,
        )
        probe = json.loads(completed.stdout)
        format_data = probe.get('format', {})

        streams = []
        for stream in probe.get('streams', []):
            streams.append({
                key: stream[key]
                for key in [
                    'index',
                    'codec_type',
                    'codec_name',
                    'codec_long_name',
                    'profile',
                    'codec_tag_string',
                    'width',
                    'height',
                    'pix_fmt',
                    'r_frame_rate',
                    'avg_frame_rate',
                    'duration',
                    'nb_frames',
                    'sample_rate',
                    'channels',
                    'channel_layout',
                    'tags',
                ]
                if key in stream
            })

        values = {
            'file_size_bytes': path.stat().st_size,
            'format': format_data.get('format_name'),
            'format_long_name': format_data.get('format_long_name'),
            'duration_seconds': (
                float(format_data['duration'])
                if format_data.get('duration') is not None
                else None
            ),
            'bit_rate': (
                int(format_data['bit_rate'])
                if format_data.get('bit_rate') is not None
                else None
            ),
            'tags': format_data.get('tags', {}),
            'streams': streams,
        }
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        OSError,
        TypeError,
        ValueError,
    ) as error:
        return extract_video_metadata_with_opencv(
            path,
            warning=f'ffprobe failed: {error}',
        )

    return {
        'status': 'extracted',
        'extractor': 'ffprobe',
        'values': values,
        'warnings': [],
    }


def extract_filesystem_timestamps(file_path):
    path = Path(file_path)

    if not path.exists():
        return {
            'status': 'file_missing',
            'created_at': None,
            'modified_at': None,
            'metadata_changed_at': None,
        }

    if not path.is_file():
        return {
            'status': 'invalid_path',
            'created_at': None,
            'modified_at': None,
            'metadata_changed_at': None,
        }

    try:
        stat = path.stat()
    except OSError as error:
        return {
            'status': 'read_error',
            'created_at': None,
            'modified_at': None,
            'metadata_changed_at': None,
            'error': str(error),
        }

    created_timestamp = getattr(stat, 'st_birthtime', None)
    return {
        'status': 'extracted',
        'created_at': (
            datetime.fromtimestamp(
                created_timestamp,
                tz=timezone.utc,
            ).isoformat()
            if created_timestamp is not None
            else None
        ),
        'modified_at': datetime.fromtimestamp(
            stat.st_mtime,
            tz=timezone.utc,
        ).isoformat(),
        'metadata_changed_at': datetime.fromtimestamp(
            stat.st_ctime,
            tz=timezone.utc,
        ).isoformat(),
    }


def parse_pdf_datetime(value):
    if not value:
        return None

    pattern = (
        r'^D:?'
        r'(?P<year>\d{4})'
        r'(?P<month>\d{2})?'
        r'(?P<day>\d{2})?'
        r'(?P<hour>\d{2})?'
        r'(?P<minute>\d{2})?'
        r'(?P<second>\d{2})?'
        r"(?P<timezone>Z|[+-]\d{2}'?\d{2}'?)?"
    )
    match = re.match(pattern, str(value))
    if not match:
        return value

    parts = match.groupdict()
    timezone_text = parts['timezone']
    if timezone_text == 'Z':
        tz = timezone.utc
    elif timezone_text:
        cleaned = timezone_text.replace("'", '')
        sign = 1 if cleaned[0] == '+' else -1
        tz = timezone(
            sign
            * timedelta(
                hours=int(cleaned[1:3]),
                minutes=int(cleaned[3:5]),
            )
        )
    else:
        tz = None

    try:
        parsed = datetime(
            int(parts['year']),
            int(parts['month'] or 1),
            int(parts['day'] or 1),
            int(parts['hour'] or 0),
            int(parts['minute'] or 0),
            int(parts['second'] or 0),
            tzinfo=tz,
        )
    except ValueError:
        return value

    return parsed.isoformat()


def extract_pdf_internal_timestamps(metadata_result):
    properties = (
        metadata_result
        .get('values', {})
        .get('document_properties', {})
    )
    return {
        'creation_time': parse_pdf_datetime(
            properties.get('creationDate')
        ),
        'modification_time': parse_pdf_datetime(
            properties.get('modDate')
        ),
        'source': 'PDF document properties',
    }


def extract_video_internal_timestamps(metadata_result):
    values = metadata_result.get('values', {})
    container_tags = values.get('tags', {})
    if not isinstance(container_tags, dict):
        container_tags = {}

    creation_time = container_tags.get('creation_time')
    modification_time = container_tags.get('modification_time')
    source = 'container.tags' if (creation_time or modification_time) else None

    if not creation_time and not modification_time:
        for stream in values.get('streams', []):
            if not isinstance(stream, dict):
                continue
            stream_tags = stream.get('tags', {})
            if not isinstance(stream_tags, dict):
                continue
            creation_time = stream_tags.get('creation_time')
            modification_time = stream_tags.get('modification_time')
            if creation_time or modification_time:
                source = f"stream_{stream.get('index')}.tags"
                break

    return {
        'creation_time': creation_time,
        'modification_time': modification_time,
        'source': source,
    }


def extract_asset_timestamps(asset_name, file_path, metadata_result):
    filesystem = extract_filesystem_timestamps(file_path)
    media = (
        extract_pdf_internal_timestamps(metadata_result)
        if asset_name == 'storyboard'
        else extract_video_internal_timestamps(metadata_result)
    )

    if filesystem['status'] in {'file_missing', 'invalid_path', 'read_error'}:
        return {
            'status': filesystem['status'],
            'filesystem': filesystem,
            'media': media,
            'warnings': ['Source file is unavailable'],
        }

    has_internal_time = any([
        media.get('creation_time'),
        media.get('modification_time'),
    ])
    return {
        'status': 'extracted' if has_internal_time else 'partial',
        'filesystem': filesystem,
        'media': media,
        'warnings': (
            []
            if has_internal_time
            else ['No embedded media timestamp found']
        ),
    }


def _empty_c2pa_result():
    return {
        'status': 'not_checked',
        'tool': 'c2patool',
        'tool_version': None,
        'active_manifest': None,
        'manifest_count': 0,
        'manifest': None,
        'validation_state': None,
        'signature_valid': None,
        'trusted': None,
        'issuer': None,
        'signed_at': None,
        'certificate_serial_number': None,
        'signature_algorithm': None,
        'actions': [],
        'ai_disclosure': {
            'present': False,
            'assertions': [],
        },
        'ai_usage': {
            'classification': 'not_disclosed',
            'ai_generated': False,
            'ai_modified': False,
            'digital_source_types': [],
            'creation_actions': [],
            'editing_actions': [],
            'modified_regions': [],
        },
        'validation_successes': [],
        'validation_errors': [],
        'validation_warnings': [],
    }


def normalize_c2pa_assertions(manifest):
    if not isinstance(manifest, dict):
        return []

    assertions = manifest.get('assertions', [])
    if isinstance(assertions, dict):
        return [
            {'label': label, 'data': data}
            for label, data in assertions.items()
        ]
    if isinstance(assertions, list):
        return [
            assertion
            for assertion in assertions
            if isinstance(assertion, dict)
        ]
    return []


def extract_c2pa_actions(manifest):
    actions = []
    for assertion in normalize_c2pa_assertions(manifest):
        label = str(assertion.get('label', ''))
        if not label.startswith('c2pa.actions'):
            continue

        data = assertion.get('data', assertion)
        if not isinstance(data, dict):
            continue

        assertion_actions = data.get('actions', [])
        if isinstance(assertion_actions, list):
            actions.extend(
                action
                for action in assertion_actions
                if isinstance(action, dict)
            )
    return actions


def extract_ai_disclosures(manifest):
    disclosures = []
    for assertion in normalize_c2pa_assertions(manifest):
        label = str(assertion.get('label', ''))
        if not label.startswith('c2pa.ai-disclosure'):
            continue

        data = assertion.get('data', assertion)
        if not isinstance(data, dict):
            continue

        content_profile = data.get('contentProfile', {})
        if not isinstance(content_profile, dict):
            content_profile = {}

        metadata = data.get('metadata', {})
        disclosures.append({
            'label': label,
            'model_type': data.get('modelType'),
            'model_name': data.get('modelName'),
            'model_identifier': data.get('modelIdentifier'),
            'human_oversight_level': content_profile.get(
                'humanOversightLevel'
            ),
            'scientific_domain': data.get('scientificDomain'),
            'content_profile': content_profile,
            'metadata': metadata if isinstance(metadata, dict) else {},
        })

    return {
        'present': bool(disclosures),
        'assertions': disclosures,
    }


def _normalize_source_type(value):
    if value in (None, ''):
        return None
    return str(value).rsplit('/', 1)[-1].lower()


def _iter_c2pa_actions(actions):
    for action in actions:
        if not isinstance(action, dict):
            continue
        yield action

        related = action.get('related', [])
        if isinstance(related, list):
            yield from _iter_c2pa_actions(related)


def interpret_ai_actions(actions, ai_disclosure):
    creation_actions = []
    editing_actions = []
    changed_regions = []
    digital_source_types = []
    ai_generated = False
    ai_modified = False

    for action in _iter_c2pa_actions(actions):
        action_name = str(action.get('action', ''))
        source_type = action.get('digitalSourceType')
        normalized_source_type = _normalize_source_type(source_type)

        if source_type and source_type not in digital_source_types:
            digital_source_types.append(source_type)
        if normalized_source_type in AI_GENERATED_SOURCE_TYPES:
            ai_generated = True
        if normalized_source_type in AI_MODIFIED_SOURCE_TYPES:
            ai_modified = True

        parameters = action.get('parameters', {})
        summary = {
            'action': action_name or None,
            'when': action.get('when'),
            'description': action.get('description'),
            'digital_source_type': source_type,
            'software_agent': action.get('softwareAgent'),
            'software_agent_index': action.get('softwareAgentIndex'),
            'parameters': parameters if isinstance(parameters, dict) else {},
        }
        if action_name == 'c2pa.created':
            creation_actions.append(summary)
        else:
            editing_actions.append(summary)

        changes = action.get('changes', [])
        if isinstance(changes, list):
            for region in changes:
                changed_regions.append({
                    'action': action_name or None,
                    'digital_source_type': source_type,
                    'region': region,
                })

    if ai_generated:
        classification = 'ai_generated'
    elif ai_modified:
        classification = 'ai_modified'
    elif ai_disclosure.get('present'):
        classification = 'ai_disclosed_unspecified_use'
    else:
        classification = 'not_disclosed'

    return {
        'classification': classification,
        'ai_generated': ai_generated,
        'ai_modified': ai_modified,
        'digital_source_types': digital_source_types,
        'creation_actions': creation_actions,
        'editing_actions': editing_actions,
        'modified_regions': changed_regions,
    }


def _collect_validation_entries(report, active_manifest):
    entries = []
    seen = set()
    candidates = [
        report.get('validation_status'),
        report.get('validation_results'),
        active_manifest.get('validation_status'),
        active_manifest.get('validation_results'),
    ]

    def collect(candidate):
        if isinstance(candidate, list):
            for item in candidate:
                if isinstance(item, dict):
                    normalized = item
                elif isinstance(item, str):
                    normalized = {'code': item, 'message': item}
                else:
                    continue

                marker = json.dumps(
                    normalized,
                    sort_keys=True,
                    ensure_ascii=False,
                    default=str,
                )
                if marker not in seen:
                    seen.add(marker)
                    entries.append(normalized)
        elif isinstance(candidate, dict):
            if any(
                key in candidate
                for key in ('code', 'explanation', 'message', 'passed')
            ):
                entries.append(candidate)
            else:
                for value in candidate.values():
                    collect(value)

    for candidate in candidates:
        collect(candidate)
    return entries


def _classify_validation_entries(entries):
    successes = []
    errors = []
    warnings = []

    for entry in entries:
        code = str(entry.get('code', ''))
        explanation = str(
            entry.get('explanation', entry.get('message', ''))
        )
        severity = str(
            entry.get('severity', entry.get('kind', ''))
        ).lower()
        combined = f'{code} {explanation}'.lower()
        succeeded = (
            entry.get('passed') is True
            or severity == 'success'
            or code == 'signingCredential.trusted'
            or any(
                marker in code
                for marker in (
                    '.validated',
                    '.insideValidity',
                    '.match',
                    '.accessible',
                    '.notRevoked',
                )
            )
        )
        failed = (
            entry.get('passed') is False
            or severity in {'error', 'failure', 'fatal'}
            or any(
                term in combined
                for term in (
                    'error',
                    'failure',
                    'failed',
                    'mismatch',
                    'invalid',
                )
            )
        )
        if failed:
            errors.append(entry)
        elif succeeded:
            successes.append(entry)
        else:
            warnings.append(entry)
    return successes, errors, warnings


def _extract_signature_information(manifest):
    signature = manifest.get('signature_info', {})
    if not isinstance(signature, dict):
        signature = {}
    return {
        'issuer': signature.get('issuer') or signature.get('cert_issuer'),
        'signed_at': (
            signature.get('time')
            or signature.get('signed_at')
            or signature.get('timestamp')
        ),
        'certificate_serial_number': signature.get('cert_serial_number'),
        'signature_algorithm': signature.get('alg'),
    }


def _validation_summary(report, active_manifest, entries, errors):
    validation_state = (
        report.get('validation_state')
        or active_manifest.get('validation_state')
    )
    normalized_state = str(validation_state or '').lower()
    codes = {
        str(entry.get('code', ''))
        for entry in entries
        if isinstance(entry, dict)
    }

    signature_valid = None
    if errors or normalized_state == 'invalid':
        signature_valid = False
    elif (
        normalized_state in {'valid', 'trusted'}
        or 'claimSignature.validated' in codes
    ):
        signature_valid = True

    trusted = None
    if normalized_state == 'trusted' or 'signingCredential.trusted' in codes:
        trusted = True
    elif 'signingCredential.untrusted' in codes:
        trusted = False
    elif signature_valid is not None:
        trusted = False

    return validation_state, signature_valid, trusted


def inspect_c2pa(file_path, timeout_seconds=120, executable=None):
    """Read C2PA evidence without converting its presence into a score."""
    path = Path(file_path)
    result = _empty_c2pa_result()

    if not path.exists():
        return {
            **result,
            'status': 'file_missing',
            'validation_errors': ['Source file does not exist'],
        }
    if not path.is_file():
        return {
            **result,
            'status': 'invalid_path',
            'validation_errors': ['Source path is not a file'],
        }

    c2patool_path = executable or shutil.which('c2patool')
    if not c2patool_path:
        return {
            **result,
            'status': 'tool_unavailable',
            'validation_errors': ['c2patool was not found on PATH'],
        }

    tool_version = None
    try:
        version_result = subprocess.run(
            [c2patool_path, '--version'],
            capture_output=True,
            text=True,
            timeout=10,
        )
        tool_version = (
            version_result.stdout.strip()
            or version_result.stderr.strip()
            or None
        )
    except (OSError, subprocess.TimeoutExpired):
        pass

    try:
        completed = subprocess.run(
            [c2patool_path, str(path)],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return {
            **result,
            'status': 'read_error',
            'tool_version': tool_version,
            'validation_errors': ['c2patool timed out'],
        }
    except OSError as error:
        return {
            **result,
            'status': 'read_error',
            'tool_version': tool_version,
            'validation_errors': [str(error)],
        }

    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    combined_message = f'{stdout}\n{stderr}'.lower()

    if any(message in combined_message for message in C2PA_NO_MANIFEST_MESSAGES):
        return {
            **result,
            'status': 'no_manifest',
            'tool_version': tool_version,
            'validation_warnings': [stderr] if stderr else [],
        }
    if any(message in combined_message for message in C2PA_UNSUPPORTED_MESSAGES):
        return {
            **result,
            'status': 'unsupported_format',
            'tool_version': tool_version,
            'validation_warnings': [stderr] if stderr else [],
        }
    if not stdout:
        return {
            **result,
            'status': 'read_error',
            'tool_version': tool_version,
            'validation_errors': [
                stderr or 'c2patool returned no JSON output'
            ],
        }

    try:
        report = json.loads(stdout)
    except json.JSONDecodeError as error:
        return {
            **result,
            'status': 'read_error',
            'tool_version': tool_version,
            'validation_errors': [f'Invalid c2patool JSON: {error}'],
            'validation_warnings': [stderr] if stderr else [],
        }

    if not isinstance(report, dict):
        return {
            **result,
            'status': 'read_error',
            'tool_version': tool_version,
            'validation_errors': ['c2patool JSON root is not an object'],
        }

    active_label = report.get('active_manifest')
    manifests = report.get('manifests', {})
    if not isinstance(manifests, dict):
        manifests = {}
    if not active_label and not manifests:
        return {
            **result,
            'status': 'no_manifest',
            'tool_version': tool_version,
            'validation_warnings': [stderr] if stderr else [],
        }

    active_manifest = manifests.get(active_label, {})
    if not isinstance(active_manifest, dict):
        active_manifest = {}

    entries = _collect_validation_entries(report, active_manifest)
    successes, errors, warnings = _classify_validation_entries(entries)
    if completed.returncode != 0 and not errors:
        errors.append({
            'code': 'c2patool.nonzero_exit',
            'message': stderr or f'Exit code {completed.returncode}',
        })
    elif stderr:
        warnings.append({'message': stderr})

    validation_state, signature_valid, trusted = _validation_summary(
        report,
        active_manifest,
        entries,
        errors,
    )
    signature = _extract_signature_information(active_manifest)
    actions = extract_c2pa_actions(active_manifest)
    ai_disclosure = extract_ai_disclosures(active_manifest)
    ai_usage = interpret_ai_actions(actions, ai_disclosure)

    if errors:
        status = 'invalid'
    elif signature_valid is True:
        status = 'verified'
    else:
        status = 'present_unverified'

    return {
        **result,
        'status': status,
        'tool_version': tool_version,
        'active_manifest': active_label,
        'manifest_count': len(manifests),
        'manifest': active_manifest,
        'validation_state': validation_state,
        'signature_valid': signature_valid,
        'trusted': trusted,
        **signature,
        'actions': actions,
        'ai_disclosure': ai_disclosure,
        'ai_usage': ai_usage,
        'validation_successes': successes,
        'validation_errors': errors,
        'validation_warnings': warnings,
    }


def add_software_candidate(candidates, name, source, version=None):
    """Append one explicit software identifier without guessing its origin."""
    if name in (None, ''):
        return

    candidate = {
        'name': str(name).strip(),
        'version': (
            str(version).strip()
            if version not in (None, '')
            else None
        ),
        'source': source,
    }
    if not candidate['name']:
        return

    identity = (
        candidate['name'].casefold(),
        (candidate['version'] or '').casefold(),
        candidate['source'],
    )
    existing = {
        (
            item['name'].casefold(),
            (item.get('version') or '').casefold(),
            item['source'],
        )
        for item in candidates
    }
    if identity not in existing:
        candidates.append(candidate)


def extract_c2pa_software(c2pa_result, candidates):
    manifest = c2pa_result.get('manifest')
    if not isinstance(manifest, dict):
        return

    generator_info = manifest.get('claim_generator_info', [])
    if isinstance(generator_info, dict):
        generator_info = [generator_info]
    if not isinstance(generator_info, list):
        generator_info = []

    for item in generator_info:
        if not isinstance(item, dict):
            continue
        add_software_candidate(
            candidates,
            item.get('name'),
            'c2pa.manifest.claim_generator_info',
            item.get('version'),
        )

    add_software_candidate(
        candidates,
        manifest.get('claim_generator'),
        'c2pa.manifest.claim_generator',
    )

    for action_index, action in enumerate(c2pa_result.get('actions', [])):
        if not isinstance(action, dict):
            continue

        software_agent = action.get('softwareAgent')
        if isinstance(software_agent, dict):
            add_software_candidate(
                candidates,
                software_agent.get('name'),
                f'c2pa.actions[{action_index}].softwareAgent',
                software_agent.get('version'),
            )
        else:
            add_software_candidate(
                candidates,
                software_agent,
                f'c2pa.actions[{action_index}].softwareAgent',
            )

        software_index = action.get('softwareAgentIndex')
        if isinstance(software_index, int) and 0 <= software_index < len(generator_info):
            referenced = generator_info[software_index]
            if isinstance(referenced, dict):
                add_software_candidate(
                    candidates,
                    referenced.get('name'),
                    (
                        f'c2pa.actions[{action_index}]'
                        '.softwareAgentIndex'
                    ),
                    referenced.get('version'),
                )


def extract_pdf_software(metadata_result, candidates):
    properties = (
        metadata_result
        .get('values', {})
        .get('document_properties', {})
    )
    if not isinstance(properties, dict):
        return

    add_software_candidate(
        candidates,
        properties.get('creator'),
        'pdf.document_properties.creator',
    )
    add_software_candidate(
        candidates,
        properties.get('producer'),
        'pdf.document_properties.producer',
    )


def extract_video_software(metadata_result, candidates):
    values = metadata_result.get('values', {})
    if not isinstance(values, dict):
        return

    container_tags = values.get('tags', {})
    if isinstance(container_tags, dict):
        for key in ('encoder', 'writing_application', 'writing_library'):
            add_software_candidate(
                candidates,
                container_tags.get(key),
                f'video.format.tags.{key}',
            )

    streams = values.get('streams', [])
    if not isinstance(streams, list):
        return
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        stream_index = stream.get('index')
        stream_tags = stream.get('tags', {})
        if not isinstance(stream_tags, dict):
            continue
        for key in (
            'encoder',
            'writing_application',
            'writing_library',
            'handler_name',
        ):
            add_software_candidate(
                candidates,
                stream_tags.get(key),
                f'video.streams[{stream_index}].tags.{key}',
            )


def extract_asset_software(asset_name, metadata_result, c2pa_result):
    candidates = []

    # Signed provenance is listed before self-reported container metadata.
    extract_c2pa_software(c2pa_result, candidates)
    if asset_name == 'storyboard':
        extract_pdf_software(metadata_result, candidates)
    else:
        extract_video_software(metadata_result, candidates)

    if (
        metadata_result.get('status') == 'file_missing'
        or c2pa_result.get('status') == 'file_missing'
    ):
        status = 'file_missing'
    elif candidates:
        status = 'identified'
    else:
        status = 'not_identified'

    return {
        'status': status,
        'primary': candidates[0] if candidates else None,
        'candidates': candidates,
        'warnings': (
            [
                'Software identifiers are self-reported metadata and do not '
                'independently prove authenticity.'
            ]
            if candidates
            else [
                'No software identifier was found in metadata or C2PA data.'
            ]
        ),
    }


def discover_project_files(search_root):
    """Find recognised project files and expose paths relative to the root."""
    root = Path(search_root)
    if not root.exists() or not root.is_dir():
        return []

    candidates = []
    for path in root.rglob('*'):
        if not path.is_file():
            continue

        try:
            relative_path = path.relative_to(root)
        except ValueError:
            continue
        if any(
            part in PROJECT_SEARCH_EXCLUDED_DIRS
            for part in relative_path.parts
        ):
            continue

        extension = path.suffix.lower()
        roles = PROJECT_FILE_ROLES.get(extension)
        if not roles:
            continue

        try:
            size_bytes = path.stat().st_size
        except OSError:
            size_bytes = None

        candidates.append({
            'path': relative_path.as_posix(),
            'name': path.name,
            'extension': extension,
            'size_bytes': size_bytes,
            'possible_roles': sorted(roles),
            'file_hash': compute_sha256(path),
        })

    return sorted(candidates, key=lambda item: item['path'].casefold())


def associate_project_files(asset_name, candidates, search_status='searched'):
    if search_status != 'searched':
        warnings = {
            'not_configured': [
                'No project_search_root was configured.'
            ],
            'search_root_missing': [
                'The configured project_search_root does not exist.'
            ],
            'invalid_search_root': [
                'The configured project_search_root is not a directory.'
            ],
        }
        return {
            'status': search_status,
            'selected': None,
            'candidates': [],
            'warnings': warnings.get(
                search_status,
                ['Project-file discovery was not completed.'],
            ),
        }

    matches = []
    for candidate in candidates:
        if asset_name not in candidate.get('possible_roles', []):
            continue
        matches.append({
            **candidate,
            'relationship': 'potential_source_project',
            'relationship_basis': 'file_extension_and_asset_role',
            'relationship_verified': False,
        })

    return {
        'status': 'found' if matches else 'not_found',
        'selected': matches[0] if len(matches) == 1 else None,
        'candidates': matches,
        'warnings': (
            [
                'Project-file relationships are candidates only and require '
                'path, timeline, or human verification.'
            ]
            if matches
            else [
                'No recognised project file was found under '
                'project_search_root.'
            ]
        ),
    }


def collect_project_file_evidence(config):
    search_root = config.get('project_search_root')
    if search_root in (None, ''):
        search_status = 'not_configured'
        candidates = []
    else:
        root = Path(search_root)
        if not root.exists():
            search_status = 'search_root_missing'
            candidates = []
        elif not root.is_dir():
            search_status = 'invalid_search_root'
            candidates = []
        else:
            search_status = 'searched'
            candidates = discover_project_files(root)

    return {
        asset_name: associate_project_files(
            asset_name,
            candidates,
            search_status=search_status,
        )
        for asset_name in ASSET_TYPES
    }


def editing_history_event(
    time,
    action,
    source,
    record_type,
    description,
    software=None,
    regions=None,
    verified=False,
    evidence=None,
):
    return {
        'time': time,
        'action': action,
        'source': source,
        'record_type': record_type,
        'description': description,
        'software': software,
        'regions': regions or [],
        'verified': bool(verified),
        'evidence': evidence or {},
    }


def _history_sort_key(event):
    value = event.get('time')
    return (
        value in (None, ''),
        str(value or ''),
        str(event.get('action') or ''),
    )


def build_editing_history(
    timestamp_result,
    c2pa_result,
    software_result,
    project_file_result,
):
    """Assemble evidence records without treating timestamps as edit proof."""
    events = []
    warnings = []

    ai_usage = c2pa_result.get('ai_usage', {})
    if not isinstance(ai_usage, dict):
        ai_usage = {}
    c2pa_verified = c2pa_result.get('signature_valid') is True

    action_groups = [
        (
            ai_usage.get('creation_actions', []),
            'Creation action declared in the active C2PA manifest.',
        ),
        (
            ai_usage.get('editing_actions', []),
            'Editing action declared in the active C2PA manifest.',
        ),
    ]
    modified_regions = ai_usage.get('modified_regions', [])
    if not isinstance(modified_regions, list):
        modified_regions = []

    for action_group, default_description in action_groups:
        if not isinstance(action_group, list):
            continue
        for action in action_group:
            if not isinstance(action, dict):
                continue

            action_name = action.get('action')
            regions = [
                item.get('region')
                for item in modified_regions
                if isinstance(item, dict)
                and item.get('action') == action_name
                and item.get('region') is not None
            ]
            events.append(editing_history_event(
                time=action.get('when'),
                action=action_name,
                source='c2pa.actions',
                record_type='declared',
                description=(
                    action.get('description')
                    or default_description
                ),
                software=(
                    action.get('software_agent')
                    or action.get('software_agent_index')
                ),
                regions=regions,
                verified=c2pa_verified,
                evidence={
                    'digital_source_type': action.get(
                        'digital_source_type'
                    ),
                    'parameters': action.get('parameters', {}),
                    'manifest_trusted': c2pa_result.get('trusted'),
                },
            ))

    filesystem = timestamp_result.get('filesystem', {})
    media = timestamp_result.get('media', {})
    if not isinstance(filesystem, dict):
        filesystem = {}
    if not isinstance(media, dict):
        media = {}

    timestamp_sources = [
        (
            'filesystem.created_at',
            filesystem.get('created_at'),
            'file_observed_created',
            (
                'Filesystem creation timestamp observed; this does not prove '
                'the original content creation time.'
            ),
        ),
        (
            'filesystem.modified_at',
            filesystem.get('modified_at'),
            'file_observed_modified',
            (
                'Filesystem modification timestamp observed; this does not '
                'identify a specific editing action.'
            ),
        ),
        (
            'media.creation_time',
            media.get('creation_time'),
            'media_declared_created',
            'Creation timestamp embedded in the media metadata.',
        ),
        (
            'media.modification_time',
            media.get('modification_time'),
            'media_declared_modified',
            'Modification timestamp embedded in the media metadata.',
        ),
    ]

    for source, value, action, description in timestamp_sources:
        if value in (None, ''):
            continue
        events.append(editing_history_event(
            time=value,
            action=action,
            source=source,
            record_type=(
                'observed'
                if source.startswith('filesystem')
                else 'declared'
            ),
            description=description,
            verified=False,
            evidence={
                'timestamp_only': True,
                'is_edit_proof': False,
            },
        ))

    selected_project = project_file_result.get('selected')
    project_candidates = (
        [selected_project]
        if isinstance(selected_project, dict)
        else project_file_result.get('candidates', [])
    )
    if not isinstance(project_candidates, list):
        project_candidates = []

    for project in project_candidates:
        if not isinstance(project, dict):
            continue
        events.append(editing_history_event(
            time=None,
            action='potential_project_source_associated',
            source='project_file.discovery',
            record_type='inferred',
            description=(
                'A possible source project file was associated by file '
                'extension and asset role; the relationship is not verified.'
            ),
            verified=False,
            evidence={
                'path': project.get('path'),
                'file_hash': project.get('file_hash'),
                'relationship_basis': project.get('relationship_basis'),
            },
        ))

    unique_events = []
    seen = set()
    for event in events:
        identity = json.dumps(
            event,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )
        if identity not in seen:
            seen.add(identity)
            unique_events.append(event)
    unique_events.sort(key=_history_sort_key)

    if not c2pa_verified and any(
        event.get('source') == 'c2pa.actions'
        for event in unique_events
    ):
        warnings.append(
            'C2PA actions were found but the active manifest signature was '
            'not verified.'
        )
    if project_candidates:
        warnings.append(
            'Project-file associations are inferred candidates, not '
            'confirmed editing events.'
        )

    if timestamp_result.get('status') == 'file_missing':
        status = 'file_missing'
    elif unique_events:
        status = 'assembled'
    else:
        status = 'not_available'

    return {
        'status': status,
        'events': unique_events,
        'event_count': len(unique_events),
        'sources': sorted({
            event['source']
            for event in unique_events
        }),
        'software_context': software_result.get('primary'),
        'warnings': warnings,
    }


def _provenance_time(value):
    if value in (None, ''):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def indicator_check(name, result, source, explanation, value=None):
    return {
        'name': name,
        'result': bool(result),
        'value': value,
        'source': source,
        'explanation': explanation,
    }


def binary_indicator(
    indicator_id,
    label,
    available,
    checks,
    available_reason,
    unavailable_reason,
):
    return {
        'id': indicator_id,
        'label': label,
        'available': bool(available),
        'status': 'available' if available else 'not_available',
        'reason': available_reason if available else unavailable_reason,
        'checks': checks,
    }


def build_provenance_summary(
    file_hash_result,
    metadata_result,
    timestamp_result,
    c2pa_result,
    software_result,
    project_file_result,
    editing_history_result,
):
    """Build four evidence-availability indicators without a score."""
    conflicts = []
    warnings = []

    hash_value = file_hash_result.get('value')
    hash_valid = (
        file_hash_result.get('status') == 'computed'
        and isinstance(hash_value, str)
        and len(hash_value) == 64
        and all(character in '0123456789abcdefABCDEF' for character in hash_value)
    )
    file_integrity_checks = [
        indicator_check(
            'sha256_computed',
            hash_valid,
            'file_hash',
            (
                'Checks whether a complete SHA-256 digest was produced for '
                'the inspected bytes.'
            ),
            hash_value,
        ),
        indicator_check(
            'bytes_hashed',
            file_hash_result.get('bytes_hashed', 0) > 0,
            'file_hash',
            (
                'Shows whether file bytes were actually read by the hashing '
                'process.'
            ),
            file_hash_result.get('bytes_hashed', 0),
        ),
    ]

    c2pa_status = c2pa_result.get('status')
    c2pa_verified = (
        c2pa_status == 'verified'
        and c2pa_result.get('signature_valid') is True
    )
    manifest_present = bool(
        c2pa_result.get('active_manifest')
        or c2pa_result.get('manifest')
    )
    validation_errors = c2pa_result.get('validation_errors', [])
    validation_warnings = c2pa_result.get('validation_warnings', [])
    c2pa_checks = [
        indicator_check(
            'manifest_present',
            manifest_present,
            'c2pa_manifest',
            'Checks whether a C2PA manifest was found.',
            c2pa_result.get('active_manifest'),
        ),
        indicator_check(
            'signature_valid',
            c2pa_result.get('signature_valid') is True,
            'c2pa_manifest',
            'Checks the result of the C2PA signature validation process.',
            c2pa_result.get('signature_valid'),
        ),
        indicator_check(
            'signing_credential_trusted',
            c2pa_result.get('trusted') is True,
            'c2pa_manifest',
            (
                'Reports whether the signing credential is trusted; this is '
                'separate from cryptographic signature validity.'
            ),
            c2pa_result.get('trusted'),
        ),
        indicator_check(
            'no_validation_errors',
            not validation_errors,
            'c2pa_manifest',
            'Checks whether C2PA validation reported any errors.',
            len(validation_errors),
        ),
        indicator_check(
            'validation_warnings',
            not validation_warnings,
            'c2pa_manifest',
            'Reports whether validation completed without warnings.',
            len(validation_warnings),
        ),
    ]

    project_candidates = [
        item
        for item in project_file_result.get('candidates', [])
        if isinstance(item, dict)
    ]
    verified_projects = [
        item
        for item in project_candidates
        if item.get('relationship_verified') is True
    ]
    project_available = bool(verified_projects)
    project_checks = [
        indicator_check(
            'candidate_found',
            bool(project_candidates),
            'project_file',
            (
                'Checks whether a recognised source-project candidate was '
                'discovered.'
            ),
            len(project_candidates),
        ),
        indicator_check(
            'relationship_verified',
            project_available,
            'project_file',
            (
                'Requires explicit verification of the relationship between '
                'the project file and this output asset.'
            ),
            len(verified_projects),
        ),
        indicator_check(
            'project_hash_available',
            any(
                isinstance(item.get('file_hash'), dict)
                and item['file_hash'].get('status') == 'computed'
                for item in project_candidates
            ),
            'project_file',
            (
                'Checks whether a discovered project candidate has its own '
                'SHA-256 digest.'
            ),
        ),
    ]

    c2pa_actions = [
        action
        for action in c2pa_result.get('actions', [])
        if isinstance(action, dict)
    ]
    ai_disclosure = c2pa_result.get('ai_disclosure', {})
    if not isinstance(ai_disclosure, dict):
        ai_disclosure = {}
    ai_usage = c2pa_result.get('ai_usage', {})
    if not isinstance(ai_usage, dict):
        ai_usage = {}
    ai_disclosure_present = ai_disclosure.get('present') is True
    declared_process_available = bool(c2pa_actions or ai_disclosure_present)
    history_events = editing_history_result.get('events', [])
    declared_history_events = [
        event
        for event in history_events
        if isinstance(event, dict)
        and event.get('record_type') == 'declared'
    ]
    modified_regions = ai_usage.get('modified_regions', [])
    if not isinstance(modified_regions, list):
        modified_regions = []
    editing_ai_checks = [
        indicator_check(
            'c2pa_actions_present',
            bool(c2pa_actions),
            'c2pa_manifest.actions',
            (
                'Checks whether creation or editing actions were declared '
                'in C2PA.'
            ),
            len(c2pa_actions),
        ),
        indicator_check(
            'declared_history_events',
            bool(declared_history_events),
            'editing_history',
            (
                'Shows how many declared events were assembled into the '
                'evidence timeline.'
            ),
            len(declared_history_events),
        ),
        indicator_check(
            'ai_disclosure_present',
            ai_disclosure_present,
            'c2pa_manifest.ai_disclosure',
            'Checks for a C2PA AI disclosure assertion.',
            ai_disclosure.get('assertions', []),
        ),
        indicator_check(
            'ai_generated_declared',
            ai_usage.get('ai_generated') is True,
            'c2pa_manifest.ai_usage',
            (
                'Reports whether an AI-generated digital source type was '
                'declared.'
            ),
            ai_usage.get('ai_generated'),
        ),
        indicator_check(
            'ai_modified_declared',
            ai_usage.get('ai_modified') is True,
            'c2pa_manifest.ai_usage',
            (
                'Reports whether an AI-modified digital source type was '
                'declared.'
            ),
            ai_usage.get('ai_modified'),
        ),
        indicator_check(
            'modified_regions_present',
            bool(modified_regions),
            'c2pa_manifest.ai_usage',
            'Reports whether affected regions were declared.',
            len(modified_regions),
        ),
        indicator_check(
            'timestamps_available',
            timestamp_result.get('status') in {'extracted', 'partial'},
            'timestamps',
            'Shows whether timestamps were available as supporting context.',
            timestamp_result.get('status'),
        ),
        indicator_check(
            'software_identified',
            software_result.get('status') == 'identified',
            'software',
            (
                'Shows whether software information was available as '
                'supporting context.'
            ),
            software_result.get('primary'),
        ),
        indicator_check(
            'metadata_extracted',
            metadata_result.get('status') == 'extracted',
            'metadata',
            'Shows whether metadata was extracted as supporting context.',
            metadata_result.get('status'),
        ),
    ]

    indicators = {
        'file_integrity': binary_indicator(
            'file_integrity',
            'File integrity and identity',
            hash_valid,
            file_integrity_checks,
            'A complete SHA-256 digest identifies the inspected file bytes.',
            'A complete SHA-256 digest is not available.',
        ),
        'c2pa_provenance': binary_indicator(
            'c2pa_provenance',
            'Verified C2PA provenance',
            c2pa_verified,
            c2pa_checks,
            (
                'The active C2PA manifest passed signature validation; '
                'credential trust is reported separately.'
            ),
            (
                'No C2PA manifest was verified; absence does not prove '
                'fabrication.'
            ),
        ),
        'source_project': binary_indicator(
            'source_project',
            'Verified source-project evidence',
            project_available,
            project_checks,
            (
                'At least one source-project relationship was explicitly '
                'verified.'
            ),
            'No source-project relationship has been explicitly verified.',
        ),
        'editing_ai_transparency': binary_indicator(
            'editing_ai_transparency',
            'Editing and AI-use transparency',
            declared_process_available,
            editing_ai_checks,
            (
                'C2PA actions and/or an AI disclosure describe the creation '
                'or editing process.'
            ),
            (
                'No C2PA actions or AI disclosure describe the creation or '
                'editing process.'
            ),
        ),
    }

    filesystem = timestamp_result.get('filesystem', {})
    media = timestamp_result.get('media', {})
    if not isinstance(filesystem, dict):
        filesystem = {}
    if not isinstance(media, dict):
        media = {}
    timestamp_pairs = [
        (
            'filesystem_timestamp_order',
            filesystem.get('created_at'),
            filesystem.get('modified_at'),
            (
                'Filesystem modification time precedes filesystem creation '
                'time.'
            ),
        ),
        (
            'media_timestamp_order',
            media.get('creation_time'),
            media.get('modification_time'),
            (
                'Embedded media modification time precedes embedded media '
                'creation time.'
            ),
        ),
    ]
    for code, created_value, modified_value, message in timestamp_pairs:
        created_time = _provenance_time(created_value)
        modified_time = _provenance_time(modified_value)
        if (
            created_time is not None
            and modified_time is not None
            and modified_time < created_time
        ):
            conflicts.append({
                'code': code,
                'description': message,
                'source': 'timestamps',
            })

    if c2pa_status == 'invalid':
        conflicts.append({
            'code': 'c2pa_validation_failed',
            'description': (
                'A C2PA manifest was present but did not pass validation; '
                'this alone does not prove the content is fake.'
            ),
            'source': 'c2pa_manifest',
        })

    has_ai_source_type = (
        ai_usage.get('ai_generated') is True
        or ai_usage.get('ai_modified') is True
    )
    if ai_disclosure_present and not has_ai_source_type:
        warnings.append(
            'An AI disclosure is present, but no AI-related '
            'digitalSourceType was extracted from the C2PA actions.'
        )
    elif has_ai_source_type and not ai_disclosure_present:
        warnings.append(
            'An AI-related digitalSourceType is present without a '
            'c2pa.ai-disclosure assertion.'
        )

    available_count = sum(
        indicator['available']
        for indicator in indicators.values()
    )
    indicator_count = len(indicators)
    if file_hash_result.get('status') == 'file_missing':
        status = 'file_missing'
    elif conflicts:
        status = 'review_required'
    elif available_count == indicator_count:
        status = 'complete'
    elif available_count > 0:
        status = 'partial'
    else:
        status = 'insufficient'

    available_indicators = [
        indicator_id
        for indicator_id, indicator in indicators.items()
        if indicator['available']
    ]
    missing_indicators = [
        indicator_id
        for indicator_id, indicator in indicators.items()
        if not indicator['available']
    ]
    return {
        'assessment_model': 'four_evidence_indicators_no_score_v1',
        'assessment_interpretation': (
            'Indicator availability and inspection details only; no '
            'authenticity score or probability is calculated.'
        ),
        'status': status,
        'available_indicator_count': int(available_count),
        'indicator_count': indicator_count,
        'coverage': f'{available_count}/{indicator_count}',
        'indicators': indicators,
        'available_indicators': available_indicators,
        'conflicts': conflicts,
        'missing_indicators': missing_indicators,
        'warnings': warnings,
    }


def simplify_provenance_indicators(provenance):
    labels = {
        'file_integrity': 'File Integrity',
        'c2pa_provenance': 'C2PA Provenance',
        'source_project': 'Source Project Evidence',
        'editing_ai_transparency': 'Editing / AI Transparency',
    }
    simplified = {}
    for asset_name, asset in provenance.items():
        indicators = asset.get('provenance_summary', {}).get('indicators', {})
        simplified[asset_name] = {
            label: indicators.get(indicator_id, {}).get(
                'status',
                'not_available',
            )
            for indicator_id, label in labels.items()
        }
    return simplified


def inspect_asset_basics(asset_name, file_path):
    if asset_name not in ASSET_TYPES:
        raise ValueError(f'Unknown asset name: {asset_name}')

    path = Path(file_path)
    metadata = (
        extract_pdf_metadata(path)
        if asset_name == 'storyboard'
        else extract_video_metadata(path)
    )
    c2pa_manifest = inspect_c2pa(path)
    return {
        'type': ASSET_TYPES[asset_name],
        'path': str(path),
        'file_hash': compute_sha256(path),
        'metadata': metadata,
        'timestamps': extract_asset_timestamps(
            asset_name,
            path,
            metadata,
        ),
        'c2pa_manifest': c2pa_manifest,
        'software': extract_asset_software(
            asset_name,
            metadata,
            c2pa_manifest,
        ),
    }


def collect_basic_provenance(config):
    """Collect the Step 3 basic provenance entry for all three assets."""
    missing_keys = [
        config_key
        for config_key in ASSET_PATH_KEYS.values()
        if config_key not in config
    ]
    if missing_keys:
        raise ValueError(
            'Missing provenance config keys: '
            + ', '.join(sorted(missing_keys))
        )

    assets = {
        asset_name: inspect_asset_basics(
            asset_name,
            config[config_key],
        )
        for asset_name, config_key in ASSET_PATH_KEYS.items()
    }
    project_files = collect_project_file_evidence(config)
    for asset_name, asset in assets.items():
        asset['project_file'] = project_files[asset_name]
        asset['editing_history'] = build_editing_history(
            asset['timestamps'],
            asset['c2pa_manifest'],
            asset['software'],
            asset['project_file'],
        )
        asset['provenance_summary'] = build_provenance_summary(
            asset['file_hash'],
            asset['metadata'],
            asset['timestamps'],
            asset['c2pa_manifest'],
            asset['software'],
            asset['project_file'],
            asset['editing_history'],
        )
    return assets


__all__ = [
    'collect_basic_provenance',
    'collect_project_file_evidence',
    'compute_sha256',
    'extract_asset_timestamps',
    'extract_asset_software',
    'extract_ai_disclosures',
    'extract_c2pa_actions',
    'extract_c2pa_software',
    'extract_filesystem_timestamps',
    'extract_pdf_metadata',
    'extract_pdf_software',
    'extract_video_metadata',
    'extract_video_software',
    'discover_project_files',
    'inspect_c2pa',
    'inspect_asset_basics',
    'associate_project_files',
    'build_editing_history',
    'build_provenance_summary',
    'binary_indicator',
    'editing_history_event',
    'indicator_check',
    'interpret_ai_actions',
    'normalize_c2pa_assertions',
    'add_software_candidate',
    'parse_pdf_datetime',
    'simplify_provenance_indicators',
]
