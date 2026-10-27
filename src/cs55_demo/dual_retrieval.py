"""Independent CLIP/edge-HOG candidate retrieval. No fused score or verdict."""
from pathlib import Path
import hashlib
import cv2
import numpy as np

SETTINGS = dict(size=128, canny_low=50, canny_high=150,
                min_gray_span=5, min_edge_pixels=10, polarity='border_median',
                contrast='percentile_1_99_with_minmax_fallback',
                hog='128win_16block_8stride_8cell_9bins_unsigned')


def _hog(image):
    # NumPy implementation: unsigned orientations, 8px cells, 2x2-cell
    # overlapping blocks, orientation interpolation, L2-Hys normalization.
    gy,gx=np.gradient(image.astype(np.float32))
    magnitude=np.hypot(gx,gy)
    orientation=(np.arctan2(gy,gx) % np.pi)*(9/np.pi)
    base=np.floor(orientation).astype(int)
    fraction=orientation-base
    cells=np.zeros((16,16,9),dtype=np.float32)
    yy,xx=np.indices(image.shape)
    np.add.at(cells,(yy//8,xx//8,base%9),magnitude*(1-fraction))
    np.add.at(cells,(yy//8,xx//8,(base+1)%9),magnitude*fraction)
    blocks=[]
    for y in range(15):
        for x in range(15):
            v=cells[y:y+2,x:x+2].reshape(-1).copy()
            v/=np.sqrt(np.dot(v,v)+1e-10)
            v=np.minimum(v,.2)
            v/=np.sqrt(np.dot(v,v)+1e-10)
            blocks.append(v)
    return np.concatenate(blocks)


def structure_feature(path):
    path = Path(path).resolve()
    gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if gray is None:
        raise ValueError(f'Cannot read image: {path}')
    raw_span = int(gray.max())-int(gray.min())
    border = np.concatenate((gray[0], gray[-1], gray[:,0], gray[:,-1]))
    inverted = bool(np.median(border) < 127.5)
    if inverted:
        gray = 255-gray
    lo, hi = np.percentile(gray, [1,99])
    if hi-lo < 5:
        lo, hi = float(gray.min()), float(gray.max())
    normalized = (np.full_like(gray,255) if raw_span < 5 else
                  np.uint8(np.clip((gray.astype(float)-lo)*255/max(hi-lo,1),0,255)))
    h,w = gray.shape
    scale = 128/max(h,w)
    nw,nh = max(1,round(w*scale)),max(1,round(h*scale))
    resized = cv2.resize(normalized,(nw,nh),interpolation=cv2.INTER_AREA if scale<1 else cv2.INTER_LINEAR)
    edge = cv2.Canny(cv2.GaussianBlur(resized,(3,3),0),50,150)
    # Edges BEFORE padding: letterboxing must not introduce artificial borders.
    canvas = np.zeros((128,128),dtype=np.uint8)
    y,x = (128-nh)//2,(128-nw)//2
    canvas[y:y+nh,x:x+nw] = edge
    canonical = np.full((128,128),255,dtype=np.uint8)
    canonical[y:y+nh,x:x+nw] = resized
    edge_count = int(np.count_nonzero(edge))
    vector = _hog(canvas)
    norm = float(np.linalg.norm(vector))
    valid = raw_span >= 5 and edge_count >= 10 and norm > 1e-8
    return dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                feature=vector/max(norm,1e-8), canonical=canonical, edges=canvas,
                valid=bool(valid), polarity_inverted=inverted, raw_gray_span=raw_span,
                edge_pixels=edge_count, edge_density=edge_count/(nw*nh),
                reason=None if valid else 'insufficient_contrast_or_edges')


def structural_matrix(source,target):
    if not source or not target:
        raise ValueError('Both image lists must be nonempty')
    matrix = np.stack([r['feature'] for r in source]) @ np.stack([r['feature'] for r in target]).T
    for i,r in enumerate(source):
        if not r['valid']:
            matrix[i,:] = np.nan
    for j,r in enumerate(target):
        if not r['valid']:
            matrix[:,j] = np.nan
    return matrix


def union_candidates(clip,structure,source,target,k=5,target_times=None):
    clip,structure = np.asarray(clip),np.asarray(structure)
    expected = (len(source),len(target))
    if clip.shape != expected or structure.shape != expected:
        raise ValueError('Matrix shape/input order mismatch')
    if not np.isfinite(clip).all() or k < 1:
        raise ValueError('CLIP must be finite; k must be positive')
    rows=[]
    for i in range(len(source)):
        clip_order=np.argsort(-clip[i],kind='stable')
        usable=np.flatnonzero(np.isfinite(structure[i]))
        struct_order=usable[np.argsort(-structure[i,usable],kind='stable')]
        cr={int(j):rank+1 for rank,j in enumerate(clip_order)}
        sr={int(j):rank+1 for rank,j in enumerate(struct_order)}
        clip_top=set(map(int,clip_order[:k])); struct_top=set(map(int,struct_order[:k]))
        # Display in target sequence order, not a misleading fused ranking.
        for j in sorted(clip_top|struct_top):
            rows.append(dict(source_index=i+1,target_index=j+1,
                source_path=source[i]['path'],target_path=target[j]['path'],
                clip_similarity=float(clip[i,j]),clip_rank=cr[j],
                structure_similarity=float(structure[i,j]) if j in sr else None,
                structure_rank=sr.get(j),from_clip=j in clip_top,from_structure=j in struct_top,
                source_structure_valid=source[i]['valid'],target_structure_valid=target[j]['valid'],
                target_timestamp_sec=None if target_times is None else float(target_times[j]),
                status='candidate_not_verified'))
    return rows


def show_candidate(source,target):
    import matplotlib.pyplot as plt
    from PIL import Image
    fig,axes=plt.subplots(2,3,figsize=(12,7))
    for row,record in enumerate((source,target)):
        with Image.open(record['path']) as img:
            axes[row,0].imshow(img.convert('RGB'))
        axes[row,1].imshow(record['canonical'],cmap='gray',vmin=0,vmax=255)
        axes[row,2].imshow(255-record['edges'],cmap='gray',vmin=0,vmax=255)
        for col,title in enumerate(('Original','Polarity/contrast normalized','Edges used by HOG')):
            axes[row,col].set_title(('Source: ' if row==0 else 'Target: ')+title)
            axes[row,col].axis('off')
    fig.tight_layout()
    return fig
