"""Independent provenance rubrics retained from the review application."""
from datetime import datetime, timezone


TIMESTAMP_FIELDS = (
    ('embedded_creation_time', 'media', 'creation_time', 'declared', 35.0, 'creation'),
    ('embedded_modification_time', 'media', 'modification_time', 'declared', 30.0, 'modification'),
    ('filesystem_creation_time', 'filesystem', 'created_at', 'observed', 20.0, 'creation'),
    ('filesystem_modification_time', 'filesystem', 'modified_at', 'observed', 15.0, 'modification'),
)


def _parse_timestamp(value):
    if value in (None, ''):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _chronology_result(delta_seconds):
    """Score direction with a one-day tolerance for timezone/export noise."""
    if delta_seconds >= 0:
        return 100.0, 'consistent', 'Evidence is not later than the corresponding Final timestamp.'
    late_by = abs(delta_seconds)
    if late_by <= 24 * 3600:
        return 70.0, 'minor_time_difference', 'Evidence is later by no more than 24 hours; timezone or export timing may explain the difference.'
    if late_by <= 7 * 24 * 3600:
        return 25.0, 'chronology_requires_review', 'Evidence is later by between one and seven days and requires contextual review.'
    return 0.0, 'chronology_conflict', 'Evidence is later by more than seven days and presents a strong chronology review signal.'


def _support_status(score):
    if score is None:
        return 'timestamp_evidence_unavailable'
    if score >= 85:
        return 'strong_timestamp_support'
    if score >= 70:
        return 'moderate_timestamp_support'
    if score >= 50:
        return 'limited_timestamp_support'
    if score > 0:
        return 'weak_or_conflicting_timestamp_evidence'
    return 'severe_timestamp_conflict'


def _proximity_band(hours, kind):
    if kind == 'creation':
        if hours <= 1:
            return 'near_simultaneous_creation', 15.0
        if hours <= 6:
            return 'highly_compressed_timeline', 10.0
        if hours <= 24:
            return 'very_short_lead_time', 5.0
        if hours <= 7 * 24:
            return 'short_lead_time', 0.0
        return 'normal_lead_time', 0.0
    if hours < 1:
        return 'near_simultaneous_modification', 5.0
    if hours <= 6:
        return 'very_close_modification_times', 2.0
    if hours <= 24:
        return 'close_modification_times', 0.0
    return 'no_proximity_signal', 0.0


def _relationship_proximity(comparisons, evidence, final):
    by_type = {item['timestamp_type']: item for item in comparisons}
    embedded_creation = by_type['embedded_creation_time']
    filesystem_creation = by_type['filesystem_creation_time']
    embedded_modification = by_type['embedded_modification_time']
    filesystem_modification = by_type['filesystem_modification_time']

    findings = []
    deduction = 0.0

    # Creation lead time is meaningful only when Evidence is not later than Final.
    creation = embedded_creation if embedded_creation['comparable'] else filesystem_creation
    if creation['comparable'] and creation['delta_seconds_final_minus_evidence'] >= 0:
        hours = creation['delta_seconds_final_minus_evidence'] / 3600.0
        status, proposed = _proximity_band(hours, 'creation')
        embedded = creation is embedded_creation
        corroborated = embedded_creation['comparable'] and filesystem_creation['comparable']
        applied = proposed if embedded else 0.0
        deduction += applied
        findings.append({
            'check': 'creation_lead_time', 'gap_hours': round(hours, 3), 'status': status,
            'source': creation['timestamp_type'], 'confidence': 'high' if corroborated else ('medium' if embedded else 'low'),
            'proposed_deduction': proposed, 'deduction_applied': applied,
            'reason': ('Embedded creation time supports this proximity finding.' if embedded else
                       'Only filesystem creation time supports this finding, so it is reported without a deduction.'),
        })

    # Modification timestamps often reflect a batch export, so the penalty is deliberately small.
    modification = embedded_modification if embedded_modification['comparable'] else filesystem_modification
    if modification['comparable']:
        hours = abs(modification['delta_seconds_final_minus_evidence']) / 3600.0
        status, proposed = _proximity_band(hours, 'modification')
        embedded = modification is embedded_modification
        corroborated = embedded_modification['comparable'] and filesystem_modification['comparable']
        applied = proposed if embedded else 0.0
        deduction += applied
        findings.append({
            'check': 'modification_time_gap', 'gap_hours': round(hours, 3), 'status': status,
            'source': modification['timestamp_type'], 'confidence': 'high' if corroborated else ('medium' if embedded else 'low'),
            'proposed_deduction': proposed, 'deduction_applied': applied,
            'reason': ('Embedded modification time supports this proximity finding.' if embedded else
                       'Filesystem modification time may reflect copying or batch export, so no deduction is applied.'),
        })

    evidence_signed = _parse_timestamp(evidence.get('c2pa_manifest', {}).get('signed_at'))
    final_signed = _parse_timestamp(final.get('c2pa_manifest', {}).get('signed_at'))
    signed_corroboration = None
    if evidence_signed and final_signed:
        signed_gap = (final_signed - evidence_signed).total_seconds() / 3600.0
        signed_corroboration = {
            'evidence_signed_at': evidence_signed.isoformat(), 'final_signed_at': final_signed.isoformat(),
            'gap_hours_final_minus_evidence': round(signed_gap, 3),
            'status': 'signed_time_available',
            'note': 'C2PA signing times strengthen context but are not substituted for media creation times.',
        }
        for finding in findings:
            if finding['status'] not in {'normal_lead_time', 'no_proximity_signal'}:
                finding['confidence'] = 'very_high'

    return {
        'deduction': min(15.0, round(deduction, 2)),
        'findings': findings,
        'signed_timestamp_corroboration': signed_corroboration,
        'review_recommended': any(item['status'] in {
            'near_simultaneous_creation', 'highly_compressed_timeline',
            'near_simultaneous_modification', 'very_close_modification_times',
        } for item in findings),
    }

