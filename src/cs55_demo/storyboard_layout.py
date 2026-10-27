"""Conservative PDF panel proposals. No proposal is automatically accepted."""
from pathlib import Path
import hashlib
import json
import uuid
import cv2
import numpy as np
import fitz
from PIL import Image, ImageDraw

DETECTOR_VERSION = 'auto-layout-v4'


def _content_region(image, text_boxes=()):
    """Estimate outer whitespace only; never trim individual panel interiors."""
    gray = np.asarray(image.convert('L'))
    h, w = gray.shape
    mask = (gray < 245).astype(np.uint8)
    # Exclude PDF text from the *estimate*, not from the original page image.
    for x0, y0, x1, y1 in text_boxes:
        mask[max(0, int(y0)):min(h, int(np.ceil(y1))),
             max(0, int(x0)):min(w, int(np.ceil(x1)))] = 0
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    keep = np.zeros_like(mask)
    for label in range(1, count):
        x, y, bw, bh, area = stats[label]
        if area >= max(4, w*h*.000002):
            keep[labels == label] = 1
    ys, xs = np.nonzero(keep)
    if not len(xs):
        return (0, 0, w, h), keep, 'uncertain_no_visual_content'
    pad = max(8, round(min(w, h)*.015))
    box = (max(0, int(xs.min())-pad), max(0, int(ys.min())-pad),
           min(w, int(xs.max())+1+pad), min(h, int(ys.max())+1+pad))
    return box, keep, 'estimated_outer_whitespace'


def _gutter_boxes(mask, region):
    """Conservative borderless fallback; every result still needs review."""
    x0, y0, x1, y1 = region
    def spans(values, minimum_gap):
        active = np.flatnonzero(values)
        if not len(active):
            return []
        cuts = np.flatnonzero(np.diff(active) >= minimum_gap)
        starts = [int(active[0])] + [int(active[k+1]) for k in cuts]
        ends = [int(active[k])+1 for k in cuts] + [int(active[-1])+1]
        return list(zip(starts, ends))
    crop = mask[y0:y1, x0:x1]
    boxes = []
    for a, b in spans(crop.any(axis=1), max(16, round(mask.shape[0]*.025))):
        for c, d in spans(crop[a:b].any(axis=0), max(16, round(mask.shape[1]*.025))):
            if d-c >= mask.shape[1]*.1 and b-a >= mask.shape[0]*.05:
                boxes.append((max(x0, x0+c-8), max(y0, y0+a-8),
                              min(x1, x0+d+8), min(y1, y0+b+8)))
    # A borderless storyboard may intentionally contain one full-page panel.
    # Returning that single region is safe because it remains pending review.
    return boxes


def _table_picture_boxes(image, boxes, known_bounds=None):
    """Recover the visual column of repeated storyboard table rows."""
    if len(boxes) < 3:
        return [], known_bounds
    widths = np.array([b[2]-b[0] for b in boxes])
    typical = float(np.median(widths))
    wide = [b for b in boxes if b[2]-b[0] > typical*1.5
            and b[2]-b[0] < image.width*.7]
    if known_bounds is None and wide:
        known_bounds = (int(np.median([b[0] for b in wide])),
                        int(np.median([b[2] for b in wide])))
    if known_bounds is None:
        return [], None

    # Narrow memo/effects cells reliably expose row boundaries even when dark
    # adjacent images merge into one contour in the visual column.
    row_candidates = [b for b in boxes if b[2]-b[0] <= typical*1.25]
    bands = []
    for box in sorted(row_candidates, key=lambda b: (b[1], b[3])):
        band = (box[1], box[3])
        if not any(abs(band[0]-old[0]) <= 4 and abs(band[1]-old[1]) <= 4
                   for old in bands):
            bands.append(band)
    heights = [b-a for a,b in bands]
    if len(bands) < 3 or not heights:
        return [], known_bounds
    row_height = float(np.median(heights))
    bands = [(a,b) for a,b in bands if .75*row_height <= b-a <= 1.25*row_height]

    gray = np.asarray(image.convert('L'))
    x0, x1 = known_bounds
    visual = []
    for y0, y1 in bands:
        pad = max(4, round(min(x1-x0, y1-y0)*.035))
        interior = gray[y0+pad:y1-pad, x0+pad:x1-pad]
        if interior.size and (interior.mean() < 252 or interior.std() > 2):
            visual.append((x0, y0, x1, y1))
    return visual, known_bounds


