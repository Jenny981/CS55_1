from __future__ import annotations

import json
from pathlib import Path


def load_config(config_path):
    config_path = Path(config_path).resolve()
    data = json.loads(config_path.read_text(encoding='utf-8'))
    base = config_path.parent

    path_keys = [
        'storyboard_path',
        'animatic_path',
        'final_path',
        'storyboard_processed_dir',
        'animatic_processed_dir',
        'final_processed_dir',
    ]

    if 'project_search_root' in data:
        path_keys.append('project_search_root')

    for key in path_keys:
        value = Path(data[key])
        if not value.is_absolute():
            value = (base / value).resolve()
        data[key] = value

    for mapping in ('source_project_paths', 'source_project_unsigned_paths'):
        if mapping not in data:
            continue
        if not isinstance(data[mapping], dict):
            raise ValueError(f'{mapping} must be an object')
        data[mapping] = {
            key: (Path(value) if Path(value).is_absolute() else (base / value).resolve())
            for key, value in data[mapping].items()
        }
    return data
