from __future__ import annotations

import hashlib
import string


def calculate_sha256(file_path):
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def build_storyboard_artefacts(storyboard_files):
    artefacts = []
    seen_hashes = set()

    for file_path in storyboard_files:
        file_hash = calculate_sha256(file_path)
        if file_hash in seen_hashes:
            continue
        seen_hashes.add(file_hash)
        artefacts.append({
            'artefact_hash': file_hash,
            'artefact_type': 'image',
            'evidence': [],
            'attributes': {},
        })

    return artefacts


def _reusable_sha256(provenance, asset_name):
    """Return a previously computed SHA-256 value when it is trustworthy."""
    if not isinstance(provenance, dict):
        return None

    hash_record = provenance.get(asset_name, {}).get('file_hash', {})
    value = hash_record.get('value')
    if (
        hash_record.get('status') == 'computed'
        and hash_record.get('algorithm') == 'sha256'
        and isinstance(value, str)
        and len(value) == 64
        and all(character in string.hexdigits for character in value)
    ):
        return value.lower()
    return None


def build_libevchain_bundle(config, storyboard_files, provenance=None):
    storyboard_artefacts = build_storyboard_artefacts(storyboard_files)
    animatic_hash = (
        _reusable_sha256(provenance, 'animatic')
        or calculate_sha256(config['animatic_path'])
    )
    final_hash = (
        _reusable_sha256(provenance, 'final')
        or calculate_sha256(config['final_path'])
    )

    animatic_artefact = {
        'artefact_hash': animatic_hash,
        'artefact_type': 'video',
        'evidence': [
            {
                'hash': item['artefact_hash'],
                'relationship_type': 'storyboard-to-animation',
                'attributes': {},
            }
            for item in storyboard_artefacts
        ],
        'attributes': {},
    }

    final_artefact = {
        'artefact_hash': final_hash,
        'artefact_type': 'video',
        'evidence': [
            {
                'hash': animatic_hash,
                'relationship_type': 'animation-to-final',
                'attributes': {},
            }
        ],
        'attributes': {},
    }

    bundle = {
        'hash_method': 'sha256',
        'final_artefact_hash': final_hash,
        'artefacts': storyboard_artefacts + [animatic_artefact, final_artefact],
    }
    if provenance is not None:
        bundle['provenance'] = provenance
    return bundle