def _area(box):
    return max(0, box[2]-box[0]) * max(0, box[3]-box[1])


def _deduplicate(boxes):
    kept = []
    for box in sorted(boxes, key=_area):
        # Prefer inner image frames over containing tables; keep overlapping
        # candidates for human review unless they substantially contain one another.
        if any(_area((max(box[0], k[0]), max(box[1], k[1]),
                      min(box[2], k[2]), min(box[3], k[3]))) / _area(k) > .9 for k in kept):
            continue
        kept.append(box)
    return sorted(kept, key=lambda b: (b[1], b[0]))


def _border_boxes(image):
    gray = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    binary = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 31, 9)
    contours, _ = cv2.findContours(binary, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    boxes = []
    for contour in contours:
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, .02 * perimeter, True)
        x, y, w, h = cv2.boundingRect(contour)
        fraction = w*h/(width*height)
        if (len(approx) == 4 and cv2.isContourConvex(approx)
                and .015 < fraction < .85 and w > width*.1 and h > height*.05
                and cv2.contourArea(contour)/(w*h) > .75):
            boxes.append((x, y, x+w, y+h))
    return _deduplicate(boxes)


def propose_panels(pdf_path, output_root):
    pdf_path = Path(pdf_path).resolve()
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    run = Path(output_root) / ('review_' + uuid.uuid4().hex[:12])
    run.mkdir(parents=True, exist_ok=False)
    pages = []
    picture_bounds = None
    with fitz.open(pdf_path) as document:
        for number, page in enumerate(document, 1):
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
            page_file = run / f'page_{number:03d}.png'
            image.save(page_file)
            sx, sy = image.width/page.rect.width, image.height/page.rect.height
            text_boxes = []
            for block in page.get_text('blocks'):
                if len(block) > 6 and block[6] == 0:
                    rect = fitz.Rect(block[:4]) * page.rotation_matrix
                    text_boxes.append((rect.x0*sx, rect.y0*sy, rect.x1*sx, rect.y1*sy))
            content_box, mask, margin_status = _content_region(image, text_boxes)
            boxes = []
            # Occurrences, not unique xrefs: reused images retain their positions.
            if page.rotation == 0:
                for info in page.get_image_info():
                    rect = fitz.Rect(info['bbox']) & page.rect
                    if rect.is_empty:
                        continue
                    fraction = rect.get_area()/page.rect.get_area()
                    if .015 < fraction < .85:
                        boxes.append((round(rect.x0*sx), round(rect.y0*sy),
                                      round(rect.x1*sx), round(rect.y1*sy)))
            embedded = boxes
            borders = _border_boxes(image)
            def text_only(box):
                x0, y0, x1, y1 = map(int, box)
                overlaps_text = any(min(x1,t[2]) > max(x0,t[0]) and
                                    min(y1,t[3]) > max(y0,t[1]) for t in text_boxes)
                inset = max(8, round(min(x1-x0,y1-y0)*.04))
                inside = mask[y0+inset:y1-inset, x0+inset:x1-inset]
                return overlaps_text and (inside.size == 0 or inside.mean() < .001)
            borders = [box for box in borders if not text_only(box)]
            # Always run both detectors. Inner frames replace containing tables.
            boxes = _deduplicate(embedded + borders)
            table_boxes, learned_bounds = _table_picture_boxes(image, boxes, picture_bounds)
            if learned_bounds is not None:
                picture_bounds = learned_bounds
            if table_boxes:
                boxes = table_boxes
                method_by_box = {box: 'table_picture_column' for box in boxes}
            else:
                method_by_box = {box: ('embedded_image_region' if box in embedded else
                                       'border_candidate') for box in boxes}
            fallback = not boxes
            if fallback:
                boxes = _gutter_boxes(mask, content_box)
            # No automatic whole-page substitution for failed segmentation.
            candidates = [{'bbox': list(box),
                           'method': ('whitespace_candidate' if fallback else method_by_box[box]),
                           'needs_boundary_review': True,
                           'decision': 'pending'} for box in boxes]
            preview = image.copy()
            draw = ImageDraw.Draw(preview)
            draw.rectangle(content_box, outline='blue', width=3)
            for index, box in enumerate(boxes, 1):
                draw.rectangle(box, outline='red', width=4)
                draw.text((box[0]+5, box[1]+5), str(index), fill='red')
            preview_file = run / f'preview_{number:03d}.png'
            preview.save(preview_file)
            pages.append({'page_index': number, 'page_path': str(page_file),
                          'preview_path': str(preview_file), 'size': list(image.size),
                          'content_bbox': list(content_box), 'margin_status': margin_status,
                          'warnings': (['Whitespace segmentation may split internal composition; check boundaries.']
                                       if fallback else []),
                          'reviewed': False, 'candidates': candidates})
    manifest = {'schema_version': 'panel-review-v1', 'detector_version': DETECTOR_VERSION,
                'source_pdf': str(pdf_path),
                'source_sha256': digest, 'run_dir': str(run), 'pages': pages,
                'limitations': ['Heuristic candidates, not verified panels.',
                                'Default top-to-bottom order requires review.',
                                'Text, logos, composite images and borderless layouts require review.',
                                'Bounding boxes use rendered-page pixels at scale 2.']}
    (run/'review.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest


def export_reviewed(manifest):
    """Explicit accept/reject per candidate and reviewed flag per page required.

    Users can edit bbox, reorder candidates, add manual boxes, or accept a
    whole-page box intentionally. Empty pages must also be reviewed.
    """
    if any(not p['reviewed'] or any(c['decision'] not in ('accept', 'reject')
                                   for c in p['candidates']) for p in manifest['pages']):
        raise ValueError('Review every page and accept/reject every candidate first.')
    if hashlib.sha256(Path(manifest['source_pdf']).read_bytes()).hexdigest() != manifest['source_sha256']:
        raise ValueError('Source PDF changed; regenerate candidates.')
    selections = []
    for page in manifest['pages']:
        w, h = page['size']
        for candidate in page['candidates']:
            if candidate['decision'] == 'reject':
                continue
            box = candidate['bbox']
            if len(box) != 4 or not all(isinstance(v, (int, float)) for v in box):
                raise ValueError('Invalid bounding box')
            x1, y1, x2, y2 = box
            if not (0 <= x1 < x2 <= w and 0 <= y1 < y2 <= h):
                raise ValueError('Bounding box outside page')
            selections.append((page, candidate))
    if not selections:
        raise ValueError('No accepted panels; evaluation must not proceed.')
    destination = Path(manifest['run_dir']) / ('accepted_' + uuid.uuid4().hex[:12])
    destination.mkdir()
    records, counters = [], {}
    for page, candidate in selections:
        number = page['page_index']
        counters[number] = counters.get(number, 0) + 1
        index = counters[number]
        path = destination/f'page_{number:03d}_panel_{index:03d}.png'
        with Image.open(page['page_path']) as image:
            image.crop(candidate['bbox']).save(path)
        records.append({'page_index': number, 'panel_index': index, 'panel_path': str(path),
                        'bbox': candidate['bbox'], 'method': candidate['method'],
                        'source_pdf': manifest['source_pdf'],
                        'source_sha256': manifest['source_sha256'], 'review_status': 'accepted'})
    (destination/'panels.json').write_text(json.dumps(records, indent=2), encoding='utf-8')
    (destination/'review.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return records
