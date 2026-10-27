"""Local React frontend and API over the shared CS55 algorithm modules."""
import io
import json
import platform
import subprocess
import sys
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, FileResponse, Response
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from cs55_demo.system import load_config, prepare, retrieve, inspect_provenance, apply_reviews, save_json
from cs55_demo.automatic import validate_ranges

executor = ThreadPoolExecutor(max_workers=1)
jobs, lock = {}, threading.Lock()


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text()) if path.is_file() else default


def resolve_run(run_id):
    path = (ROOT / 'outputs' / run_id).resolve()
    if path.parent != (ROOT / 'outputs').resolve() or not (path / 'prepared.json').is_file():
        raise ValueError('Unknown run')
    return path


def task(action):
    job_id = uuid.uuid4().hex
    with lock:
        if len(jobs) >= 50:
            completed = [k for k, v in jobs.items() if v['state'] != 'running']
            for key in completed[:25]:
                del jobs[key]
        jobs[job_id] = dict(state='running', messages=[], run_id=None, error=None)

    def progress(message):
        with lock:
            jobs[job_id]['messages'] = (jobs[job_id]['messages'] + [str(message)])[-30:]

    def execute():
        try:
            run = action(progress)
            with lock:
                jobs[job_id].update(state='completed', run_id=Path(run).name)
        except Exception as error:
            with lock:
                jobs[job_id].update(state='failed', error=str(error))
    executor.submit(execute)
    return JSONResponse(dict(job_id=job_id))


