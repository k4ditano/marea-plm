import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, readFile, rm, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {bytes, discover, metadata, unescape, saveImage, release} from './deriva-fetch.mjs';

test('metadata understands attribute order, quotes, casing and valid Unicode entities', () => {
  assert.deepEqual(metadata(`<META CONTENT='Título &#x1f30a; &amp; mar' PROPERTY='og:title'>
    <meta name="description" content="Más &quot;palabras&quot;">
    <meta content=/cover.jpg property=og:image>`),
  {title: 'Título 🌊 & mar', excerpt: 'Más "palabras"', image: '/cover.jpg'});
  assert.equal(unescape('&#1114112; &#xD800; &#0; &#65;'), '� � � A');
});

test('generic pages resolve relative covers against the final redirect URL without cookies', async () => {
  const visited = [];
  const result = await discover('https://example.test/old', async (url, options) => {
    visited.push(url);
    assert.equal(options.credentials, 'omit'); assert.equal(options.redirect, 'manual');
    if (url.endsWith('/old')) return new Response('', {status: 302, headers: {location: '/folder/page'}});
    if (url.endsWith('/folder/page')) return new Response('<meta property="og:image" content="cover.png"><meta property="og:title" content="Portada ñ">');
    assert.equal(url, 'https://example.test/folder/cover.png');
    return new Response(Buffer.from('image payload'));
  });
  assert.equal(result.title, 'Portada ñ');
  assert.equal(result.image.toString(), 'image payload');
  assert.equal(visited.length, 3);
});

test('YouTube gets an actual thumbnail even without oEmbed; errors keep valid text', async () => {
  const result = await discover('https://youtu.be/dQw4w9WgXcQ', async url =>
    url.includes('/oembed?') ? new Response('', {status: 403}) : new Response('cover'));
  assert.equal(result.image.toString(), 'cover');
  const generic = await discover('https://example.test/page', async url => url.endsWith('/page')
    ? new Response('<meta property="og:title" content="Saved"><meta property="og:image" content="/huge">')
    : new Response('x', {headers: {'content-length': '9000000'}}));
  assert.deepEqual(generic, {title: 'Saved'});
});

test('X and Reddit preserve the upstream public metadata sources with exact hosts', async () => {
  const x = await discover('https://x.com/someone/status/12345', async url => url.includes('api.fxtwitter.com')
    ? new Response(JSON.stringify({tweet: {text: 'A post', author: {name: 'Name', screen_name: 'someone'}, media: {photos: [{url: 'https://images.test/p.jpg'}]}}}))
    : new Response('pixels'));
  assert.equal(x.title, 'Name (@someone)'); assert.equal(x.excerpt, 'A post');
  const reddit = await discover('https://www.reddit.com/r/example/a', async url => {
    assert(url.startsWith('https://www.reddit.com/oembed?'));
    return new Response(JSON.stringify({title: 'Post title'}));
  });
  assert.deepEqual(reddit, {title: 'Post title'});
});

test('download limits apply to streams, redirect loops, schemes and credentials', async () => {
  await assert.rejects(bytes('file:///C:/secret', 10, () => { throw new Error('must not fetch'); }));
  await assert.rejects(bytes('https://user:pass@example.test/', 10));
  await assert.rejects(bytes('https://example.test/', 10, async () => new Response(Buffer.alloc(11))));
  await assert.rejects(bytes('https://example.test/', 10, async () => new Response('', {status: 302, headers: {location: 'file:///C:/secret'}})));
  let count = 0;
  await assert.rejects(bytes('https://example.test/', 10, async () => {
    count++; return new Response('', {status: 302, headers: {location: '/again'}});
  }));
  assert.equal(count, 5);
});

test('owned temporary images handle Unicode paths and reject deleting unrelated files', async () => {
  const directory = await mkdtemp(join(tmpdir(), 'marea covers ñ 海 '));
  try {
    const path = await saveImage(Buffer.from('first'), directory);
    assert.deepEqual(await readFile(path), Buffer.from('first'));
    const concurrent = await saveImage(Buffer.from('first'), directory);
    assert.notEqual(concurrent, path);
    const other = join(directory, 'keep.txt'); await writeFile(other, 'keep');
    await assert.rejects(release(other, directory));
    await assert.rejects(release(join(directory, '..', 'a'.repeat(64) + '.raw'), directory));
    await release(path, directory); await release(path, directory);
    assert.deepEqual(await readFile(concurrent), Buffer.from('first'));
    assert.equal((await readFile(other)).toString(), 'keep');
  } finally { await rm(directory, {recursive: true, force: true}); }
});