def timestamp_comparisons(provenance):
    """Score timestamp availability, chronology and unusually compressed timing."""
    final_timestamps = provenance.get('final', {}).get('timestamps', {})
    output = []
    for evidence_name in ('storyboard', 'animatic'):
        if evidence_name not in provenance or 'final' not in provenance:
            continue
        evidence_timestamps = provenance[evidence_name].get('timestamps', {})
        comparisons = []
        for label, section, key, evidence_type, weight, kind in TIMESTAMP_FIELDS:
            evidence_value = evidence_timestamps.get(section, {}).get(key)
            final_value = final_timestamps.get(section, {}).get(key)
            evidence_time = _parse_timestamp(evidence_value)
            final_time = _parse_timestamp(final_value)
            if evidence_time is None or final_time is None:
                score = None
                status = 'not_comparable'
                delta_seconds = None
                reason = 'One or both timestamps are missing or cannot be parsed.'
            else:
                delta_seconds = (final_time - evidence_time).total_seconds()
                score, status, reason = _chronology_result(delta_seconds)
            comparisons.append({
                'timestamp_type': label, 'record_type': evidence_type, 'time_semantics': kind,
                'weight_percent': weight, 'evidence_value': evidence_value, 'final_value': final_value,
                'delta_seconds_final_minus_evidence': delta_seconds, 'comparable': score is not None,
                'score': score, 'status': status, 'reason': reason,
            })

        available_weight = sum(item['weight_percent'] for item in comparisons if item['comparable'])
        availability = round(available_weight, 2)
        consistency = (sum(item['weight_percent'] * item['score'] for item in comparisons if item['comparable'])
                       / available_weight) if available_weight else None
        base_score = (available_weight / 100.0) * (30.0 + 0.7 * consistency) if consistency is not None else None
        proximity = _relationship_proximity(comparisons, provenance[evidence_name], provenance['final'])
        final_score = max(0.0, base_score - proximity['deduction']) if base_score is not None else None
        final_score = round(final_score, 2) if final_score is not None else None
        availability_points = round((available_weight / 100.0) * 30.0, 2)
        chronology_points = round((available_weight / 100.0) * 0.7 * consistency, 2) if consistency is not None else 0.0
        missing_points = round((1.0 - available_weight / 100.0) * 100.0, 2)
        chronology_lost_points = round(
            (available_weight / 100.0) * 0.7 * (100.0 - consistency), 2
        ) if consistency is not None else 0.0
        conflict_count = sum(item['status'] in {'chronology_requires_review', 'chronology_conflict'} for item in comparisons)
        reasons = []
        if final_score is None:
            reasons.append('No timestamp type was comparable between Evidence and Final.')
        else:
            reasons.append(f'{availability:.0f}% of the weighted timestamp evidence was comparable.')
            reasons.append(f'Comparable timestamps had {consistency:.2f}% weighted chronology consistency.')
            if proximity['deduction']:
                reasons.append(f'{proximity["deduction"]:.2f} points were deducted for unusually close embedded timestamps.')
        output.append({
            'relationship': f'{evidence_name}_to_final', 'evidence_asset': evidence_name,
            'final_asset': 'final', 'timestamp_score': final_score,
            'base_timestamp_score': round(base_score, 2) if base_score is not None else None,
            'availability_score': availability, 'chronology_consistency': round(consistency, 2) if consistency is not None else None,
            'proximity_deduction': proximity['deduction'], 'status': _support_status(final_score),
            'review_recommended': proximity['review_recommended'] or conflict_count > 0,
            'reason': ' '.join(reasons), 'temporal_proximity': proximity,
            'score_breakdown': {
                'formula': 'final = availability_points + chronology_points - proximity_deduction',
                'availability_points_earned': availability_points,
                'chronology_points_earned': chronology_points,
                'points_not_earned_missing_timestamps': missing_points,
                'points_not_earned_chronology': chronology_lost_points,
                'proximity_points_deducted': proximity['deduction'],
                'base_points_earned': round(base_score, 2) if base_score is not None else None,
                'final_points': final_score,
            },
            'comparisons': comparisons,
            'limitations': ['Filesystem timestamps can change when files are copied, downloaded, or restored.',
                            'Embedded timestamps are self-declared metadata unless independently signed.',
                            'A compressed timeline is a review signal, not proof that evidence is invalid.',
                            'Chronological order is supporting context, not proof of authorship or authenticity.'],
        })

    relationship_scores = [item['timestamp_score'] for item in output if item['timestamp_score'] is not None]
    project_score = round(sum(relationship_scores) / len(relationship_scores), 2) if relationship_scores else None
    chain = _production_chain_analysis(provenance)
    return {
        'method': 'weighted_timestamp_evidence_v2', 'project_timestamp_score': project_score,
        'project_status': _support_status(project_score), 'relationships': output,
        'production_chain_analysis': chain,
        'score_interpretation': ('The score combines weighted timestamp availability and chronology, then applies a capped '
                                 'deduction for unusually close embedded timestamps. It is evidence support, not an authenticity probability.'),
    }