async def bootstrap(request):
    paths = sorted((ROOT / 'outputs').glob('run_*/prepared.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    config_path = ROOT / 'config.local.json'
    config = load_config(config_path if config_path.exists() else ROOT / 'config.example.json')
    return JSONResponse(dict(config=config, runs=[dict(id=p.parent.name, created=p.stat().st_mtime,
        has_results=(p.parent / 'result.json').is_file()) for p in paths], native_picker=platform.system() == 'Darwin'))


async def detail(request):
    run = resolve_run(request.path_params['run_id'])
    return JSONResponse(dict(id=run.name, config=read(run/'config.json'), prepared=read(run/'prepared.json'),
        result=read(run/'result.json'), decisions=read(run/'effective_decisions.json', []),
        matches=read(run/'matched_list.json', []), scores=read(run/'evidence_scores.json'),
        correspondence=read(run/'correspondence_diagnostics.json'),
        provenance=read(run/'provenance_scores.json'), timestamps=read(run/'timestamp_comparisons.json'),
        reviews=read(run/'reviews.json', []), files=[p.name for p in sorted(run.glob('*.json'))]))


async def start_prepare(request):
    config = await request.json()
    for field in ('final_path', 'storyboard_path', 'animatic_path', 'project_search_root'):
        if config.get(field):
            value = Path(config[field]).expanduser()
            config[field] = str(value.resolve() if value.is_absolute() else (ROOT/value).resolve())
    config['output_dir'] = str(ROOT / 'outputs')
    config['correspondence_ranges'] = []
    # Normalize and validate using the same loader as notebook and CLI.
    staging = ROOT / 'outputs' / ('request_' + uuid.uuid4().hex + '.json')
    save_json(staging, config)
    normalized = load_config(staging)
    staging.unlink()
    return task(lambda progress: prepare(normalized, progress=progress)['run_dir'])


async def update_ranges(request):
    run = resolve_run(request.path_params['run_id'])
    body = await request.json()
    ranges = body['ranges']
    validate_ranges(ranges)
    prepared = read(run/'prepared.json')
    known = {p['evidence_index'] for p in prepared['panels']}
    for rule in ranges:
        if rule['evidence_type'] == 'storyboard' and not set(rule['panel_indices']).issubset(known):
            raise ValueError('The range includes unknown extracted panel IDs')
        if rule['evidence_type'] == 'animatic' and not prepared['frames']['animatic']:
            raise ValueError('No Animatic material was submitted')
    config = read(run/'config.json')
    config['correspondence_ranges'] = ranges
    if (run/'result.json').exists():
        run = new_revision(prepared, config)
    else:
        save_json(run/'config.json', config)
    return JSONResponse(dict(run_id=run.name))


def new_revision(prepared, config):
    run = ROOT / 'outputs' / ('run_revision_' + uuid.uuid4().hex[:12])
    run.mkdir(parents=True)
    save_json(run/'prepared.json', dict(prepared, run_dir=str(run)))
    save_json(run/'config.json', config)
    return run


async def start_match(request):
    run = resolve_run(request.path_params['run_id'])
    config = read(run/'config.json')
    settings = await request.json()
    config['matching'].update(settings)
    config['matching'].setdefault('acceptance_mode', 'range_top1')
    prepared = read(run/'prepared.json')
    # Every match job writes into its own revision; earlier reviews are preserved.
    run = new_revision(prepared, config)
    config = load_config(run/'config.json')
    prepared = read(run/'prepared.json')

    def execute(progress):
        retrieve(config, prepared, progress=progress)
        return run
    return task(execute)


async def start_provenance(request):
    run = resolve_run(request.path_params['run_id'])
    def execute(progress):
        inspect_provenance(read(run/'config.json'), read(run/'prepared.json'), progress=progress)
        return run
    return task(execute)


async def review(request):
    run = resolve_run(request.path_params['run_id'])
    body = await request.json()
    existing = {(r['route'], r['final_index']): r for r in read(run/'reviews.json', [])}
    for item in body['reviews']:
        existing[(item['route'], item['final_index'])] = item
    apply_reviews(run, list(existing.values()))
    return JSONResponse(dict(saved=True))


async def job_status(request):
    with lock:
        value = jobs.get(request.path_params['job_id'])
        return JSONResponse(dict(value) if value else {'error': 'Unknown job'}, status_code=200 if value else 404)


async def media(request):
    run = resolve_run(request.path_params['run_id'])
    prepared = read(run/'prepared.json')
    paths = {str(Path(p['panel_path']).resolve()) for p in prepared['panels']}
    paths.update(str(Path(f['keyframe_path']).resolve()) for rows in prepared['frames'].values() for f in rows)
    path = Path(request.query_params.get('path', '')).resolve()
    if str(path) not in paths or not path.is_file():
        return Response(status_code=404)
    with Image.open(path) as image:
        preview = image.convert('RGB')
        preview.thumbnail((960, 640))
        buffer = io.BytesIO()
        preview.save(buffer, 'JPEG', quality=85)
    return Response(buffer.getvalue(), media_type='image/jpeg', headers={'Cache-Control': 'private, max-age=3600'})


async def download(request):
    run = resolve_run(request.path_params['run_id'])
    name = request.path_params['name']
    if Path(name).name != name or not name.endswith('.json') or not (run/name).is_file():
        return Response(status_code=404)
    return FileResponse(run/name, filename=name, media_type='application/json')


async def upload(request):
    role = request.path_params['role']
    suffix = Path(request.query_params.get('filename', '')).suffix.lower()
    if role not in ('final', 'animatic', 'storyboard') or suffix not in (('.pdf',) if role == 'storyboard' else ('.mp4', '.mov', '.mkv', '.avi', '.webm')):
        raise ValueError('Unsupported material file type')
    destination = ROOT/'outputs'/('uploads_'+uuid.uuid4().hex[:12])
    destination.mkdir(parents=True)
    path = destination/(role+suffix)
    size = 0
    try:
        with path.open('wb') as handle:
            async for chunk in request.stream():
                size += len(chunk)
                if size > 10 * 1024**3:
                    raise ValueError('Upload exceeds 10 GB; use a local path')
                handle.write(chunk)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return JSONResponse(dict(path=str(path), bytes=size))


async def choose_file(request):
    if platform.system() != 'Darwin':
        raise ValueError('Native path selection is available on macOS; use Upload or enter a path')
    completed = await run_in_threadpool(subprocess.run,
        ['osascript', '-e', 'POSIX path of (choose file with prompt "Select a CS55 material")'],
        capture_output=True, text=True, timeout=120)
    return JSONResponse(dict(path=completed.stdout.strip() if completed.returncode == 0 else None))


async def handle_error(request, exc):
    return JSONResponse(dict(error=str(exc)), status_code=400)


routes = [Route('/api/bootstrap', bootstrap), Route('/api/prepare', start_prepare, methods=['POST']),
          Route('/api/upload/{role}', upload, methods=['POST']), Route('/api/choose-file', choose_file, methods=['POST']),
          Route('/api/jobs/{job_id}', job_status), Route('/api/runs/{run_id}', detail),
          Route('/api/runs/{run_id}/ranges', update_ranges, methods=['POST']),
          Route('/api/runs/{run_id}/match', start_match, methods=['POST']),
          Route('/api/runs/{run_id}/provenance', start_provenance, methods=['POST']),
          Route('/api/runs/{run_id}/reviews', review, methods=['POST']),
          Route('/api/runs/{run_id}/media', media), Route('/api/runs/{run_id}/download/{name}', download)]
dist = ROOT/'frontend/dist'
if dist.is_dir():
    routes.append(Mount('/', app=StaticFiles(directory=dist, html=True)))
app = Starlette(routes=routes, exception_handlers={ValueError: handle_error, FileNotFoundError: handle_error, KeyError: handle_error})

# Bind only to loopback when launched as a script.
if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8505)
