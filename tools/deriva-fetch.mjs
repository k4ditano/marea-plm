// Fetch a visible card's public metadata. Image conversion stays in pleamar.
import {createHash, randomUUID} from 'node:crypto';
import {mkdir, readdir, stat, writeFile, rename, unlink} from 'node:fs/promises';
import {join, resolve, basename} from 'node:path';
import {pathToFileURL} from 'node:url';
import {youtubeId} from './deriva-preview.mjs';

function web(value, base) {
  const url = new URL(value, base);
  if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password) throw new Error('Unsupported preview URL');
  return url;
}

export async function bytes(value, limit, fetcher = fetch) {
  let url = web(value);
  const signal = AbortSignal.timeout(10000);
  for (let redirects = 0; redirects <= 4; redirects++) {
    const response = await fetcher(url.href, {signal, credentials: 'omit', redirect: 'manual',
      headers: {'User-Agent': 'Marea preview/1.0', Accept: '*/*'}});
    if ([301, 302, 303, 307, 308].includes(response.status)) {
      await response.body?.cancel();
      if (!response.headers.get('location')) throw new Error('Missing preview redirect');
      url = web(response.headers.get('location'), url);
      continue;
    }
    if (!response.ok || !response.body || Number(response.headers.get('content-length')) > limit) {
      await response.body?.cancel();
      throw new Error('Preview unavailable');
    }
    const reader = response.body.getReader(), chunks = [];
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
    return {data: Buffer.concat(chunks, length), url: url.href};
  }
  throw new Error('Too many preview redirects');
}

export function unescape(value) {
  return String(value).replace(/&#(x[0-9a-f]+|\d+);|&(quot|apos|lt|gt|amp);/gi, (whole, number, name) => {
    if (name) return {quot: '"', apos: "'", lt: '<', gt: '>', amp: '&'}[name.toLowerCase()];
    const n = number[0].toLowerCase() === 'x' ? parseInt(number.slice(1), 16) : Number(number);
    return n > 0 && n <= 0x10ffff && !(n >= 0xd800 && n <= 0xdfff) ? String.fromCodePoint(n) : '\ufffd';
  });
}

export function metadata(html) {
  const fields = new Map();
  for (const match of html.matchAll(/<meta\s[^>]{0,16384}>/gi)) {
    const attrs = new Map();
    for (const a of match[0].matchAll(/([\w:-]+)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+))/g))
      attrs.set(a[1].toLowerCase(), unescape(a[2] ?? a[3] ?? a[4]));
    const key = attrs.get('property') ?? attrs.get('name');
    if (key && attrs.get('content')) fields.set(key.toLowerCase(), attrs.get('content'));
  }
  return {image: fields.get('og:image') ?? fields.get('twitter:image'), title: fields.get('og:title'),
    excerpt: fields.get('og:description') ?? fields.get('description')};
}