def _production_chain_analysis(provenance):
    """Describe Storyboard → Animatic → Final timing when all three exist."""
    if not all(name in provenance for name in ('storyboard', 'animatic', 'final')):
        return {'applicable': False, 'status': 'not_applicable', 'reason': 'All three production stages are required.'}

    def preferred_time(asset, kind):
        timestamps = provenance[asset].get('timestamps', {})
        media_key = 'creation_time' if kind == 'creation' else 'modification_time'
        filesystem_key = 'created_at' if kind == 'creation' else 'modified_at'
        embedded = _parse_timestamp(timestamps.get('media', {}).get(media_key))
        filesystem = _parse_timestamp(timestamps.get('filesystem', {}).get(filesystem_key))
        return (embedded, 'embedded') if embedded else ((filesystem, 'filesystem') if filesystem else (None, None))

    creation = {name: preferred_time(name, 'creation') for name in ('storyboard', 'animatic', 'final')}
    modification = {name: preferred_time(name, 'modification') for name in ('storyboard', 'animatic', 'final')}
    result = {'applicable': True, 'creation_times': {}, 'modification_times': {}, 'review_recommended': False}
    for name, (value, source) in creation.items():
        result['creation_times'][name] = {'value': value.isoformat() if value else None, 'source': source}
    for name, (value, source) in modification.items():
        result['modification_times'][name] = {'value': value.isoformat() if value else None, 'source': source}

    creation_values = [creation[name][0] for name in ('storyboard', 'animatic', 'final')]
    if all(creation_values):
        ordered = creation_values[0] <= creation_values[1] <= creation_values[2]
        span_hours = (max(creation_values) - min(creation_values)).total_seconds() / 3600.0
        all_embedded = all(creation[name][1] == 'embedded' for name in ('storyboard', 'animatic', 'final'))
        result['creation_span_hours'] = round(span_hours, 3)
        if not ordered:
            result.update(status='production_chain_chronology_conflict', review_recommended=True,
                          reason='The observed creation times do not follow Storyboard → Animatic → Final order.')
        elif span_hours <= 1 and not all_embedded:
            result.update(status='filesystem_chain_proximity_observed', review_recommended=True,
                          reason='The available file-record times are within one hour, but at least one comes from the filesystem and may reflect copying, upload or batch export rather than creation.')
        elif span_hours <= 24 and not all_embedded:
            result.update(status='filesystem_chain_timing_observed',
                          reason='The available file-record times follow the production order, but at least one comes from the filesystem and is weak creation evidence.')
        elif span_hours <= 1:
            result.update(status='near_simultaneous_full_chain_generation', review_recommended=True,
                          reason='All three stages were created within one hour; contextual review is recommended.')
        elif span_hours <= 24:
            result.update(status='rapid_full_chain_generation', review_recommended=True,
                          reason='All three stages were created within 24 hours; this is a compressed production timeline.')
        else:
            result.update(status='production_chain_chronology_supported',
                          reason='Observed creation times follow Storyboard → Animatic → Final order.')
    else:
        result.update(status='production_chain_not_comparable', reason='One or more production stages lack a comparable creation time.')

    filesystem_modifications = [
        _parse_timestamp(provenance[name].get('timestamps', {}).get('filesystem', {}).get('modified_at'))
        for name in ('storyboard', 'animatic', 'final')
    ]
    if all(filesystem_modifications):
        gap = (max(filesystem_modifications) - min(filesystem_modifications)).total_seconds() / 3600.0
        result['filesystem_modification_span_hours'] = round(gap, 3)
        result['batch_export_or_copy_possible'] = gap <= 1
    else:
        result['batch_export_or_copy_possible'] = None
    return result

