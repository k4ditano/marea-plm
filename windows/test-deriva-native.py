"""Run the real SQLite worker on isolated Unicode paths; no UI or user library."""
import argparse
import base64
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--worker', type=Path, required=True)
args = parser.parse_args()
worker = args.worker.resolve()

with tempfile.TemporaryDirectory(prefix='deriva native ñ ') as temporary:
    root = Path(temporary)
    library = root / 'biblioteca 海'
    env = dict(os.environ, MAREA_DERIVA_DIR=str(library))

    def run(*command, environment=None):
        result = subprocess.run([str(worker), *command], env=environment or env,
            capture_output=True, text=True, encoding='utf-8', timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        assert result.returncode == 0, result.stderr + result.stdout
        value = json.loads(result.stdout)
        assert value.get('ok', True), value
        return value.get('result', value)

    def ingest(value):
        return run('ingest', '--request', json.dumps(value, ensure_ascii=False))

    where = run('where')
    assert Path(where['base']) == library
    if os.name == 'nt':
        assert where['socket'] is None
        default_env = dict(env, LOCALAPPDATA=str(root / 'local appdata'))
        default_env.pop('MAREA_DERIVA_DIR')
        assert Path(run('where', environment=default_env)['base']) == root / 'local appdata/proyecto-marea/deriva'
        unsupported = subprocess.run([str(worker), 'serve'], env=env, capture_output=True, timeout=10)
        assert unsupported.returncode == 2 and b'unavailable' in unsupported.stderr
    capture = {'type': 'text', 'title': 'Recuerdo de Le\u00f3n', 'text': 'El faro ilumina la bah\u00eda.'}
    assert ingest(capture)['saved'] == 1
    assert ingest(capture)['duplicates'] == 1
    assert len(run('search', '--query', 'bahia')['items']) == 1
    assert ingest({'type': 'url', 'source_url': 'https://example.com/deriva?utm_source=test'})['saved'] == 1
    document = root / 'dibujo 海 ñ.txt'
    data = 'T\u00edtulo con acentos y Unicode: 海.\n'.encode()
    document.write_bytes(data)
    result = ingest({'type': 'file', 'paths': [str(document)]})
    assert result['saved'] == 1, result
    digest = hashlib.sha256(data).hexdigest()
    blob = library / 'blobs' / digest[:2] / digest[2:4] / digest
    assert blob.read_bytes() == data
    assert ingest({'type': 'file', 'paths': [str(document)]})['duplicates'] == 1
    own_db = ingest({'type': 'file', 'paths': [str(library / 'library.sqlite3')]})
    assert own_db['items'][0]['reason'] == 'ya_es_de_la_biblioteca'
    # Distinct processes must not derive colliding IDs from the same clock tick.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        added = list(pool.map(lambda n: ingest({'type': 'text', 'text': f'Concurrent capture number {n}'}), range(24)))
    identifiers = [item['items'][0]['id'] for item in added]
    assert all(item['saved'] == 1 for item in added) and len(set(identifiers)) == 24
    assert len(run('list', '--limit', '100')['items']) == 27
    assert run('integrity-check', '--deep')['ok']
    backup = run('backup', '--keep', '2')
    assert Path(backup['path']).is_file()
    assert run('integrity-check', '--deep', '--db', backup['path'])['ok']
    exported = root / 'exportaci\u00f3n 海'
    assert run('export', '--directory', str(exported))['captures'] == 27
    other = dict(env, MAREA_DERIVA_DIR=str(root / 'restored 海'))
    run('import', '--deriva', str(exported), environment=other)
    assert len(run('list', '--limit', '100', environment=other)['items']) == 27
    assert run('integrity-check', '--deep', environment=other)['ok']
    assert not list((library / 'blobs/.tmp').iterdir())
    video = ingest({'type': 'url', 'source_url': 'https://youtu.be/dQw4w9WgXcQ'})['items'][0]['id']
    # A payload above Windows' argv limit must cross stdin unchanged. The
    # protocol stores bytes; the fetch helper separately checks JPEG responses.
    preview = bytes(range(256)) * 200
    request = {'id': video, 'title': 'Video title ñ 海', 'author': 'Author',
        'preview_b64': base64.b64encode(preview).decode('ascii')}
    def enrich(payload):
        return subprocess.run([str(worker), 'enrich', '--request-stdin'], input=payload,
            env=env, capture_output=True, text=True, encoding='utf-8', timeout=30,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    response = enrich(json.dumps(request, ensure_ascii=False))
    assert response.returncode == 0, response.stdout + response.stderr
    item = json.loads(response.stdout)['result']['item']
    assert item['title'] == request['title'] and Path(item['preview_path']).read_bytes() == preview
    response = enrich(json.dumps({'id': video, 'title': 'replacement', 'author': 'replacement',
        'preview_b64': base64.b64encode(b'replacement').decode()}))
    assert response.returncode == 0
    persisted = run('get', '--id', video)['item']
    assert persisted['title'] == request['title'] and persisted['author'] == request['author']
    assert Path(persisted['preview_path']).read_bytes() == preview
    assert enrich('x' * 1_048_577).returncode != 0
    assert enrich('{broken json').returncode != 0
    assert run('integrity-check', '--deep')['ok']
print('PASS: real Deriva CLI, SQLite persistence, Unicode paths, concurrent IDs, deduplication, FTS, blobs, backup and export/import')
