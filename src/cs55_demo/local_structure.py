"""Directional local edge support under translation + isotropic scale only.

Heuristic geometry diagnostics, NOT semantic landmark recognition or probability.
Coordinates refer to the existing 128x128 normalized image canvas.
"""
import cv2
import numpy as np

LOCAL_SETTINGS = dict(scales=[.5,.75,1.,1.25,1.5], tolerance_px=2,
                      orientation_bins=4, min_edge_points=20,
                      strong_coverage=.75, partial_coverage=.4,
                      min_distinct_margin=.04, max_background_hit_fraction=.5,
                      min_source_bbox_fraction=.08,
                      assessment='uncalibrated_geometric_heuristic_v1')


def _orientation(record):
    smooth=cv2.GaussianBlur(record['canonical'],(3,3),0).astype(np.float32)
    gy,gx=np.gradient(smooth)
    return np.floor((np.arctan2(gy,gx)%np.pi)*4/np.pi).astype(int)%4


def local_support(source,target):
    result=dict(coverage=None,oriented_coverage=None,assessment='insufficient_evidence',
                confidence='low',reason='insufficient_edges',bbox=None,
                coordinate_space='normalized_128_canvas',heuristic=True)
    sy,sx=np.nonzero(source['edges'])
    if not source['valid'] or not target['valid'] or len(sx)<20:
        return result
    x0,x1,y0,y1=int(sx.min()),int(sx.max()+1),int(sy.min()),int(sy.max()+1)
    bw,bh=x1-x0,y1-y0
    src_bins=_orientation(source)[sy,sx]
    tgt_bins=_orientation(target)
    kernel=cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5))
    hits=cv2.dilate((target['edges']>0).astype(np.uint8),kernel).astype(np.float32)
    oriented=[cv2.dilate(((target['edges']>0)&(tgt_bins==b)).astype(np.uint8),kernel).astype(np.float32)
              for b in range(4)]
    alternatives=[]
    for scale in LOCAL_SETTINGS['scales']:
        xx=np.rint((sx-x0)*scale).astype(int)
        yy=np.rint((sy-y0)*scale).astype(int)
        w,h=int(xx.max()+1),int(yy.max()+1)
        if w>128 or h>128 or min(w,h)<4:
            continue
        # Count original source points, including collisions after downscaling:
        # denominator stays the ORIGINAL source edge count.
        score=np.zeros((129-h,129-w),np.float32)
        for b in range(4):
            template=np.zeros((h,w),np.float32)
            mask=src_bins==b
            np.add.at(template,(yy[mask],xx[mask]),1.)
            score+=cv2.matchTemplate(oriented[b],template,cv2.TM_CCORR)
        score=np.clip(score/len(sx),0,1)
        # Retain distinct translation alternatives, not just adjacent pixels.
        for _ in range(3):
            py,px=np.unravel_index(np.argmax(score),score.shape)
            value=float(score[py,px])
            if value<0: break
            alternatives.append((value,int(px),int(py),w,h,scale,xx,yy))
            rx,ry=max(4,w//3),max(4,h//3)
            score[max(0,py-ry):py+ry+1,max(0,px-rx):px+rx+1]=-1
    if not alternatives:
        result['reason']='no_feasible_scale'; return result
    alternatives.sort(key=lambda v:v[0],reverse=True)
    best=alternatives[0]
    value,tx,ty,w,h,scale,xx,yy=best
    matched=np.array([oriented[b][ty+y,tx+x]>0 for b,x,y in zip(src_bins,xx,yy)])
    covered=hits[ty+yy,tx+xx]>0
    cells=np.minimum((sy-y0)*3//bh,2)*3+np.minimum((sx-x0)*3//bw,2)
    occupied=[int(c) for c in np.unique(cells) if np.count_nonzero(cells==c)>=5]
    supported=[c for c in occupied if matched[cells==c].mean()>=.6]
    # Best geometrically distinct competitor; same-center nearby-scale peaks
    # describe the same region and are not counted as a separate match.
    distinct=[a[0] for a in alternatives[1:]
              if abs((a[1]+a[3]/2)-(tx+w/2))>w*.35
              or abs((a[2]+a[4]/2)-(ty+h/2))>h*.35]
    margin=float(value-max(distinct)) if distinct else None
    background=float(hits[ty:ty+h,tx:tx+w].mean())
    orientation_count=sum(np.count_nonzero(src_bins==b)>=len(sx)*.1 for b in range(4))
    rich=(len(occupied)>=3 and orientation_count>=2 and bw*bh/(128*128)>=.08)
    ambiguous=margin is None or margin<.04
    assessment='insufficient_evidence'; reason='low_or_nondistinct_support'
    if value>=.4 and background<.5 and rich:
        assessment='partial_support'; reason='partial_or_ambiguous_alignment'
        if value>=.75 and len(supported)>=3 and not ambiguous:
            assessment='structural_support'; reason='multiple_spatial_regions_supported'
    elif value>=.4 and background<.5:
        reason='source_structure_too_sparse_or_simple'
    if background>=.5:
        reason='dense_target_edges_allow_chance_overlap'
    result.update(coverage=float(covered.mean()),oriented_coverage=float(matched.mean()),
        assessment=assessment,reason=reason,confidence='review_required' if assessment=='structural_support' else 'low',
        bbox=[tx,ty,tx+w,ty+h],source_bbox=[x0,y0,x1,y1],scale=float(scale),
        original_source_edge_count=int(len(sx)),matched_source_edge_count=int(covered.sum()),
        occupied_regions=len(occupied),supported_regions=len(supported),
        orientation_count=int(orientation_count),distinct_peak_margin=margin,
        target_near_edge_fraction=background,
        matched_fraction_note='Extra target edges do not enter coverage denominator; density is an ambiguity warning.')
    return result


def local_matrix(source,target):
    matrix=np.full((len(source),len(target)),np.nan,dtype=np.float32)
    details={}
    for i,a in enumerate(source):
        for j,b in enumerate(target):
            result=local_support(a,b)
            details[(i,j)]=result
            if result['oriented_coverage'] is not None:
                matrix[i,j]=result['oriented_coverage']
        if (i+1)%10==0 or i+1==len(source): print('Local structure',i+1,'/',len(source))
    return matrix,details


def show_local(source,target,result):
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle
    fig,axes=plt.subplots(1,3,figsize=(12,4))
    axes[0].imshow(source['canonical'],cmap='gray',vmin=0,vmax=255)
    axes[1].imshow(target['canonical'],cmap='gray',vmin=0,vmax=255)
    axes[2].imshow(255-target['edges'],cmap='gray',vmin=0,vmax=255)
    if result['bbox']:
        tx,ty,x2,y2=result['bbox']; x0,y0,_,_=result['source_bbox']
        for ax in axes[1:]: ax.add_patch(Rectangle((tx,ty),x2-tx,y2-ty,fill=False,edgecolor='red'))
        sy,sx=np.nonzero(source['edges'])
        xx=np.rint((sx-x0)*result['scale']).astype(int)+tx
        yy=np.rint((sy-y0)*result['scale']).astype(int)+ty
        hit=cv2.dilate((target['edges']>0).astype(np.uint8),
                      cv2.getStructuringElement(cv2.MORPH_ELLIPSE,(5,5)))
        axes[2].scatter(xx,yy,s=2,c=np.where(hit[yy,xx]>0,'green','red'))
    for ax,title in zip(axes,['Source','Target + best region','Projected source: green covered / red missed']):
        ax.set_title(title,fontsize=9); ax.axis('off')
    fig.tight_layout(); return fig