def provenance_scores(provenance_summary):
    """Score every provenance indicator with an explicit check-level rubric."""
    rubrics = {'file_integrity': {'sha256_computed': (70, True), 'bytes_hashed': (30, True)}, 'c2pa_provenance': {'manifest_present': (20, True), 'signature_valid': (35, True), 'signing_credential_trusted': (20, True), 'no_validation_errors': (15, True), 'validation_warnings': (10, True)}, 'source_project': {'candidate_found': (25, True), 'project_hash_available': (25, True), 'relationship_verified': (50, True)}, 'editing_ai_transparency': {'c2pa_actions_present': (20, True), 'declared_history_events': (20, True), 'timestamps_available': (20, True), 'software_identified': (20, True), 'metadata_extracted': (20, True)}}
    assets = {}
    for asset_name, item in provenance_summary.items():
        indicators = item.get('indicators', {})
        indicator_scores = {}
        for indicator_id, indicator in indicators.items():
            if not isinstance(indicator, dict):
                continue
            checks_by_name = {check.get('name'): check for check in indicator.get('checks', []) if isinstance(check, dict)}
            rubric = rubrics.get(indicator_id, {})
            components = []
            for check_name, (maximum_points, applicable) in rubric.items():
                check = checks_by_name.get(check_name, {})
                passed = check.get('result') is True
                components.append({'check': check_name, 'applicable': applicable, 'passed': passed, 'points_awarded': float(maximum_points if passed else 0), 'maximum_points': float(maximum_points), 'observed_value': check.get('value'), 'source': check.get('source'), 'explanation': check.get('explanation')})
            score = sum((component['points_awarded'] for component in components))
            maximum = sum((component['maximum_points'] for component in components if component['applicable']))
            if indicator_id == 'c2pa_provenance' and (not checks_by_name.get('manifest_present', {}).get('result')):
                score = 0.0
                gate_reason = 'No manifest was found, so validation-cleanliness checks cannot earn C2PA points.'
            else:
                gate_reason = None
            indicator_scores[indicator_id] = {'label': indicator.get('label', indicator_id), 'score': round(100.0 * score / maximum, 2) if maximum else None, 'points_awarded': score, 'maximum_points': maximum, 'available': indicator.get('available') is True, 'reason': indicator.get('reason'), 'gate_reason': gate_reason, 'components': components, 'unscored_context_checks': [check for name, check in checks_by_name.items() if name not in rubric]}
        assets[asset_name] = {'status': item.get('status'), 'review_required': bool(item.get('conflicts')), 'indicator_scores': indicator_scores}
    return {'method': 'independent_weighted_check_rubrics_v2', 'score_interpretation': 'Each indicator is scored independently from its documented checks. No aggregate provenance score is calculated.', 'rubric_basis': {'file_integrity': 'Digest completion is primary; successful byte reading is supporting evidence.', 'c2pa_provenance': 'Manifest presence opens the gate; signature validity and credential trust carry the most weight.', 'source_project': 'A candidate alone is weak; an explicitly verified relationship carries the most weight.', 'editing_ai_transparency': 'Five independent forms of process context contribute equally. AI absence is not penalised.'}, 'assets': assets, 'limitations': ['Indicator scores measure evidence quality and availability, not authenticity probability.', 'A low score means supporting provenance evidence is limited; it does not prove fabrication.', 'The four indicator scores must not be added or averaged into a single provenance score.', 'Conflicts are reported separately for human review.']}
