from pathlib import Path
import math
import uuid
import cv2
import pandas as pd

def classify_near_blank_frame(frame, dark_value=10, bright_value=245, blank_fraction=0.98):
    """Detect near-uniform black or white frames; retain normal monochrome footage."""
    if frame is None or frame.size == 0:
        raise ValueError('Frame is empty')
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    dark_fraction = float((gray <= dark_value).mean())
    bright_fraction = float((gray >= bright_value).mean())
    if dark_fraction >= blank_fraction:
        reason = 'near_black'
    elif bright_fraction >= blank_fraction:
        reason = 'near_white'
    else:
        reason = None
    return {'blank_reason': reason, 'gray_mean': float(gray.mean()), 'gray_std': float(gray.std()), 'dark_fraction': dark_fraction, 'bright_fraction': bright_fraction}

def extract_time_samples(video_path, output_root, prefix, interval_sec=2.0, start_sec=0.0, end_sec=None, skip_near_blank=False, dark_value=10, bright_value=245, blank_fraction=0.98):
    if not math.isfinite(interval_sec) or interval_sec <= 0:
        raise ValueError('Sampling interval must be positive')
    if not math.isfinite(start_sec) or start_sec < 0:
        raise ValueError('Start time must be finite and nonnegative')
    if end_sec is not None:
        if not math.isfinite(end_sec) or end_sec <= start_sec:
            raise ValueError('End time must be empty or finite and greater than start time')
    if not 0 <= dark_value < bright_value <= 255:
        raise ValueError('Thresholds must satisfy 0 <= dark < bright <= 255')
    if not 0 < blank_fraction <= 1:
        raise ValueError('blank_fraction must be in (0, 1]')
    video_path = Path(video_path).resolve()
    cap = cv2.VideoCapture(str(video_path))
    kept_records, audit_records = ([], [])
    try:
        if not cap.isOpened():
            raise ValueError(f'Cannot open video: {video_path}')
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if not math.isfinite(fps) or fps <= 0 or count <= 0:
            raise ValueError('Invalid video FPS or frame count')
        duration = count / fps
        if start_sec >= duration:
            raise ValueError(f'Start time {start_sec:g}s exceeds duration {duration:.3f}s')
        effective_end_sec = duration if end_sec is None else min(end_sec, duration)
        if effective_end_sec <= start_sec:
            raise ValueError('Trimmed video interval is empty')
        output_dir = Path(output_root) / (prefix + '_' + uuid.uuid4().hex[:12])
        output_dir.mkdir(parents=True, exist_ok=False)
        previous_frame = -1
        sample_count = max(0, math.ceil((effective_end_sec - start_sec) / interval_sec))
        for source_sample_index in range(1, sample_count + 1):
            requested_sec = start_sec + (source_sample_index - 1) * interval_sec
            frame_index = min(int(round(requested_sec * fps)), count - 1)
            if frame_index == previous_frame:
                continue
            if not cap.set(cv2.CAP_PROP_POS_FRAMES, frame_index):
                raise RuntimeError(f'Cannot seek to frame {frame_index}')
            ok, frame = cap.read()
            if not ok or frame is None:
                raise RuntimeError(f'Cannot decode frame near {requested_sec:.3f}s; stopping to avoid silently missing samples')
            decoded_index = int(round(cap.get(cv2.CAP_PROP_POS_FRAMES))) - 1
            if decoded_index != frame_index:
                raise RuntimeError(f'Seek mismatch: requested {frame_index}, decoded {decoded_index}')
            reported_sec = float(cap.get(cv2.CAP_PROP_POS_MSEC)) / 1000
            estimated_sec = frame_index / fps
            use_reported = math.isfinite(reported_sec) and (reported_sec > 0 or frame_index == 0)
            timestamp = reported_sec if use_reported else estimated_sec
            quality = classify_near_blank_frame(frame, dark_value, bright_value, blank_fraction)
            skipped = bool(skip_near_blank and quality['blank_reason'] is not None)
            base = {'source_sample_index': source_sample_index, 'requested_sec': requested_sec, 'timestamp_sec': timestamp, 'timestamp_source': 'opencv_reported' if use_reported else 'fps_estimate', 'frame_index': frame_index, 'fps': fps, 'interval_sec': interval_sec, 'start_sec': start_sec, 'end_sec': effective_end_sec, 'sampling_method': 'fixed_interval_fps_seek_with_optional_blank_filter', 'source_video': str(video_path), **quality, 'filter_status': 'skipped' if skipped else 'kept'}
            if skipped:
                audit_records.append({**base, 'sample_id': None, 'shot_id': None, 'keyframe_path': None})
            else:
                index = len(kept_records) + 1
                output_path = output_dir / f'{prefix}_sample_{index:06d}.png'
                if not cv2.imwrite(str(output_path), frame):
                    raise IOError(f'Cannot save image: {output_path}')
                record = {**base, 'sample_id': index, 'shot_id': index, 'keyframe_path': str(output_path)}
                kept_records.append(record)
                audit_records.append(record)
            previous_frame = frame_index
        if not kept_records:
            raise ValueError('No usable frames remain; check start/end times and filtering thresholds')
        table = pd.DataFrame(kept_records)
        audit = pd.DataFrame(audit_records)
        table.to_csv(output_dir / 'samples.csv', index=False)
        audit.to_csv(output_dir / 'sampling_audit.csv', index=False)
        audit[audit['filter_status'] == 'skipped'].to_csv(output_dir / 'skipped_samples.csv', index=False)
        return (table, output_dir)
    finally:
        cap.release()
