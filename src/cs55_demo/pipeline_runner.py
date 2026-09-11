from __future__ import annotations

import json
from pathlib import Path

from .embeddings import prepare_embeddings
from .matching import (
    calculate_storyboard_animatic_similarity,
    calculate_animatic_final_similarity_matrix,
    sequence_aware_storyboard_animatic_matching,
    sequence_aware_animatic_final_matching,
)
from .metrics import calculate_chain_metrics
from .evidence_chain_builder import build_libevchain_bundle


def run_full_pipeline(config, use_cache=True, cache_path=None, embedder=None):
    embedding_data = prepare_embeddings(
        config,
        use_cache=use_cache,
        cache_path=cache_path,
        embedder=embedder,
    )

    sa_matrix = calculate_storyboard_animatic_similarity(
        embedding_data['storyboard_embeddings'],
        embedding_data['animatic_embeddings'],
    )
    af_matrix = calculate_animatic_final_similarity_matrix(
        embedding_data['animatic_embeddings'],
        embedding_data['final_embeddings'],
    )

    prepared_data = {
        **embedding_data,
        'storyboard_animatic_similarity': sa_matrix,
        'animatic_final_similarity_matrix': af_matrix,
        'ordered_sa_matches': sequence_aware_storyboard_animatic_matching(sa_matrix),
        'ordered_af_matches': sequence_aware_animatic_final_matching(af_matrix),
    }

    metrics = calculate_chain_metrics(
        prepared_data,
        expected_final_count=config.get('expected_final_count'),
    )

    bundle = build_libevchain_bundle(config, prepared_data['storyboard_files'])

    result = {
        'dataset_name': config['dataset_name'],
    
        'chain_metrics': {
            'coherence': metrics['coherence'],
            'confidence': metrics['confidence'],
            'coverage': metrics['coverage'],
            'completeness': metrics['completeness'],
        },
        'stage_metrics': {
            'storyboard_to_animation_similarity': metrics['storyboard_animatic_similarity'],
            'animation_to_final_similarity': metrics['animatic_final_similarity'],
        },
        'coverage_breakdown': {
            'animatic_coverage': metrics['animatic_coverage'],
            'final_coverage': metrics['final_coverage'],
            'used_animatic_shots': metrics['used_animatic_shots'],
            'total_animatic_shots': metrics['total_animatic_shots'],
            'used_final_shots': metrics['used_final_shots'],
            'total_final_shots': metrics['total_final_shots'],
        },
    }

    return result, bundle


def save_outputs(result, bundle, output_dir='outputs'):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / 'final_evidence_chain_result.json'
    bundle_path = output_dir / 'evidence_chain_bundle.json'

    result_path.write_text(json.dumps(result, indent=4, ensure_ascii=False), encoding='utf-8')
    bundle_path.write_text(json.dumps(bundle, indent=4, ensure_ascii=False), encoding='utf-8')
    return result_path, bundle_path
