// Network enrichment stays outside the offline Deriva worker.
import {execFile} from 'node:child_process';
import {access} from 'node:fs/promises';
import {fileURLToPath, pathToFileURL} from 'node:url';

export function youtubeId(value) {
  try {
    const url = new URL(value);
    if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password || url.port) return null;
    let id;
    if (url.hostname === 'youtu.be') id = url.pathname.slice(1);
    else if (['youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'].includes(url.hostname)) {
      if (url.pathname === '/watch') id = url.searchParams.get('v');
      else id = url.pathname.match(/^\/(?:shorts|embed|live)\/([^/]+)\/?$/)?.[1];
    }
    return /^[A-Za-z0-9_-]{11}$/.test(id ?? '') ? id : null;
  } catch { return null; }
}

async function bytes(url, limit, fetcher) {
  const response = await fetcher(url, {signal: AbortSignal.timeout(8000), redirect: 'error', credentials: 'omit'});
  if (!response.ok || Number(response.headers.get('content-length')) > limit) throw new Error('Preview unavailable');
  const reader = response.body.getReader();
  const chunks = [];
  let length = 0;
  try {
    for (;;) {
      const {done, value} = await reader.read();
      if (done) break;
      length += value.byteLength;
      if (length > limit) throw new Error('Preview exceeds size limit');
      chunks.push(value);
    }
  } finally { await reader.cancel(); }
  return Buffer.concat(chunks, length);
}

async function worker(command, request) {
  let executable = process.env.MAREA_DERIVA_WORKER;
  if (!executable) {
    const bundled = fileURLToPath(new URL('../../bin/deriva-worker.exe', import.meta.url));
    try { await access(bundled); executable = bundled; }
    catch { executable = 'deriva-worker'; }
  }
  return new Promise((resolve, reject) => {
    const child = execFile(executable, command, {windowsHide: true, timeout: 15000, maxBuffer: 2 * 1024 * 1024}, (error, stdout) => {
      if (error) return reject(new Error('Deriva could not load the preview'));
      try {
        const value = JSON.parse(stdout);
        if (!value.ok) throw new Error('Deriva rejected the preview');
        resolve(value.result);
      } catch (error) { reject(error); }
    });
    child.stdin.on('error', () => {}); // An early worker exit is reported above.
    child.stdin.end(request === undefined ? undefined : JSON.stringify(request));
  });
}

export async function enrichPreview(id, {invoke = worker, fetcher = fetch, exists = access} = {}) {
  if (!/^[a-f0-9]{16,64}$/.test(id ?? '')) throw new Error('Invalid capture id');
  const {item} = await invoke(['get', '--id', id]);
  if (!item || item.id !== id) throw new Error('Capture unavailable');
  const video = youtubeId(item.canonical_url || item.source_url);
  if (!video) return {item};
  if (item.preview_path) {
    try { await exists(item.preview_path); return {item}; } catch { /* A missing cache may be repaired. */ }
  }
  const url = 'https://www.youtube.com/watch?v=' + video;
  const [metadata, thumbnail] = await Promise.allSettled([
    bytes('https://www.youtube.com/oembed?url=' + encodeURIComponent(url) + '&format=json', 65536, fetcher)
      .then(data => JSON.parse(data.toString('utf8'))),
    bytes('https://i.ytimg.com/vi/' + video + '/mqdefault.jpg', 512 * 1024, fetcher),
  ]);
  const request = {id};
  if (metadata.status === 'fulfilled') {
    for (const [key, field] of [['title', 'title'], ['author', 'author_name']]) {
      if (typeof metadata.value?.[field] === 'string') request[key] = metadata.value[field].slice(0, 2048);
    }
  }
  if (thumbnail.status === 'fulfilled') {
    const data = thumbnail.value;
    if (data.length > 4 && data[0] === 0xff && data[1] === 0xd8 && data[2] === 0xff
        && data.at(-2) === 0xff && data.at(-1) === 0xd9) request.preview_b64 = data.toString('base64');
  }
  if (Object.keys(request).length === 1) return {item};
  return invoke(['enrich', '--request-stdin'], request);
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--id') throw new Error('Expected --id CAPTURE_ID');
    console.log(JSON.stringify({ok: true, result: await enrichPreview(process.argv[3])}));
  } catch {
    console.log(JSON.stringify({ok: false, error: 'Video preview unavailable; the saved link is unchanged.'}));
    process.exitCode = 1;
  }
}