export async function discover(value, fetcher = fetch) {
  const url = web(value), video = youtubeId(url.href);
  let found = {};
  const getJSON = async value => JSON.parse((await bytes(value, 512 * 1024, fetcher)).data.toString('utf8'));
  if (video) {
    found.image = `https://i.ytimg.com/vi/${video}/hqdefault.jpg`;
    try {
      const data = await getJSON('https://www.youtube.com/oembed?url=' + encodeURIComponent('https://www.youtube.com/watch?v=' + video) + '&format=json');
      found.title = data.title; found.author = data.author_name;
    } catch { /* The actual thumbnail remains useful when oEmbed is unavailable. */ }
  } else if (['x.com', 'www.x.com', 'twitter.com', 'www.twitter.com'].includes(url.hostname) && /\/status\/\d+/.test(url.pathname)) {
    const post = url.pathname.match(/\/status\/(\d+)/)[1];
    const {tweet} = await getJSON('https://api.fxtwitter.com/status/' + post);
    if (tweet && typeof tweet === 'object') {
      found = {image: tweet.media?.photos?.[0]?.url ?? tweet.media?.videos?.[0]?.thumbnail_url ?? tweet.author?.avatar_url,
        excerpt: tweet.text, title: tweet.author?.name ? `${tweet.author.name} (@${tweet.author.screen_name ?? ''})` : undefined};
    }
  } else if (url.hostname === 'reddit.com' || url.hostname.endsWith('.reddit.com')) {
    found.title = (await getJSON('https://www.reddit.com/oembed?url=' + encodeURIComponent(url.href))).title;
  } else {
    const result = await bytes(url.href, 3 * 1024 * 1024, fetcher);
    found = metadata(result.data.toString('utf8'));
    if (found.image) found.image = web(found.image, result.url).href;
  }
  const result = {};
  for (const key of ['title', 'author', 'excerpt']) if (typeof found[key] === 'string' && found[key].trim()) result[key] = found[key].slice(0, key === 'excerpt' ? 16000 : 2048);
  if (typeof found.image === 'string' && !found.image.includes('abs.twimg.com/rweb/ssr/default')) {
    try { result.image = (await bytes(web(found.image).href, 8 * 1024 * 1024, fetcher)).data; }
    catch { /* Keep valid text metadata even if the picture cannot be read. */ }
  }
  return result;
}

const ownedName = /^[a-f0-9]{64}\.raw$/;
function cacheRoot() {
  if (!process.env.LOCALAPPDATA) throw new Error('LOCALAPPDATA unavailable');
  return resolve(process.env.LOCALAPPDATA, 'Marea', 'DerivaFetch');
}
export async function saveImage(data, directory = cacheRoot()) {
  if (!Buffer.isBuffer(data) || data.length > 8 * 1024 * 1024) throw new Error('Invalid preview');
  await mkdir(directory, {recursive: true});
  // A second Marea instance may download the same picture. Each download owns
  // its source file; releasing one must not remove another instance's input.
  const name = createHash('sha256').update(randomUUID()).update(data).digest('hex') + '.raw', output = join(directory, name);
  const partial = output + '.' + randomUUID() + '.partial';
  try { await writeFile(partial, data, {flag: 'wx'}); await rename(partial, output); }
  finally { await unlink(partial).catch(() => {}); }
  // Abrupt runtime termination may skip release. Bound the owned on-disk
  // downloads independently of the permanent, much smaller library covers.
  const entries = [];
  for (const name of await readdir(directory)) {
    if (!ownedName.test(name)) continue;
    const path = join(directory, name), info = await stat(path).catch(() => null);
    if (info?.isFile()) entries.push({path, size: info.size, time: info.mtimeMs});
  }
  let size = entries.reduce((sum, e) => sum + e.size, 0);
  for (const entry of entries.sort((a, b) => a.time - b.time)) {
    if (entry.path !== output && (size > 32 * 1024 * 1024 || Date.now() - entry.time > 600000)) {
      await unlink(entry.path).catch(() => {}); size -= entry.size;
    }
  }
  return output;
}
export async function release(path, directory = cacheRoot()) {
  if (!ownedName.test(basename(path)) || resolve(path) !== join(resolve(directory), basename(path))) throw new Error('Not an owned download');
  await unlink(path).catch(error => { if (error.code !== 'ENOENT') throw error; });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    if (process.argv.length !== 4) throw new Error('Expected --url URL or --release PATH');
    if (process.argv[2] === '--release') { await release(process.argv[3]); console.log('{"ok":true}'); }
    else if (process.argv[2] === '--url') {
      const result = await discover(process.argv[3]);
      if (result.image) { result.image_file = await saveImage(result.image); delete result.image; }
      console.log(JSON.stringify({ok: true, result}));
    } else throw new Error('Unknown command');
  } catch {
    console.log('{"ok":false,"error":"Preview unavailable; the saved capture is unchanged."}');
    process.exitCode = 1;
  }
}
